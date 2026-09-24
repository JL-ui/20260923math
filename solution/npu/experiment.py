"""实验驱动：算法 → 官方评估 → 可追溯记录。

每条记录字段（论文实验章节与附录直接引用）::

    experiment_id case problem num_cores algorithm variant seed
    runtime_s eval_s makespan speedup added_copy_bytes cache_hit_rate
    feasible n_subgraphs plan_path error
"""

from __future__ import annotations

import json
import os
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


_LARGE_P1_CACHE = None


def _large_p1_cases():
    """P1 端到端耗时中位数 > 600s 的用例集合（大图代理兜底的判定集）。

    从 ``results/main.csv`` 里问题 1 的候选行统计 ``eval_s`` 中位数；
    该文件不存在或用例未出现时不计入。进程内缓存一次。
    """
    global _LARGE_P1_CACHE
    if _LARGE_P1_CACHE is None:
        import csv
        import statistics
        by_case: dict = {}
        path = paths.RESULTS_DIR / 'main.csv'
        if path.is_file():
            with path.open(encoding='utf-8', newline='') as fh:
                for r in csv.DictReader(fh):
                    if r.get('problem') != '1':
                        continue
                    ev = r.get('eval_s')
                    if ev in (None, '', 'None'):
                        continue
                    by_case.setdefault(r['case'], []).append(float(ev))
        _LARGE_P1_CACHE = {c for c, vals in by_case.items()
                          if vals and statistics.median(vals) > 600}
    return _LARGE_P1_CACHE


def _proxy_fallback_portfolio(case, problem, num_cores, grid, g, seed, save_plan):
    """大图 P1 代理兜底：跳过全部候选的官方评估，只用 cap_ls 局部搜索内部的
    ``TrafficState.cost()`` 解析估计排序选 top-1，官方评估只调用一次核实。

    仅用于 ``_large_p1_cases()`` 命中的用例；正式成绩仍来自这一次官方评估。
    """
    best = None
    for i, params in enumerate(grid):
        try:
            plan, cost = algorithms.cap_ls(g, num_cores, problem, seed=seed,
                                           _return_cost=True, **params)
        except Exception:                                       # noqa: BLE001
            continue
        if best is None or cost < best[0]:
            best = (cost, i, plan)
    base = evaluate.singlecore_baseline(case)
    if best is None:
        return [{'case': case, 'problem': problem, 'eval_problem': problem,
                'num_cores': num_cores, 'algorithm': 'capls', 'variant': 'c0',
                'seed': seed, 'feasible': False, 'makespan': None,
                'speedup': None,
                'error': 'PLAN: all candidates failed to build (proxy_fallback)',
                'params': json.dumps({'proxy_fallback': True})}]
    cost, i, plan = best
    plan = evaluate.canonical_plan(plan)
    t0 = time.perf_counter()
    res = evaluate.default_cache().evaluate(problem, case, plan)
    n_sub = len(set(plan['node_to_subgraph'].values()))
    params = dict(grid[i])
    params['proxy_fallback'] = True
    rec = {'case': case, 'problem': problem, 'eval_problem': problem,
          'num_cores': num_cores, 'algorithm': 'capls', 'variant': f'c{i}',
          'seed': seed, 'runtime_s': round(time.perf_counter() - t0, 3),
          'eval_s': res.get('eval_seconds'),
          'feasible': bool(res.get('feasible')), 'makespan': res.get('makespan'),
          'added_copy_bytes': res.get('added_copy_bytes'),
          'partition_added_copy_bytes': res.get('partition_added_copy_bytes'),
          'spill_added_copy_bytes': res.get('spill_added_copy_bytes'),
          'scheduled_copy_bytes': res.get('scheduled_copy_bytes'),
          'cache_hit_rate': res.get('cache_hit_rate'), 'n_subgraphs': n_sub,
          'baseline_makespan': base.get('makespan'), 'error': res.get('error', ''),
          'is_best': True, 'params': json.dumps(params, sort_keys=True)}
    rec['speedup'] = (base['makespan'] / rec['makespan']
                      if rec['feasible'] and base.get('makespan') else None)
    if save_plan:
        path = (paths.PLAN_DIR /
               f'{case}_p{problem}_n{num_cores}_capls_best.json')
        path.write_text(json.dumps(plan, ensure_ascii=False), encoding='utf-8')
        rec['plan_path'] = str(path.relative_to(paths.ROOT))
    return [rec]


