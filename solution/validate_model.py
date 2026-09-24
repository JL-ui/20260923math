"""模型检验：解析代价模型 F 与官方评估器 Makespan 的一致性。

对每个用例的全部候选方案，同时记录
  * 解析估计（场景 A 用 Task 级事件模拟，场景 B 用每核 Pipe 负载 + 同步深度）
  * 官方评估器给出的 Makespan
然后报告 Pearson / Spearman 相关系数与"用解析模型选出的候选 vs 真最优候选"
的 Makespan 相对差距（即代理模型的选择损失）。

    python solution/validate_model.py --jobs 8 --cases ... -o results/model_validation.csv
"""

from __future__ import annotations

import argparse
import math
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from npu import (algorithms, assign, evaluate, experiment,      # noqa: E402
                 partition, paths, stratify)


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


def _estimate(g, bs, core, num_cores, problem, cfg, plan):
    if problem == 1:
        mapping = {int(k): int(v) for k, v in plan['node_to_subgraph'].items()}
        return estimate_scene_a_from_plan(g, mapping, plan['core_schedules'], cfg)
    est, _ = assign.estimate_scene_b(
        bs, core, num_cores, cfg,
        cache_capacity=cfg['cache_capacity_bytes'] if problem == 3 else 0)
    return est


def task(case, problem, ncores):
    cfg = paths.official_config()
    g = experiment.get_graph(case)
    rows = []
    for idx, params in enumerate(algorithms.candidate_params(problem, ncores, 'full')):
        params = dict(params)
        active = min(ncores, params.get('cores_used') or ncores)
        try:
            bs = partition.make_blocks(
                g, max(1, active), block_cap=params.get('block_cap', 0.35),
                use_affinity=params.get('use_affinity', True))
            if active <= 1:
                core = [0] * bs.m
            else:
                init = params.get('init', 'lpt')
                if init == 'rr':
                    core = assign.round_robin_assign(bs, active)
                elif init == 'contig':
                    core = assign.contiguous_assign(bs, active)
                else:
                    core = assign.lpt_assign(
                        bs, active, comm_weight=params.get('comm_weight', 0.0))
                state = algorithms.TrafficState(
                    bs, core, active, cfg,
                    sync_penalty=params.get(
                        'sync_weight',
                        cfg['task_cross_core_wait_cycles'] if problem == 1
                        else cfg['cross_core_copy_delay_cycles']),
                    cache_capacity=(cfg['cache_capacity_bytes']
                                    if problem == 3 else 0))
                algorithms._local_search(bs, state, active, problem == 3)
                core = state.core
            if params.get('subgraph_mode') == 'block':
                plan = algorithms._plan_blocks_as_subgraphs(bs, core, ncores)
            else:
                plan = algorithms._plan_from_core_map(
                    g, bs, core, ncores, max_ops=params.get('max_ops'))
            plan = evaluate.canonical_plan(plan)
            est = _estimate(g, bs, core, active, problem, cfg, plan)
            res = evaluate.default_cache().evaluate(problem, case, plan)
        except Exception as exc:                                # noqa: BLE001
            rows.append({'case': case, 'problem': problem, 'num_cores': ncores,
                         'variant': idx, 'feasible': False,
                         'error': type(exc).__name__})
            continue
        rows.append({'case': case, 'problem': problem, 'num_cores': ncores,
                     'variant': idx, 'feasible': bool(res.get('feasible')),
                     'estimate': round(est, 1),
                     'makespan': res.get('makespan'),
                     'error': res.get('error', '')})
    evaluate.default_cache().flush()
    return rows


def _rank(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    for pos, i in enumerate(order):
        r[i] = pos
    return r


def _corr(xs, ys):
    n = len(xs)
    if n < 3:
        return float('nan')
    mx, my = sum(xs) / n, sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return float('nan')
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--jobs', type=int, default=8)
    ap.add_argument('--cases', nargs='*')
    ap.add_argument('--cores', type=int, default=4)
    ap.add_argument('-o', '--output', default='results/model_validation.csv')
    args = ap.parse_args()
    cases = args.cases or paths.all_cases()[:40]
    tasks = [(c, p, args.cores) for c in cases for p in (1, 2, 3)]
    rows = []
    with ProcessPoolExecutor(max_workers=args.jobs) as ex:
        futs = [ex.submit(task, *t) for t in tasks]
        for i, f in enumerate(as_completed(futs), 1):
            rows.extend(f.result())
            if i % 20 == 0:
                print(f'{i}/{len(futs)}', flush=True)
    experiment.write_csv(rows, Path(args.output))

    print('\n=== 模型检验 ===')
    for problem in (1, 2, 3):
        ok = [r for r in rows if r['problem'] == problem and r.get('feasible')
              and r.get('estimate') and r.get('makespan')]
        if len(ok) < 5:
            continue
        lx = [math.log(r['estimate']) for r in ok]
        ly = [math.log(r['makespan']) for r in ok]
        pear = _corr(lx, ly)
        spear = _corr(_rank(lx), _rank(ly))
        # 选择损失：按解析模型选 vs 按真值选
        bycase = {}
        for r in ok:
            bycase.setdefault((r['case'], r['num_cores']), []).append(r)
        loss = []
        for group in bycase.values():
            pick = min(group, key=lambda r: r['estimate'])
            best = min(group, key=lambda r: r['makespan'])
            loss.append(pick['makespan'] / best['makespan'] - 1)
        print('问题 {}: n={} log-Pearson={:.3f} Spearman={:.3f} '
              '代理选择损失 中位数={:.2%} 均值={:.2%}'.format(
                  problem, len(ok), pear, spear,
                  sorted(loss)[len(loss) // 2], sum(loss) / len(loss)))


if __name__ == '__main__':
    main()
