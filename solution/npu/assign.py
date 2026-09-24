"""核心分配与代价模型。

本模块提供两类东西：

1. **解析代价模型**：在不调用官方评估器的前提下，快速估计一个
   (块→核) 分配的 Makespan。问题 1 用"Task 级事件模拟"（与评估器的
   Task 激活规则同构），问题 2/3 用"每核逐 Pipe 负载 + 跨核同步深度"。
2. **分配算法**：LPT 贪心 + Kernighan–Lin 风格的移动/交换局部搜索。

**重要**：解析模型只用于搜索内部剪枝；任何对外汇报的指标一律由
``evaluate`` 模块调用官方评估器得到。
"""

from __future__ import annotations

import math
import random
from collections import defaultdict

from . import graphlib, paths

PIPE_BW_HIT = 'cache'


# --------------------------------------------------------------------------
# 通信量模型
# --------------------------------------------------------------------------

def scene_b_traffic(bs, core_of_block, num_cores, cache_capacity=0):
    """问题 2/3：按核统计 COPY_IN / COPY_OUT 字节与 Cache 命中字节。

    与 ``_build_scene_b_tasks`` 的插入规则逐条对应：
      * 图输入：每个消费核各读一次；
      * 图输出：每个生产核各写一次；
      * 跨核：每个 (生产核, 消费核) 组合一对 COPY_OUT/COPY_IN。
    Cache 命中估计：同一 tensor id 的第 2 次及以后的 COPY_IN 命中
    （FIFO 只读 Cache 以逻辑 tensor id 为键）。
    """
    g = bs.g
    cin = [0] * num_cores
    cout = [0] * num_cores
    cin_hit = [0] * num_cores
    total = 0
    cross = 0
    for tid, (pb, cb) in bs.tensor_blocks.items():
        size = g.size(tid)
        if not size:
            continue
        pc = {core_of_block[b] for b in pb}
        cc = {core_of_block[b] for b in cb}
        is_out = tid in g.graph_output_tensor
        readers = []
        if cb and not pb:                       # 图输入
            readers = sorted(cc)
        if pb and (is_out or not cb):           # 图输出
            for k in pc:
                cout[k] += size
                total += size
        for sc in pc:                           # 跨核搬运
            for dc in cc:
                if dc == sc:
                    continue
                cout[sc] += size
                total += size
                cross += size
                readers.append(dc)
        for idx, k in enumerate(readers):
            cin[k] += size
            total += size
            if idx > 0 and 0 < size <= cache_capacity:
                cin_hit[k] += size
    return {'cin': cin, 'cout': cout, 'cin_hit': cin_hit,
            'total_bytes': total, 'cross_bytes': cross}


def scene_a_traffic(bs, groups, core_of_group, num_cores):
    """问题 1：以"子图组"为单位统计边界搬运字节。

    ``groups[i]`` 是第 i 个子图包含的块 id 列表，``core_of_group[i]`` 是其核。
    """
    g = bs.g
    group_of_block = {}
    for gi, blocks in enumerate(groups):
        for b in blocks:
            group_of_block[b] = gi
    n = len(groups)
    cin = [0] * n
    cout = [0] * n
    total = 0
    for tid, (pb, cb) in bs.tensor_blocks.items():
        size = g.size(tid)
        if not size:
            continue
        pg = {group_of_block[b] for b in pb}
        cg = {group_of_block[b] for b in cb}
        is_out = tid in g.graph_output_tensor
        for s in cg - pg:
            cin[s] += size
            total += size
        for s in pg:
            if is_out or not cg or (cg - {s}):
                cout[s] += size
                total += size
    return {'cin': cin, 'cout': cout, 'total_bytes': total,
            'group_of_block': group_of_block, 'core_of_group': core_of_group}


# --------------------------------------------------------------------------
# Makespan 解析估计
# --------------------------------------------------------------------------

