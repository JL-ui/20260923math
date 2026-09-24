"""单算子子图下的容量感知表调度：给定算子→核分配，决定每个核的算子全序。

问题 2/3 中核内执行顺序 = Step1 顺序按子图优先级稳定重排；当每个算子单独
成为一个子图时，方案给出的子图顺序就是核内的精确执行顺序。本模块用
HEFT 式上行秩 + 片上驻留惩罚 + 流水互补奖励做确定性表调度，然后按跨核
同步层次做稳定重排，保证 (层次, 核, 核内位置) 编号满足全部硬约束。
"""

from __future__ import annotations

import bisect
import math
import random

PIPES = ('PIPE_MTE2', 'PIPE_MTE3', 'PIPE_M', 'PIPE_V')
PIPE_INDEX = {p: i for i, p in enumerate(PIPES)}
TOP_CANDIDATES = 64


def pair_bytes(g) -> dict:
    """bytes(u, v) = u 的输出张量中被 v 消费的张量大小之和（{u: {v: bytes}}）。"""
    pb = g._cache.get('pair_bytes')
    if pb is None:
        pb = {v: {} for v in g.nodes}
        for u in g.nodes:
            d = pb[u]
            for tid in set(g.op_out.get(u, ())):
                size = g.size(tid)
                for c in g.consumers.get(tid, ()):
                    if c != u:
                        d[c] = d.get(c, 0) + size
        g._cache['pair_bytes'] = pb
    return pb


def upward_rank(g, core_of_op, delay, bandwidth) -> dict:
    """rank_u(v) = cycles(v) + max_s (c(v,s) + rank_u(s))，归一化到 [0, 1]。"""
    pb = pair_bytes(g)
    rank = {}
    for v in reversed(g.topo):
        cv = core_of_op[v]
        best = 0.0
        row = pb[v]
        for s in g.succs[v]:
            c = 0.0 if core_of_op[s] == cv else delay + row.get(s, 0) / bandwidth
            val = c + rank[s]
            if val > best:
                best = val
        rank[v] = max(1, g.cycles(v)) + best
    top = max(rank.values(), default=1.0) or 1.0
    return {v: r / top for v, r in rank.items()}


def schedule(g, core_of_op, levels, problem, cfg, alpha, mu, nu,
             noise=0.0, seed=0, num_cores=None):
    bw = cfg['bandwidth']
    delay = (cfg['task_cross_core_wait_cycles'] if problem == 1
             else cfg['cross_core_copy_delay_cycles'])
    cap = {'L1': cfg['L1'], 'UB': cfg['UB']}
    limit = {pos: alpha * c for pos, c in cap.items()}
    K = num_cores or (max(core_of_op.values()) + 1)
    pb = pair_bytes(g)
    rank = upward_rank(g, core_of_op, delay, bw)
    gumbel = {}
    if noise:
        rng = random.Random(seed)
        for v in g.nodes:
            u = rng.random()
            while u <= 0.0:
                u = rng.random()
            gumbel[v] = -math.log(-math.log(u))

    # 片上张量（L1/UB）的读写表；DDR 张量不计驻留
    outs, ins = {}, {}
    for v in g.nodes:
        o = []
        for tid in set(g.op_out.get(v, ())):
            pos = g.tensors[tid]['pos']
            if pos in cap:
                o.append((tid, g.size(tid), pos))
        outs[v] = o
        i = []
        for tid in set(g.op_in.get(v, ())):
            pos = g.tensors[tid]['pos']
            if pos in cap:
                i.append((tid, g.size(tid), pos))
        ins[v] = i
    remaining = {}
    for v in g.nodes:
        k = core_of_op[v]
        for tid, _, _ in ins[v]:
            remaining[(tid, k)] = remaining.get((tid, k), 0) + 1
    resident = set()
    used = [{'L1': 0, 'UB': 0} for _ in range(K)]
    pipe_free = [[0.0] * 4 for _ in range(K)]
    finish = {}
    ready_time = {}
    npred = {v: len(g.preds[v]) for v in g.nodes}
    ready = [[] for _ in range(K)]          # 升序列表，键 (-rank, op)
    for v in g.nodes:
        if npred[v] == 0:
            ready_time[v] = 0.0
            bisect.insort(ready[core_of_op[v]], (-rank[v], v))
    orders = [[] for _ in range(K)]

    def delta_live(v, k):
        alloc = {'L1': 0, 'UB': 0}
        freed = 0
        bufs = set()
        for tid, size, pos in outs[v]:
            alloc[pos] += size
            bufs.add(pos)
        for tid, size, pos in ins[v]:
            if (tid, k) not in resident:
                alloc[pos] += size
                bufs.add(pos)
            if remaining[(tid, k)] == 1:
                freed += size
                bufs.add(pos)
        c = cap['UB'] if bufs == {'UB'} else cap['L1']
        return alloc, alloc['L1'] + alloc['UB'] - freed, c

    def pick(k):
        pool = ready[k][:TOP_CANDIDATES]
        if not pool:
            return None
        pf = pipe_free[k]
        latest = max(range(4), key=lambda p: (pf[p], -p))
        best_feasible = None
        best_fallback = None
        for _, v in pool:
            alloc, dl, c = delta_live(v, k)
            if best_fallback is None or (dl, v) < best_fallback[:2]:
                best_fallback = (dl, v)
            if (used[k]['L1'] + alloc['L1'] > limit['L1']
                    or used[k]['UB'] + alloc['UB'] > limit['UB']):
                continue
            p = PIPE_INDEX[g.pipe(v)]
            score = rank[v] - mu * dl / c + (nu if p != latest else 0.0)
            if noise:
                score += noise * gumbel[v]
            if best_feasible is None or (score, -v) > best_feasible[:2]:
                best_feasible = (score, -v, v)
        v = best_feasible[2] if best_feasible else best_fallback[1]
        start = max(ready_time[v], pf[PIPE_INDEX[g.pipe(v)]])
        return (start, k, v)

    cand = [None] * K
    dirty = set(range(K))
    done = 0
    n = len(g.nodes)
    while done < n:
        for k in dirty:
            cand[k] = pick(k)
        dirty.clear()
        best = None
        for k in range(K):
            c = cand[k]
            if c is not None and (best is None or c[:2] < best[:2]):
                best = c
        start, k, v = best
        # 提交
        key = (-rank[v], v)
        lst = ready[k]
        del lst[bisect.bisect_left(lst, key)]
        end = start + max(1, g.cycles(v))
        finish[v] = end
        pipe_free[k][PIPE_INDEX[g.pipe(v)]] = end
        for tid, size, pos in outs[v]:
            if remaining.get((tid, k), 0) > 0:
                used[k][pos] += size
                resident.add((tid, k))
        for tid, size, pos in ins[v]:
            if (tid, k) not in resident:
                used[k][pos] += size
                resident.add((tid, k))
            remaining[(tid, k)] -= 1
            if remaining[(tid, k)] == 0:
                used[k][pos] -= size
                resident.discard((tid, k))
        orders[k].append(v)
        done += 1
        dirty.add(k)
        row = pb[v]
        for s in g.succs[v]:
            npred[s] -= 1
            ks = core_of_op[s]
            t = end + (0.0 if ks == k else delay + row.get(s, 0) / bw)
            if t > ready_time.get(s, 0.0):
                ready_time[s] = t
            if npred[s] == 0:
                bisect.insort(ready[ks], (-rank[s], s))
                dirty.add(ks)
    for k in range(K):
        pos = {v: i for i, v in enumerate(orders[k])}
        orders[k].sort(key=lambda v: (levels[v], pos[v]))
    return orders
