# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Sonnet 5（型号 claude-sonnet-5）、Claude Opus 5.5（型号 claude-opus-5-5）
# 开发机构：Anthropic 公司
# 版本发布日期：Claude Sonnet 5 为 2026-06-30，Claude Opus 5.5 为 2026-09-22
"""问题 3 的只读 L2 收益模型。

与官方评估器的语义严格对齐（见《评估器机制说明》O 节）：

* 只有 ``COPY_IN`` 查询 Cache，键为它写入的**片上**张量的逻辑 id；
* 未命中走 DDR 池并在完成时按 FIFO 写入，命中走独立的 ``CACHE_READ`` 池；
* 单个张量大于 Cache 容量则不缓存；命中不刷新 FIFO 顺序。

由此，命中只可能来自两类结构：

1. **跨核多播**：同一张量被 $|\\mathcal C_t|$ 个核心读入，第一次未命中，其余命中；
2. **换入复读**：Step2 对同一逻辑张量多次换入，第二次起命中。

本模块给出复用度、Cache 价值、期望节省与 Cache 压力四个量，
并提供一个忽略淘汰的**乐观上界**估计（用于分配阶段的代价折算）。
"""

from __future__ import annotations

from collections import OrderedDict, defaultdict

from . import graphlib, paths


def copy_in_multiset(g: graphlib.Graph, core_of_op: dict):
    """按场景 B 的插入规则，枚举每个 tensor 产生的 COPY_IN 次数与所在核。

    返回 ``{tensor_id: [core, ...]}``，列表顺序即评估器遍历顺序
    （``for tensor_id in sorted(tensor_by_id)``，核按升序）。
    """
    reads = {}
    for tid in sorted(g.tensors):
        ps, cs = g.producers[tid], g.consumers[tid]
        if not ps and not cs:
            continue
        pc = sorted({core_of_op[o] for o in ps})
        cc = sorted({core_of_op[o] for o in cs})
        seq = []
        if cs and not ps:                      # 图输入：每个消费核读一次
            seq.extend(cc)
        for sc in pc:                          # 跨核：每个 (src,dst) 一次
            for dc in cc:
                if dc != sc:
                    seq.append(dc)
        if seq:
            reads[tid] = seq
    return reads


def reuse_degree(g: graphlib.Graph, core_of_op: dict) -> dict:
    """reuse(t) = 该张量产生的 COPY_IN 次数（≥2 才可能命中）。"""
    return {tid: len(seq) for tid, seq in copy_in_multiset(g, core_of_op).items()}


def cache_value(g: graphlib.Graph, core_of_op: dict,
                capacity: int | None = None) -> dict:
    """value(t) = s_t · (reuse(t) − 1) · 1[s_t ≤ C_L2]，即可被 L2 服务的字节。"""
    cap = paths.official_config()['cache_capacity_bytes'] if capacity is None \
        else capacity
    out = {}
    for tid, seq in copy_in_multiset(g, core_of_op).items():
        size = g.size(tid)
        if size and size <= cap and len(seq) > 1:
            out[tid] = size * (len(seq) - 1)
    return out


def expected_saved_ddr(g: graphlib.Graph, core_of_op: dict, **kw) -> int:
    return sum(cache_value(g, core_of_op, **kw).values())


def expected_time_saved(g: graphlib.Graph, core_of_op: dict, **kw) -> float:
    """命中把 s/bw 变成 s/bw_L2，并把这部分字节移出 DDR 争用。"""
    cfg = paths.official_config()
    saved = expected_saved_ddr(g, core_of_op, **kw)
    return saved * (1.0 / cfg['bandwidth'] - 1.0 / cfg['cache_bandwidth_bytes_per_cycle'])


def cache_pressure(g: graphlib.Graph, core_of_op: dict,
                   capacity: int | None = None) -> float:
    """Cache 压力 = 可缓存的活跃张量总字节 / L2 容量。

    远大于 1 说明 FIFO 会频繁淘汰，"乐观上界"会显著高估命中率。
    """
    cfg = paths.official_config()
    cap = cfg['cache_capacity_bytes'] if capacity is None else capacity
    total = sum(g.size(tid) for tid, seq in
                copy_in_multiset(g, core_of_op).items()
                if len(seq) > 1 and 0 < g.size(tid) <= cap)
    return total / cap if cap else 0.0


def simulate_fifo_hits(g: graphlib.Graph, core_of_op: dict,
                       order=None, capacity: int | None = None) -> dict:
    """按 FIFO 语义复演一遍插入/淘汰，给出比"乐观上界"更紧的命中估计。

    ``order`` 为 COPY_IN 的近似发生顺序；缺省用张量 id 升序（与评估器构造
    Task 时的遍历顺序一致）。真实执行顺序由多核事件模拟决定，故这里只是
    一个更保守的估计，用于分析而非最终成绩。
    """
    cfg = paths.official_config()
    cap = cfg['cache_capacity_bytes'] if capacity is None else capacity
    reads = copy_in_multiset(g, core_of_op)
    seq = order or [(tid, core) for tid in sorted(reads) for core in reads[tid]]
    entries: OrderedDict = OrderedDict()
    used = 0
    hit_bytes = miss_bytes = 0
    hits = misses = 0
    for tid, _core in seq:
        size = g.size(tid)
        if not size:
            continue
        if tid in entries:
            hit_bytes += size
            hits += 1
            continue
        miss_bytes += size
        misses += 1
        if size > cap:
            continue
        while entries and used + size > cap:
            _, old = entries.popitem(last=False)
            used -= old
        entries[tid] = size
        used += size
    total = hit_bytes + miss_bytes
    return {'hits': hits, 'misses': misses, 'hit_bytes': hit_bytes,
            'miss_bytes': miss_bytes,
            'hit_rate': hit_bytes / total if total else 0.0,
            'resident_bytes': used}


def summarize(g: graphlib.Graph, core_of_op: dict) -> dict:
    """一次性给出论文 §8 所需的全部量。"""
    val = cache_value(g, core_of_op)
    deg = reuse_degree(g, core_of_op)
    sim = simulate_fifo_hits(g, core_of_op)
    return {
        'n_cacheable_tensors': len(val),
        'max_reuse_degree': max(deg.values(), default=0),
        'expected_saved_ddr_bytes': sum(val.values()),
        'expected_time_saved_cycles': expected_time_saved(g, core_of_op),
        'cache_pressure': cache_pressure(g, core_of_op),
        'fifo_hit_rate_estimate': sim['hit_rate'],
        'optimistic_hit_bytes': sum(val.values()),
        'fifo_hit_bytes': sim['hit_bytes'],
    }
