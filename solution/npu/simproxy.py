"""算子级事件模拟代理：在不调用官方评估器的前提下估计方案的 Makespan。

模型规则（全部写死，不加开关）：

1. 核内算子序列：按方案的核内子图顺序排列子图，子图内算子按 ``g.topo``
   中的位置排序（近似评估器 Step1 的顺序）。
2. 搬运算子：图输入张量在每个核第一次使用前插入一个 MTE2 搬入；跨核张量在
   生产核的（最后一个）生产算子之后、对每个消费核各插入一个 MTE3 搬出，消费核
   在第一次使用前插入 MTE2 搬入，其就绪时刻 = 对应搬出完成 +
   ``cross_core_copy_delay_cycles``。不模拟 spill。
   问题 1 的子图即 Task，直接使用 Task 级事件模拟（``estimate_scene_a_from_plan``）。
3. 流水：每核四条流水各自串行。计算算子时长 = ``cycles``；DDR 搬运时长 =
   字节 / (带宽 / 当前在途 DDR 搬运数)，在途数在开始时刻计算（含自身）并在
   执行期间视为常数。问题 3 中若张量此前已被任一核搬入且仍在容量为
   ``cache_capacity_bytes`` 的 FIFO 中，则时长 = 字节 / Cache 带宽，且不计入
   DDR 在途数；未命中的搬入在完成时写入 FIFO。
4. 全局申请序：核内按序发射，序列中第 i 个操作的开始时刻 ≥ 第 i−1 个的开始时刻；
   各流水可乱序完成。
5. 返回 max(全部操作完成时刻, DDR 总字节 / 带宽)。

仅用于候选排序与分析，论文中的 Makespan 一律来自官方评估器。
"""

from __future__ import annotations

import heapq
from collections import OrderedDict

PIPE_INDEX = {'PIPE_MTE2': 0, 'PIPE_MTE3': 1, 'PIPE_M': 2, 'PIPE_V': 3}
MTE2, MTE3 = 0, 1


def _topo_pos(g):
    pos = g._cache.get('topo_pos')
    if pos is None:
        pos = {v: i for i, v in enumerate(g.topo)}
        g._cache['topo_pos'] = pos
    return pos


def estimate(g, plan, problem, cfg) -> float:
    mapping = {int(k): int(v) for k, v in plan['node_to_subgraph'].items()}
    schedules = [list(order) for order in plan['core_schedules']]
    if problem == 1:
        from validate_model import estimate_scene_a_from_plan
        return estimate_scene_a_from_plan(g, mapping, schedules, cfg)
    return _scene_b(g, mapping, schedules, cfg, use_cache=(problem == 3))


