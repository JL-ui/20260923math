"""实验驱动：算法 → 官方评估 → 可追溯记录。

每条记录字段（论文实验章节与附录直接引用）::

    experiment_id case problem num_cores algorithm variant seed
    runtime_s eval_s makespan speedup added_copy_bytes cache_hit_rate
    feasible n_subgraphs plan_path error
"""

from __future__ import annotations

import json
import time
import traceback
from pathlib import Path

from . import algorithms, evaluate, graphlib, paths

_GRAPH = {}


def get_graph(case: str) -> graphlib.Graph:
    if case not in _GRAPH:
        _GRAPH[case] = graphlib.load_graph(paths.case_path(case))
    return _GRAPH[case]


def singlecore_plan(g) -> dict:
    return evaluate.make_plan({v: 0 for v in g.nodes}, [[0]])


def run_one(case: str, problem: int, num_cores: int, algorithm: str,
            params: dict | None = None, seed: int = 0,
            save_plan: bool = False, variant: str = '',
            eval_problems=None) -> list:
    """跑一次算法并用官方评估器打分，返回记录列表（可能含多个评估视角）。"""
    params = dict(params or {})
    g = get_graph(case)
    base = evaluate.singlecore_baseline(case)
    eval_problems = eval_problems or [problem]
    t0 = time.perf_counter()
    try:
        if num_cores == 1 and algorithm not in ('random',):
            plan = singlecore_plan(g)
        else:
            plan = algorithms.ALGORITHMS[algorithm](
                g, num_cores, problem, seed=seed, **params)
        runtime = time.perf_counter() - t0
    except Exception as exc:                                   # noqa: BLE001
        return [{
            'case': case, 'problem': problem, 'num_cores': num_cores,
            'algorithm': algorithm, 'variant': variant, 'seed': seed,
            'runtime_s': round(time.perf_counter() - t0, 3),
            'feasible': False, 'makespan': None, 'speedup': None,
            'error': 'PLAN {}: {}'.format(type(exc).__name__, str(exc)[:200]),
            'traceback': traceback.format_exc()[-600:],
        }]

    plan = evaluate.canonical_plan(plan)
    n_sub = len(set(plan['node_to_subgraph'].values()))
    records = []
    cache = evaluate.default_cache()
    for ep in eval_problems:
        res = cache.evaluate(ep, case, plan)
        rec = {
            'case': case, 'problem': problem, 'eval_problem': ep,
            'num_cores': num_cores, 'algorithm': algorithm,
            'variant': variant, 'seed': seed,
            'runtime_s': round(runtime, 3),
            'eval_s': res.get('eval_seconds'),
            'feasible': bool(res.get('feasible')),
            'makespan': res.get('makespan'),
            'added_copy_bytes': res.get('added_copy_bytes'),
            'partition_added_copy_bytes': res.get('partition_added_copy_bytes'),
            'spill_added_copy_bytes': res.get('spill_added_copy_bytes'),
            'scheduled_copy_bytes': res.get('scheduled_copy_bytes'),
            'cache_hit_rate': res.get('cache_hit_rate'),
            'cache_hit_bytes': res.get('cache_hit_bytes'),
            'n_subgraphs': n_sub,
            'baseline_makespan': base.get('makespan'),
            'error': res.get('error', ''),
        }
        if rec['feasible'] and base.get('makespan'):
            rec['speedup'] = base['makespan'] / rec['makespan']
        else:
            rec['speedup'] = None
        records.append(rec)
    if save_plan:
        path = (paths.PLAN_DIR /
                f'{case}_p{problem}_n{num_cores}_{algorithm}{variant}.json')
        path.write_text(json.dumps(plan, ensure_ascii=False), encoding='utf-8')
        for rec in records:
            rec['plan_path'] = str(path.relative_to(paths.ROOT))
    return records


def run_portfolio(case: str, problem: int, num_cores: int,
                  level: str = 'full', seed: int = 0,
                  save_plan: bool = True, eval_problems=None) -> list:
    """主算法的多起点组合：候选逐个评估，返回全部候选记录 + 最优标记。"""
    n = get_graph(case).n
    if level == 'auto' and problem == 1:
        level = 'fast' if n > 12000 else 'full'
    elif level == 'auto':
        level = 'full'
    grid = algorithms.candidate_params(problem, num_cores, level)
    if level == 'full' and n > 6000 and problem == 1:
        grid = grid[:8]          # P1 大图裁剪候选集（官方 P1 评估很慢），保证求解时间可控
    out = []
    for i, params in enumerate(grid):
        recs = run_one(case, problem, num_cores, 'capls', params, seed=seed,
                       variant=f'c{i}', eval_problems=[problem])
        for rec in recs:
            rec['params'] = json.dumps(params, sort_keys=True)
        out.extend(recs)
    feasible = [r for r in out if r['feasible']]
    if not feasible:
        return out
    best = min(feasible, key=lambda r: r['makespan'])
    best_params = grid[int(best['variant'][1:])]
    for r in out:
        r['is_best'] = (r is best)
    if save_plan or (eval_problems and len(eval_problems) > 1):
        extra = run_one(case, problem, num_cores, 'capls', best_params,
                        seed=seed, save_plan=save_plan, variant='_best',
                        eval_problems=eval_problems or [problem])
        for r in extra:
            r['params'] = json.dumps(best_params, sort_keys=True)
            r['is_best'] = True
        out.extend(extra)
    return out


def write_csv(records: list, path: Path):
    import csv
    if not records:
        return
    keys = []
    for rec in records:
        for k in rec:
            if k not in keys and k != 'traceback':
                keys.append(k)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=keys, extrasaction='ignore')
        writer.writeheader()
        for rec in records:
            writer.writerow(rec)