def estimate_scene_a(bs, groups, core_of_group, num_cores, cfg=None):
    """Task 级事件模拟：与评估器的 Task 激活规则同构。

    Task 时长用 ``max(M, V, (cin+cout)/bw)`` 估计（四条 Pipe 并行，但
    两类 COPY 共用 DDR 带宽），再叠加同核切换与跨核等待。
    """
    cfg = cfg or paths.official_config()
    bw = cfg['bandwidth']
    same_wait = cfg['task_same_core_wait_cycles']
    cross_wait = cfg['task_cross_core_wait_cycles']
    tr = scene_a_traffic(bs, groups, core_of_group, num_cores)
    gob = tr['group_of_block']
    n = len(groups)

    duration = []
    for i, blocks in enumerate(groups):
        m = sum(bs.mcycles[b] for b in blocks)
        v = sum(bs.vcycles[b] for b in blocks)
        copy_time = (tr['cin'][i] + tr['cout'][i]) / bw
        duration.append(max(m, v, copy_time, 1.0))

    preds = [set() for _ in range(n)]
    for i in range(bs.m):
        for j in bs.succ[i]:
            a, b = gob[i], gob[j]
            if a != b:
                preds[b].add(a)

    core_prev_end = [None] * num_cores
    end = [0.0] * n
    order_by_core = defaultdict(list)
    for i in range(n):
        order_by_core[core_of_group[i]].append(i)
    # 子图 id 按 σ 递增，因此按 id 升序推进即为合法激活顺序
    ready_index = {k: 0 for k in range(num_cores)}
    finished = set()
    pending = list(range(n))
    makespan = 0.0
    # 按 id 升序模拟：每个 Task 的开始时刻 = max(同核前一 Task 结束+切换,
    # 跨核前驱结束+同步, 同核前驱结束)
    for i in pending:
        k = core_of_group[i]
        start = 0.0
        if core_prev_end[k] is not None:
            start = core_prev_end[k] + same_wait
        for p in preds[i]:
            if core_of_group[p] != k:
                start = max(start, end[p] + cross_wait)
            else:
                start = max(start, end[p])
        end[i] = start + duration[i]
        core_prev_end[k] = end[i]
        makespan = max(makespan, end[i])
        finished.add(i)
    ddr_lb = tr['total_bytes'] / bw
    return max(makespan, ddr_lb), {'traffic': tr, 'duration': duration,
                                   'ddr_lb': ddr_lb}


def estimate_scene_b(bs, core_of_block, num_cores, cfg=None,
                     cache_capacity=0, cache_bw=None):
    """问题 2/3：每核四条 Pipe 负载 + 跨核同步深度 + 全局 DDR 下界。"""
    cfg = cfg or paths.official_config()
    bw = cfg['bandwidth']
    delay = cfg['cross_core_copy_delay_cycles']
    cbw = cache_bw or cfg['cache_bandwidth_bytes_per_cycle']
    tr = scene_b_traffic(bs, core_of_block, num_cores, cache_capacity)
    per_core = []
    for k in range(num_cores):
        m = v = 0
        for i in range(bs.m):
            if core_of_block[i] == k:
                m += bs.mcycles[i]
                v += bs.vcycles[i]
        hit = tr['cin_hit'][k]
        miss = tr['cin'][k] - hit
        mte2 = miss / bw + hit / cbw
        mte3 = tr['cout'][k] / bw
        per_core.append(max(m, v, mte2, mte3))
    ddr_bytes = tr['total_bytes'] - sum(tr['cin_hit'])
    ddr_lb = ddr_bytes / bw
    # 跨核同步深度：块级 DAG 上"换核次数"的最长链
    depth = _cross_core_depth(bs, core_of_block)
    est = max(max(per_core), ddr_lb) + delay * depth
    return est, {'traffic': tr, 'per_core': per_core, 'ddr_lb': ddr_lb,
                 'cross_depth': depth}