def _scene_b(g, mapping, schedules, cfg, use_cache=False):
    bw = float(cfg['bandwidth'])
    delay = cfg['cross_core_copy_delay_cycles']
    cache_cap = cfg['cache_capacity_bytes'] if use_cache else 0
    cache_bw = float(cfg['cache_bandwidth_bytes_per_cycle'])
    num_cores = len(schedules)
    topo_pos = _topo_pos(g)

    core_of_sub = {}
    for k, order in enumerate(schedules):
        for sg in order:
            core_of_sub[sg] = k
    members = {}
    for v, sg in mapping.items():
        members.setdefault(sg, []).append(v)
    core_of = {v: core_of_sub[sg] for v, sg in mapping.items()}
    core_ops = []
    for order in schedules:
        seq = []
        for sg in order:
            seq.extend(sorted(members.get(sg, ()), key=topo_pos.__getitem__))
        core_ops.append(seq)
    pos_in_core = {}
    for seq in core_ops:
        for i, v in enumerate(seq):
            pos_in_core[v] = i

    # ---------- 操作表 ----------
    pipe, dur0, nbytes, is_copy_in, tid_of, deps = [], [], [], [], [], []

    def new_item(p, cycles=0, size=0, copy_in=False, tid=None):
        pipe.append(p)
        dur0.append(cycles)
        nbytes.append(size)
        is_copy_in.append(copy_in)
        tid_of.append(tid)
        deps.append([])
        return len(pipe) - 1

    op_item = {}
    in_item = {}            # (tid, src_core | None, dst_core) -> item
    out_item = {}           # (tid, src_core, dst_core) -> item
    seqs = [[] for _ in range(num_cores)]
    for k in range(num_cores):
        for v in core_ops[k]:
            for tid in g.op_in.get(v, ()):
                ps = g.producers.get(tid, ())
                size = g.size(tid)
                if not ps:
                    key = (tid, None, k)
                    if key not in in_item:
                        in_item[key] = new_item(MTE2, size=size, copy_in=True, tid=tid)
                        seqs[k].append(in_item[key])
                    continue
                for s in sorted({core_of[p] for p in ps}):
                    if s == k:
                        continue
                    key = (tid, s, k)
                    if key not in in_item:
                        in_item[key] = new_item(MTE2, size=size, copy_in=True, tid=tid)
                        seqs[k].append(in_item[key])
            it = new_item(PIPE_INDEX[g.pipe(v)], cycles=max(1, g.cycles(v)))
            op_item[v] = it
            seqs[k].append(it)
            for tid in g.op_out.get(v, ()):
                cs = g.consumers.get(tid, ())
                dst = sorted({core_of[c] for c in cs} - {k})
                if not dst:
                    continue
                local = [p for p in g.producers[tid] if core_of[p] == k]
                if max(local, key=pos_in_core.__getitem__) != v:
                    continue
                for d in dst:
                    out_item[(tid, k, d)] = new_item(MTE3, size=g.size(tid), tid=tid)
                    seqs[k].append(out_item[(tid, k, d)])

    # ---------- 依赖 ----------
    for v, it in op_item.items():
        k = core_of[v]
        dl = deps[it]
        for p in g.preds[v]:
            if core_of[p] == k:
                dl.append((op_item[p], 0))
        for tid in g.op_in.get(v, ()):
            ps = g.producers.get(tid, ())
            if not ps:
                dl.append((in_item[(tid, None, k)], 0))
                continue
            for s in {core_of[p] for p in ps}:
                if s != k:
                    dl.append((in_item[(tid, s, k)], 0))
    for (tid, s, d), it in out_item.items():
        for p in g.producers[tid]:
            if core_of[p] == s:
                deps[it].append((op_item[p], 0))
        deps[in_item[(tid, s, d)]].append((it, delay))

    # ---------- 事件模拟（全局按开始时刻递增提交）----------
    n_items = len(pipe)
    finish = [None] * n_items
    ptr = [0] * num_cores
    last_start = [0.0] * num_cores
    pipe_free = [[0.0] * 4 for _ in range(num_cores)]
    ddr_active = []                 # 在途 DDR 搬运的结束时刻
    pending_insert = []             # (完成时刻, 序号, tid, size)
    cache = OrderedDict()
    cache_used = 0
    ddr_bytes = 0
    makespan = 0.0
    counter = 0
    remaining = n_items
    while remaining:
        best = None
        for k in range(num_cores):
            if ptr[k] >= len(seqs[k]):
                continue
            it = seqs[k][ptr[k]]
            ready = last_start[k]
            ok = True
            for d, add in deps[it]:
                f = finish[d]
                if f is None:
                    ok = False
                    break
                if f + add > ready:
                    ready = f + add
            if not ok:
                continue
            start = max(ready, pipe_free[k][pipe[it]])
            if best is None or start < best[0]:
                best = (start, k, it)
        if best is None:
            raise RuntimeError('simproxy: in-order issue deadlock')
        start, k, it = best
        while ddr_active and ddr_active[0] <= start:
            heapq.heappop(ddr_active)
        if tid_of[it] is not None:                     # 搬运操作
            while pending_insert and pending_insert[0][0] <= start:
                _, _, tid, size = heapq.heappop(pending_insert)
                if tid in cache or size > cache_cap:
                    continue
                while cache and cache_used + size > cache_cap:
                    _, old = cache.popitem(last=False)
                    cache_used -= old
                cache[tid] = size
                cache_used += size
            size = nbytes[it]
            if use_cache and is_copy_in[it] and tid_of[it] in cache:
                dur = max(1.0, size / cache_bw)
            else:
                cnt = len(ddr_active) + 1
                dur = max(1.0, size * cnt / bw)
                heapq.heappush(ddr_active, start + dur)
                ddr_bytes += size
                if use_cache and is_copy_in[it]:
                    counter += 1
                    heapq.heappush(pending_insert,
                                   (start + dur, counter, tid_of[it], size))
        else:
            dur = dur0[it]
        end = start + dur
        finish[it] = end
        pipe_free[k][pipe[it]] = end
        last_start[k] = start
        ptr[k] += 1
        remaining -= 1
        if end > makespan:
            makespan = end
    return max(makespan, ddr_bytes / bw)