def _fasteval_portfolio(case, problem, num_cores, grid, g, seed):
    """T09 快速评估器初筛：全部候选先用 evaluate_fast 打分，只对冠军调用一次
    官方评估器核实；不等则记录到 fasteval_mismatch.csv 并返回 None（回退官方全评）。

    仅用于问题 1（P1 官方评估慢，才需要这条加速路径）；P2/P3 与最终成绩一律
    直接走官方评估器 + 缓存，不接入这里。
    """
    plans = []
    for i, params in enumerate(grid):
        try:
            plan = evaluate.canonical_plan(
                algorithms.cap_ls(g, num_cores, problem, seed=seed, **params))
        except Exception:                                       # noqa: BLE001
            plans.append(None)
            continue
        plans.append(plan)
    fast_results = []
    for plan in plans:
        if plan is None:
            fast_results.append(None)
            continue
        try:
            fast_results.append(evaluate.evaluate_fast(problem, case, plan))
        except Exception:                                       # noqa: BLE001
            fast_results.append(None)
    feasible_idx = [i for i, r in enumerate(fast_results)
                    if r and r.get('feasible')]
    if not feasible_idx:
        return None
    best_i = min(feasible_idx, key=lambda i: fast_results[i]['makespan'])
    best_plan = plans[best_i]
    official = evaluate.default_cache().evaluate(problem, case, best_plan)
    fast_best = fast_results[best_i]
    a = {k: v for k, v in official.items() if k not in ('eval_seconds', 'cached')}
    b = {k: v for k, v in fast_best.items() if k not in ('eval_seconds', 'cached')}
    if a != b:
        row = {'case': case, 'problem': problem, 'num_cores': num_cores,
              'variant': f'c{best_i}',
              'fast_makespan': fast_best.get('makespan'),
              'official_makespan': official.get('makespan'),
              'fast_feasible': fast_best.get('feasible'),
              'official_feasible': official.get('feasible')}
        path = paths.RESULTS_DIR / 'fasteval_mismatch.csv'
        write_csv([row], path.with_suffix('.tmp'))
        if path.is_file():
            old = path.read_text(encoding='utf-8').splitlines()
            new = path.with_suffix('.tmp').read_text(encoding='utf-8').splitlines()
            path.write_text('\n'.join(old + new[1:]) + '\n', encoding='utf-8')
        else:
            path.write_text(path.with_suffix('.tmp').read_text(encoding='utf-8'),
                            encoding='utf-8')
        path.with_suffix('.tmp').unlink(missing_ok=True)
        return None
    return plans, fast_results, best_i, official


def run_portfolio(case: str, problem: int, num_cores: int,
                  level: str = 'full', seed: int = 0,
                  save_plan: bool = True, eval_problems=None) -> list:
    """主算法的多起点组合：候选逐个评估，返回全部候选记录 + 最优标记。"""
    g = get_graph(case)
    n = g.n
    if problem == 1 and case in _large_p1_cases():
        # 大图 P1 代理兜底：优先于 NPU_FASTEVAL 与常规候选网格裁剪，跳过全部
        # 候选的官方评估，只用解析代价排序选 top-1 后官方核实一次。
        full_grid = algorithms.candidate_params(problem, num_cores, 'full', n_ops=n)
        return _proxy_fallback_portfolio(case, problem, num_cores, full_grid,
                                         g, seed, save_plan)
    use_fast = problem == 1 and os.environ.get('NPU_FASTEVAL') == '1'
    if level == 'auto' and problem == 1:
        level = 'fast' if (n > 12000 and not use_fast) else 'full'
    elif level == 'auto':
        level = 'full'
    grid = algorithms.candidate_params(problem, num_cores, level, n_ops=n)
    if level == 'full' and n > 6000 and problem == 1 and not use_fast:
        grid = grid[:8]          # P1 大图裁剪候选集（官方 P1 评估很慢），保证求解时间可控
    if use_fast:
        fast_out = _fasteval_portfolio(case, problem, num_cores, grid, g, seed)
        if fast_out is not None:
            plans, fast_results, best_i, official = fast_out
            out = []
            for i, (plan, fr) in enumerate(zip(plans, fast_results)):
                if plan is None or fr is None:
                    continue
                n_sub = len(set(plan['node_to_subgraph'].values()))
                base = evaluate.singlecore_baseline(case)
                res = official if i == best_i else fr
                rec = {'case': case, 'problem': problem, 'eval_problem': problem,
                      'num_cores': num_cores, 'algorithm': 'capls',
                      'variant': f'c{i}', 'seed': seed, 'runtime_s': None,
                      'eval_s': res.get('eval_seconds'),
                      'feasible': bool(res.get('feasible')),
                      'makespan': res.get('makespan'),
                      'added_copy_bytes': res.get('added_copy_bytes'),
                      'partition_added_copy_bytes': res.get('partition_added_copy_bytes'),
                      'spill_added_copy_bytes': res.get('spill_added_copy_bytes'),
                      'scheduled_copy_bytes': res.get('scheduled_copy_bytes'),
                      'cache_hit_rate': res.get('cache_hit_rate'),
                      'n_subgraphs': n_sub, 'baseline_makespan': base.get('makespan'),
                      'error': res.get('error', ''), 'is_best': i == best_i,
                      'params': json.dumps(grid[i], sort_keys=True)}
                rec['speedup'] = (base['makespan'] / rec['makespan']
                                  if rec['feasible'] and base.get('makespan')
                                  and i == best_i else None)
                out.append(rec)
            if save_plan:
                path = (paths.PLAN_DIR /
                       f'{case}_p{problem}_n{num_cores}_capls_best.json')
                path.write_text(json.dumps(plans[best_i], ensure_ascii=False),
                               encoding='utf-8')
                for r in out:
                    if r['is_best']:
                        r['plan_path'] = str(path.relative_to(paths.ROOT))
            return out
        # 官方值与快速值不等：回退为官方评估全部候选（不再使用 evaluate_fast）
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
