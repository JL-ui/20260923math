"""单调层指派：ASAP 之外的合法跨核同步层次。

任何满足
    同核边 u→v：l(v) ≥ l(u)，   跨核边 u→v：l(v) ≥ l(u) + 1
的层指派 l，按 (l, 核) 等价类成形子图、按 (l, 核) 递增编号，都保持
``stratify.build_subgraphs`` 的全部可行性性质（ASAP 层 r(v) 是其中逐点最小的一个）。
本模块在这一族里再给两种构造：把算子推迟到负载更轻的层（ALAP 填充），以及
把计算量很小的层并入前一层（层压缩）。
"""

from __future__ import annotations

from collections import defaultdict

from . import stratify


def asap(g, core_of_op) -> dict:
    return stratify.cross_core_levels(g, core_of_op)


def check_monotone(g, core_of_op, l) -> None:
    for u in g.nodes:
        cu = core_of_op[u]
        lu = l[u]
        for v in g.succs[u]:
            need = lu + (1 if core_of_op[v] != cu else 0)
            if l[v] < need:
                raise ValueError(
                    'non-monotone level assignment: {} (core {}, l={}) -> {} '
                    '(core {}, l={})'.format(u, cu, lu, v, core_of_op[v], l[v]))


def alap_fill(g, core_of_op) -> dict:
    """逆拓扑序把每个算子放到 [ASAP, 上界] 内本核负载最轻的层（并列取最小层）。"""
    l = asap(g, core_of_op)
    top = max(l.values(), default=0)
    load = defaultdict(int)
    for v in g.nodes:
        load[(core_of_op[v], l[v])] += g.cycles(v)
    for v in reversed(g.topo):
        k = core_of_op[v]
        upper = top
        for s in g.succs[v]:
            cand = l[s] - (1 if core_of_op[s] != k else 0)
            if cand < upper:
                upper = cand
        w = g.cycles(v)
        load[(k, l[v])] -= w
        best = l[v]
        for lv in range(l[v], upper + 1):
            if load[(k, lv)] < load[(k, best)]:
                best = lv
        l[v] = best
        load[(k, best)] += w
    check_monotone(g, core_of_op, l)
    return l


def compress(g, core_of_op, l, frac=0.05) -> dict:
    """把总周期低于 frac × 平均层周期的层内可前移算子并入前一层，再紧凑重编号。"""
    l = dict(l)
    top = max(l.values(), default=0)
    work = defaultdict(int)
    for v in g.nodes:
        work[l[v]] += g.cycles(v)
    mean = sum(work[lv] for lv in range(top + 1)) / (top + 1)
    by_level = defaultdict(list)
    for v in g.topo:
        by_level[l[v]].append(v)
    for lv in range(1, top + 1):
        if work[lv] >= frac * mean:
            continue
        for v in by_level[lv]:
            k = core_of_op[v]
            need = 0
            for u in g.preds[v]:
                cand = l[u] + (1 if core_of_op[u] != k else 0)
                if cand > need:
                    need = cand
            if need <= lv - 1:
                l[v] = lv - 1
    remap = {old: new for new, old in enumerate(sorted(set(l.values())))}
    l = {v: remap[x] for v, x in l.items()}
    check_monotone(g, core_of_op, l)
    return l


def assign_levels(g, core_of_op, mode='asap') -> dict:
    if mode == 'asap':
        return asap(g, core_of_op)
    if mode == 'alap_fill':
        return alap_fill(g, core_of_op)
    if mode == 'compress':
        return compress(g, core_of_op, asap(g, core_of_op))
    if mode == 'alap_compress':
        return compress(g, core_of_op, alap_fill(g, core_of_op))
    raise ValueError(f'unknown level_mode: {mode}')
