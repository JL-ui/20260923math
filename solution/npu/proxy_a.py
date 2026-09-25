"""场景 A（问题 1）的 Task 级事件模拟代理。

由 ``solution/validate_model.py`` 原样迁出（T14），行为不变。
"""

from __future__ import annotations


def estimate_scene_a_from_plan(g, mapping, schedules, cfg):
    """场景 A 的 Task 级事件模拟，直接基于最终方案（与评估器规则同构）。

    Task 时长用 max(M, V, (cin+cout)/bw) 估计；激活规则、同核切换与跨核等待
    与 `multicore_cut_evaluate_problem_1.task_release_time` 一一对应。
    """
    bw = cfg['bandwidth']
    same_wait = cfg['task_same_core_wait_cycles']
    cross_wait = cfg['task_cross_core_wait_cycles']
    core_of_sub = {}
    for k, order in enumerate(schedules):
        for sg in order:
            core_of_sub[sg] = k
    subs = sorted(core_of_sub)
    mv = {s: [0, 0] for s in subs}
    for v, sg in mapping.items():
        if g.pipe(v) == 'PIPE_M':
            mv[sg][0] += g.cycles(v)
        elif g.pipe(v) == 'PIPE_V':
            mv[sg][1] += g.cycles(v)
    cin = {s: 0 for s in subs}
    cout = {s: 0 for s in subs}
    preds = {s: set() for s in subs}
    for tid in g.tensors:
        ps, cs = g.producers[tid], g.consumers[tid]
        if not ps and not cs:
            continue
        size = g.size(tid)
        psub = {mapping[o] for o in ps}
        csub = {mapping[o] for o in cs}
        is_out = tid in g.graph_output_tensor
        for s in csub - psub:
            cin[s] += size
        for s in psub:
            if is_out or not csub or (csub - {s}):
                cout[s] += size
        for a in psub:
            for b in csub:
                if a != b:
                    preds[b].add(a)
    # 子图 id 经 canonical_plan 重编号后是"按核分组"的，不再是全局拓扑序；
    # 因此必须按"每核队首 + 前驱全完成"的真实激活规则推进，而不能按 id 升序。
    end, core_time, done = {}, {}, set()
    ptr = [0] * len(schedules)
    makespan = 0.0
    remaining = len(subs)
    while remaining:
        progressed = False
        for k, order in enumerate(schedules):
            if ptr[k] >= len(order):
                continue
            sg = order[ptr[k]]
            if any(d not in done for d in preds[sg]):
                continue
            dur = max(mv[sg][0], mv[sg][1], (cin[sg] + cout[sg]) / bw, 1.0)
            start = core_time.get(k)
            start = 0.0 if start is None else start + same_wait
            for pdep in preds[sg]:
                start = max(start, end[pdep] + (cross_wait
                                                if core_of_sub[pdep] != k else 0))
            end[sg] = start + dur
            core_time[k] = end[sg]
            done.add(sg)
            ptr[k] += 1
            remaining -= 1
            makespan = max(makespan, end[sg])
            progressed = True
        if not progressed:
            raise RuntimeError('scene A estimate: task graph deadlock')
    total_bytes = sum(cin.values()) + sum(cout.values())
    return max(makespan, total_bytes / bw)
