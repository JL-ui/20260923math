"""跨核同步层次（cross-core depth）分层与子图成形。

动机（来自对官方评估器的反向解析）
------------------------------------
Step3 对"会申请片上张量的操作"施加了**全局申请序**约束：
``allocation_order`` 是扩展序列 ``seq_ext`` 的投影，只有排在队首的申请者
才能发射。于是，一旦某个跨核 ``COPY_IN`` 排在核内序列的前部而其数据尚未
送达，**整个核**（四条 Pipe）都会被堵住，代价远大于配置里的
``cross_core_copy_delay_cycles``（500 cycle）。问题 1 的 Task 激活规则
更直接：一个 Task 必须等它的**全部**前驱 Task 完成。

因此本模块引入"跨核同步层次"

.. math::  r(v)=\\max_{u\\to v}\\bigl(r(u)+\\mathbb 1[c(u)\\ne c(v)]\\bigr),
           \\quad r(v)=0 \\text{ 若 } v \\text{ 无前驱}

并定义 **子图 = (核心 c, 层次 r)**。这一定义有三条可证性质：

P1. r 沿依赖边非降，跨核边必严格 +1 ⟹ 按 (r, c) 编号即为子图商图的
    一个拓扑序，硬约束"子图依赖无环 + 同核顺序合法"自动满足；
P2. **同一层次内不存在跨核边**（否则该边的终点层次至少为 r+1），
    故同层的各核子图完全独立、可并行；
P3. 每个核上"需要远端数据"的算子被自动推迟到更高层次，核内先执行完全部
    本地就绪的工作，最大程度掩盖跨核同步延迟。

问题 1 中层次数直接决定 Task 串行级数（每级额外付出一次
``task_cross_core_wait_cycles``），因此层次数也是分配阶段的优化目标之一。
"""

from __future__ import annotations

from collections import defaultdict

from . import graphlib


def cross_core_levels(g: graphlib.Graph, core_of_op: dict) -> dict:
    """计算 r(v)：沿依赖路径累计的换核次数。"""
    level = {}
    for v in g.topo:
        cv = core_of_op[v]
        best = 0
        for p in g.preds[v]:
            cand = level[p] + (1 if core_of_op[p] != cv else 0)
            if cand > best:
                best = cand
        level[v] = best
    return level


def level_stats(levels: dict, core_of_op: dict, num_cores: int):
    per = defaultdict(int)
    for v, r in levels.items():
        per[(core_of_op[v], r)] += 1
    depth = max(levels.values()) + 1 if levels else 1
    return depth, per


def build_subgraphs(g: graphlib.Graph, core_of_op: dict, num_cores: int,
                    rank: dict, max_ops: int | None = None,
                    max_work: float | None = None, levels: dict | None = None):
    """按 (核心, 层次) 成形子图，必要时再按规模沿 σ 序切开。

    ``levels``：显式传入非 ASAP 层指派（T12 的 alap_fill / compress 等）；
    缺省时按 ``cross_core_levels``（ASAP）计算。任何传入的层指派都必须满足
    单调性（``levels.check_monotone``），否则不能保证子图商图无环等硬约束。

    返回 ``(mapping, core_schedules)``：``mapping`` 是 op→sgid，
    ``core_schedules[k]`` 是核 k 上按 sgid 升序的子图列表。
    子图编号顺序 = (层次 r, 核心 c, 组内切片序)，满足性质 P1。
    """
    from . import levels as levels_mod
    levels = levels if levels is not None else cross_core_levels(g, core_of_op)
    levels_mod.check_monotone(g, core_of_op, levels)
    buckets = defaultdict(list)
    for v in g.nodes:
        buckets[(levels[v], core_of_op[v])].append(v)

    mapping = {}
    schedules = [[] for _ in range(num_cores)]
    sid = 0
    for key in sorted(buckets):
        r, k = key
        members = sorted(buckets[key], key=lambda v: rank[v])
        pieces = [members]
        if (max_ops and len(members) > max_ops) or max_work:
            pieces = []
            cur, cur_ops, cur_w = [], 0, 0.0
            for v in members:
                cur.append(v)
                cur_ops += 1
                cur_w += g.cycles(v)
                if ((max_ops and cur_ops >= max_ops)
                        or (max_work and cur_w >= max_work)):
                    pieces.append(cur)
                    cur, cur_ops, cur_w = [], 0, 0.0
            if cur:
                pieces.append(cur)
        for piece in pieces:
            for v in piece:
                mapping[v] = sid
            schedules[k].append(sid)
            sid += 1
    return mapping, schedules, levels
