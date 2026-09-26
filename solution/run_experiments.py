# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Sonnet 5（型号 claude-sonnet-5）、Claude Opus 5.5（型号 claude-opus-5-5）
# 开发机构：Anthropic 公司
# 版本发布日期：Claude Sonnet 5 为 2026-06-30，Claude Opus 5.5 为 2026-09-22
"""实验总驱动。

    python solution/run_experiments.py --stage main      --jobs 14
    python solution/run_experiments.py --stage baseline  --jobs 14
    python solution/run_experiments.py --stage ablation  --jobs 14
    python solution/run_experiments.py --stage n1        --jobs 14

所有记录追加写入 ``results/<stage>.csv``，字段见 ``npu.experiment``。
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from npu import algorithms, evaluate, experiment, paths, variants  # noqa: E402

CORES = (2, 3, 4, 5)
PROBLEMS = (1, 2, 3)


# --------------------------------------------------------------------------
# 任务
# --------------------------------------------------------------------------

def task_main(case, problem, ncores, level):
    recs = experiment.run_portfolio(case, problem, ncores, level=level,
                                    save_plan=True)
    evaluate.default_cache().flush()
    return recs


def task_baseline(case, problem, ncores, algos):
    out = []
    for algo in algos:
        out.extend(experiment.run_one(case, problem, ncores, algo))
    return out


def task_n1(case, problem):
    """N=1 参考点：整图单子图方案在该问题下的官方评估。"""
    recs = experiment.run_one(case, problem, 1, 'single', save_plan=False)
    evaluate.default_cache().flush()
    return recs


def task_p3(case, ncores):
    """问题 3 对照：同一方案分别在"无 L2"(problem 2) 与"只读 Cache"(problem 3)
    下评估，隔离出 L2 的净收益。"""
    if ncores == 1:
        recs = []
        for ep in (2, 3):
            recs.extend(experiment.run_one(case, 3, 1, 'single',
                                           eval_problems=[ep]))
    else:
        recs = experiment.run_portfolio(case, 3, ncores, level='auto',
                                        save_plan=True, eval_problems=[2, 3])
    evaluate.default_cache().flush()
    return recs


ABLATIONS = variants.ABLATIONS


SENSITIVITY = {
    'bandwidth': [15, 30, 60, 120, 240],
    'L1': [131072, 262144, 524288, 1048576, 2097152],
    'UB': [32768, 65536, 131072, 262144, 524288],
    'cache_capacity_bytes': [65536, 262144, 1048576, 4194304, 16777216],
    'cache_bandwidth_bytes_per_cycle': [60, 125, 250, 500, 1000],
    'cross_core_copy_delay_cycles': [0, 125, 500, 2000, 8000],
    'task_cross_core_wait_cycles': [0, 250, 1000, 4000, 16000],
}
SENSITIVITY_PROBLEM = {
    'cache_capacity_bytes': 3, 'cache_bandwidth_bytes_per_cycle': 3,
    'cross_core_copy_delay_cycles': 2, 'task_cross_core_wait_cycles': 1,
}


def task_sensitivity(case, knob, value, ncores):
    """研究性敏感性实验：修改单个硬件参数，重新优化并评估。

    **不用于正式成绩**；报告量为 Makespan 相对该用例默认配置的倍数。
    """
    problem = SENSITIVITY_PROBLEM.get(knob, 2)
    default = paths.official_config()[knob]
    paths.clear_config_override()
    if value != default:
        paths.set_config_override(**{knob: value})
    g = experiment.get_graph(case)
    t0 = time.perf_counter()
    best = None
    for params in algorithms.candidate_params(problem, ncores, 'fast'):
        try:
            plan = evaluate.canonical_plan(
                algorithms.cap_ls(g, ncores, problem, **params))
            res = evaluate.default_cache().evaluate(problem, case, plan)
        except Exception:                                       # noqa: BLE001
            continue
        if res.get('feasible') and (best is None
                                    or res['makespan'] < best['makespan']):
            best = res
    rec = {'case': case, 'knob': knob, 'value': value, 'is_default': value == default,
           'problem': problem, 'num_cores': ncores, 'sensitivity': True,
           'runtime_s': round(time.perf_counter() - t0, 3),
           'feasible': bool(best),
           'makespan': best['makespan'] if best else None,
           'added_copy_bytes': best.get('added_copy_bytes') if best else None,
           'cache_hit_rate': best.get('cache_hit_rate') if best else None}
    evaluate.default_cache().flush()
    paths.clear_config_override()
    return [rec]


GRANULARITY_BETAS = (0.03, 0.06, 0.12, 0.25, 0.5, 1.0, 2.0)


def task_granularity(case, problem, ncores):
    """切图粒度敏感性：只变 β（单块计算量上限 = β·W/N），其余固定。"""
    base = evaluate.singlecore_baseline(case)
    out = []
    for beta in GRANULARITY_BETAS:
        recs = experiment.run_one(case, problem, ncores, 'capls',
                                  {'block_cap': beta}, variant=str(beta))
        for r in recs:
            r['baseline_makespan'] = base.get('makespan')
        out.extend(recs)
    evaluate.default_cache().flush()
    return out


def task_ablation(case, problem, ncores):
    g = experiment.get_graph(case)
    base = evaluate.singlecore_baseline(case)
    out = []
    for name in ABLATIONS:
        t0 = time.perf_counter()
        try:
            plan = variants.ablation_plan(g, name, problem, ncores)
            runtime = time.perf_counter() - t0
            res = evaluate.default_cache().evaluate(problem, case, plan)
        except Exception as exc:                                # noqa: BLE001
            out.append({'case': case, 'problem': problem, 'num_cores': ncores,
                        'algorithm': 'ablation', 'variant': name,
                        'feasible': False,
                        'error': '{}: {}'.format(type(exc).__name__, str(exc)[:200])})
            continue
        rec = {'case': case, 'problem': problem, 'eval_problem': problem,
               'num_cores': ncores, 'algorithm': 'ablation', 'variant': name,
               'runtime_s': round(runtime, 3), 'eval_s': res.get('eval_seconds'),
               'feasible': bool(res.get('feasible')),
               'makespan': res.get('makespan'),
               'added_copy_bytes': res.get('added_copy_bytes'),
               'cache_hit_rate': res.get('cache_hit_rate'),
               'baseline_makespan': base.get('makespan'),
               'n_subgraphs': len(set(plan['node_to_subgraph'].values())),
               'error': res.get('error', '')}
        rec['speedup'] = (base['makespan'] / rec['makespan']
                          if rec['feasible'] and base.get('makespan') else None)
        out.append(rec)
    evaluate.default_cache().flush()
    return out


def task_ablation2(case, problem, ncores):
    """T16：以 c2 参数为基准的逐项消融（每个变体一个官方评估，走缓存）。"""
    g = experiment.get_graph(case)
    base = evaluate.singlecore_baseline(case)
    out = []
    for name in variants.ABLATION2:
        if problem == 1 and name in variants.ABLATION2_P23_ONLY:
            continue
        t0 = time.perf_counter()
        try:
            plan = evaluate.canonical_plan(algorithms.cap_ls(
                g, ncores, problem, **variants.ablation2_params(name)))
            runtime = time.perf_counter() - t0
            res = evaluate.default_cache().evaluate(problem, case, plan)
        except Exception as exc:                                # noqa: BLE001
            out.append({'case': case, 'problem': problem, 'num_cores': ncores,
                        'algorithm': 'ablation2', 'variant': name,
                        'feasible': False,
                        'error': '{}: {}'.format(type(exc).__name__, str(exc)[:200])})
            continue
        rec = {'case': case, 'problem': problem, 'eval_problem': problem,
               'num_cores': ncores, 'algorithm': 'ablation2', 'variant': name,
               'runtime_s': round(runtime, 3), 'eval_s': res.get('eval_seconds'),
               'feasible': bool(res.get('feasible')),
               'makespan': res.get('makespan'),
               'added_copy_bytes': res.get('added_copy_bytes'),
               'cache_hit_rate': res.get('cache_hit_rate'),
               'baseline_makespan': base.get('makespan'),
               'n_subgraphs': len(set(plan['node_to_subgraph'].values())),
               'error': res.get('error', '')}
        rec['speedup'] = (base['makespan'] / rec['makespan']
                          if rec['feasible'] and base.get('makespan') else None)
        out.append(rec)
    evaluate.default_cache().flush()
    return out


# --------------------------------------------------------------------------
# 驱动
# --------------------------------------------------------------------------

def drive(jobs, tasks, out_csv, label):
    t0 = time.time()
    rows, done = [], 0
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        futures = [ex.submit(fn, *args) for fn, args in tasks]
        for fut in as_completed(futures):
            try:
                recs = fut.result()
            except Exception as exc:                            # noqa: BLE001
                print('TASK FAILED:', type(exc).__name__, str(exc)[:300], flush=True)
                continue
            rows.extend(recs)
            done += 1
            if done % 10 == 0 or done == len(futures):
                print('[{}] {}/{} tasks  {:.1f}s  rows={}'.format(
                    label, done, len(futures), time.time() - t0, len(rows)),
                    flush=True)
    experiment.write_csv(rows, out_csv)
    print('wrote', out_csv, len(rows), 'rows in {:.1f}s'.format(time.time() - t0))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--stage', required=True,
                    choices=['main', 'baseline', 'ablation', 'ablation2', 'n1', 'p3',
                             'granularity', 'sensitivity'])
    ap.add_argument('--jobs', type=int, default=14)
    ap.add_argument('--cases', nargs='*')
    ap.add_argument('--cores', nargs='*', type=int, default=list(CORES))
    ap.add_argument('--problems', nargs='*', type=int, default=list(PROBLEMS))
    ap.add_argument('--level', default='auto')
    ap.add_argument('--algos', nargs='*',
                    default=['random', 'topo', 'balance', 'comm'])
    ap.add_argument('--out')
    args = ap.parse_args()
    cases = args.cases or paths.all_cases()

    tasks = []
    if args.stage == 'main':
        for c in cases:
            for p in args.problems:
                for n in args.cores:
                    tasks.append((task_main, (c, p, n, args.level)))
    elif args.stage == 'baseline':
        for c in cases:
            for p in args.problems:
                for n in args.cores:
                    tasks.append((task_baseline, (c, p, n, tuple(args.algos))))
    elif args.stage == 'ablation':
        for c in cases:
            for p in args.problems:
                for n in args.cores:
                    tasks.append((task_ablation, (c, p, n)))
    elif args.stage == 'ablation2':
        for c in cases:
            for p in args.problems:
                for n in args.cores:
                    tasks.append((task_ablation2, (c, p, n)))
    elif args.stage == 'n1':
        for c in cases:
            for p in args.problems:
                tasks.append((task_n1, (c, p)))
    elif args.stage == 'p3':
        for c in cases:
            for n in ([1] + list(args.cores)):
                tasks.append((task_p3, (c, n)))
    elif args.stage == 'granularity':
        for c in cases:
            for p in args.problems:
                for n in args.cores:
                    tasks.append((task_granularity, (c, p, n)))
    elif args.stage == 'sensitivity':
        n = args.cores[0] if args.cores else 4
        for c in cases:
            for knob, values in SENSITIVITY.items():
                for v in values:
                    tasks.append((task_sensitivity, (c, knob, v, n)))

    out = Path(args.out) if args.out else paths.RESULTS_DIR / f'{args.stage}.csv'
    drive(args.jobs, tasks, out, args.stage)


if __name__ == '__main__':
    main()