def _cross_core_depth(bs, core_of_block) -> int:
    best = [0] * bs.m
    top = 0
    for i in range(bs.m):
        cur = 0
        for p in bs.pred[i]:
            cand = best[p] + (1 if core_of_block[p] != core_of_block[i] else 0)
            if cand > cur:
                cur = cand
        best[i] = cur
        top = max(top, cur)
    return top


# --------------------------------------------------------------------------
# 分配算法
# --------------------------------------------------------------------------

def lpt_assign(bs, num_cores, comm_weight: float = 0.0, seed: int = 0):
    """LPT 贪心：按计算量降序放入"使 max(M,V) 增量最小"的核。

    ``comm_weight`` > 0 时对"与已分配邻块不同核"的字节施加惩罚，
    实现通信感知装箱。
    """
    order = sorted(range(bs.m), key=lambda i: (-bs.work[i], i))
    core = [-1] * bs.m
    loadM = [0.0] * num_cores
    loadV = [0.0] * num_cores
    neigh = defaultdict(dict)
    if comm_weight > 0:
        for (a, b), byt in bs.pair_bytes.items():
            neigh[a][b] = byt
            neigh[b][a] = byt
    for i in order:
        best, best_cost = 0, None
        for k in range(num_cores):
            cost = max(loadM[k] + bs.mcycles[i], loadV[k] + bs.vcycles[i])
            if comm_weight > 0:
                pen = sum(b for j, b in neigh[i].items()
                          if core[j] >= 0 and core[j] != k)
                cost += comm_weight * pen
            if best_cost is None or cost < best_cost:
                best, best_cost = k, cost
        core[i] = best
        loadM[best] += bs.mcycles[i]
        loadV[best] += bs.vcycles[i]
    return core


def round_robin_assign(bs, num_cores):
    return [i % num_cores for i in range(bs.m)]


def contiguous_assign(bs, num_cores):
    """沿 σ 把块切成 N 段连续区间，按计算量均分。

    对"链状块图"（体同步/归约结构）特别有用：跨核同步层次数从 O(m)
    降到 O(N)，问题 1 的 Task 串行级数因而大幅减少。
    """
    total = sum(bs.work) or 1
    core, acc, k = [], 0.0, 0
    for i in range(bs.m):
        core.append(min(k, num_cores - 1))
        acc += bs.work[i]
        while k < num_cores - 1 and acc >= total * (k + 1) / num_cores:
            k += 1
    return core


def random_assign(bs, num_cores, seed=0):
    rng = random.Random(seed)
    return [rng.randrange(num_cores) for _ in range(bs.m)]


def refine_assignment(bs, core_of_block, num_cores, objective,
                      max_passes: int = 8, max_moves: int = 4000,
                      rng: random.Random | None = None):
    """移动式局部搜索：把块换到另一核，若目标下降则接受。

    ``objective(core_of_block) -> float``，调用方决定用场景 A 还是 B 的
    解析模型。为控制规模，每轮只考察"负载最重核"上的块。
    """
    rng = rng or random.Random(0)
    best = objective(core_of_block)
    cur = list(core_of_block)
    moves = 0
    for _ in range(max_passes):
        improved = False
        loads = defaultdict(float)
        for i in range(bs.m):
            loads[cur[i]] += bs.work[i]
        hot = sorted(range(num_cores), key=lambda k: -loads[k])[:max(2, num_cores // 2 + 1)]
        candidates = [i for i in range(bs.m) if cur[i] in hot]
        rng.shuffle(candidates)
        for i in candidates:
            if moves >= max_moves:
                break
            src = cur[i]
            for k in range(num_cores):
                if k == src:
                    continue
                cur[i] = k
                val = objective(cur)
                moves += 1
                if val < best - 1e-9:
                    best = val
                    improved = True
                    break
                cur[i] = src
        if not improved or moves >= max_moves:
            break
    return cur, best
