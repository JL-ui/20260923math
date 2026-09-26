"""单用例求解入口：生成官方格式的多核切图与调度方案。

    python solution/solve.py data/case_001.json --problem 2 --cores 4 \
           -o data/case_001_multicore_res.json

默认运行与主实验相同的标准求解流程（experiment.run_portfolio：候选网格 +
问题一模拟退火 / 问题二、三优先级采样，由官方评估器择优），并与整图单核方案、
`results/main.csv` 中同一用例更少核数下的已有方案（若存在，补空核后比较）
一起取 Makespan 最小者（即论文 5.4 节 S4 中的两类兜底候选），保证单次求解
本身也不低于单核、不差于更少核数下已经跑出的结果。加 `--grid-only` 只在
候选网格中择优、不做上述比较（旧行为）；加 `--fast` 只跑单个默认配置，
不调用评估器。
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from npu import algorithms, evaluate, experiment, graphlib, paths  # noqa: E402


def _embed(plan, extra_cores):
    return evaluate.canonical_plan({
        'node_to_subgraph': plan['node_to_subgraph'],
        'core_schedules': [list(o) for o in plan['core_schedules']]
        + [[] for _ in range(extra_cores)]})


def _mono_candidates(g, case, problem, cores):
    """单调性修复的免费候选：整图单核、以及同一用例更少核数下已有的标准流程方案。

    均只在末尾追加空核，不改变已占用核心的调度，因此 Makespan 与来源方案相同；
    找不到 `results/main.csv`（例如新用例，没有先跑过批量实验）时静默跳过后者。
    """
    cands = [('single', evaluate.canonical_plan(
        evaluate.make_plan({v: 0 for v in g.nodes},
                           [[0]] + [[] for _ in range(cores - 1)])))]
    main_csv = paths.RESULTS_DIR / 'main.csv'
    if not main_csv.is_file():
        return cands
    with main_csv.open(encoding='utf-8', newline='') as f:
        for r in csv.DictReader(f):
            if (r.get('case') != case or int(float(r.get('problem', -1))) != problem
                    or r.get('variant') != '_best' or r.get('feasible') != 'True'):
                continue
            n = int(float(r['num_cores']))
            if n >= cores or not r.get('plan_path'):
                continue
            src = paths.ROOT / r['plan_path'].replace('\\', '/')
            if not src.is_file():
                continue
            plan = json.loads(src.read_text(encoding='utf-8'))
            cands.append((f'embed_n{n}', _embed(plan, cores - n)))
    return cands


def solve_standard(case_path, problem: int, cores: int, seed: int = 0,
                   verbose: bool = True):
    """标准求解流程：与 results/main.csv 同一入口，论文主结果即此口径。"""
    case_path = Path(case_path)
    if case_path.resolve().parent != paths.case_path(case_path.stem).resolve().parent:
        raise SystemExit('标准求解流程按用例名读取 data/<case>.json，请直接传 data/ 下的用例文件')
    case = case_path.stem
    t0 = time.perf_counter()
    g = graphlib.load_graph(case_path)
    if cores <= 1:
        plan = evaluate.make_plan({v: 0 for v in g.nodes}, [[0]])
        return evaluate.canonical_plan(plan), None, time.perf_counter() - t0
    recs = experiment.run_portfolio(case, problem, cores, level='auto', seed=seed,
                                    save_plan=True)
    evaluate.default_cache().flush()
    best = [r for r in recs if r.get('variant') == '_best' and r.get('feasible')
            and int(r.get('eval_problem', problem)) == problem]
    if not best:
        best = [r for r in recs if r.get('is_best') and r.get('feasible')]
    if not best or not best[0].get('plan_path'):
        raise SystemExit('标准求解流程没有得到可行方案')
    plan = json.loads((paths.ROOT / best[0]['plan_path'].replace('\\', '/')).read_text(encoding='utf-8'))
    res = evaluate.default_cache().evaluate(problem, case, plan)
    label = best[0].get('variant')
    for cand_label, cand_plan in _mono_candidates(g, case, problem, cores):
        cand_res = evaluate.default_cache().evaluate(problem, case, cand_plan)
        if cand_res.get('feasible') and cand_res['makespan'] < res['makespan']:
            plan, res, label = cand_plan, cand_res, cand_label
    evaluate.default_cache().flush()
    if verbose:
        print('  standard flow: variant={} makespan={}'.format(label, res.get('makespan')))
    return evaluate.canonical_plan(plan), res, time.perf_counter() - t0


def solve(case_path, problem: int, cores: int, fast: bool = False,
          seed: int = 0, verbose: bool = True):
    g = graphlib.load_graph(case_path)
    case = Path(case_path).stem
    t0 = time.perf_counter()
    if cores <= 1:
        plan = evaluate.make_plan({v: 0 for v in g.nodes}, [[0]])
        return evaluate.canonical_plan(plan), None, time.perf_counter() - t0
    if fast:
        plan = algorithms.cap_ls(g, cores, problem, seed=seed)
        return evaluate.canonical_plan(plan), None, time.perf_counter() - t0

    level = 'fast' if (problem == 1 and g.n > 12000) else 'full'
    grid = algorithms.candidate_params(problem, cores, level, n_ops=g.n)
    if level == 'full' and g.n > 6000 and problem == 1:
        grid = grid[:8]
    best, best_res = None, None
    for i, params in enumerate(grid):
        try:
            plan = evaluate.canonical_plan(
                algorithms.cap_ls(g, cores, problem, seed=seed, **params))
        except Exception as exc:                                 # noqa: BLE001
            if verbose:
                print(f'  candidate {i}: plan failed ({type(exc).__name__})')
            continue
        res = evaluate.default_cache().evaluate(problem, case, plan)
        if verbose:
            print('  candidate {}: makespan={} added={} {}'.format(
                i, res.get('makespan'), res.get('added_copy_bytes'),
                '' if res.get('feasible') else res.get('error', '')[:80]))
        if res.get('feasible') and (best_res is None
                                    or res['makespan'] < best_res['makespan']):
            best, best_res = plan, res
    evaluate.default_cache().flush()
    if best is None:                       # 兜底：整图单核，保证始终有可行解
        best = evaluate.canonical_plan(
            evaluate.make_plan({v: 0 for v in g.nodes},
                               [[0]] + [[] for _ in range(cores - 1)]))
    return best, best_res, time.perf_counter() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('graph')
    ap.add_argument('--problem', type=int, default=2, choices=(1, 2, 3))
    ap.add_argument('--cores', '-n', type=int, default=4)
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--fast', action='store_true')
    ap.add_argument('--grid-only', action='store_true',
                    help='只在候选网格中择优（不含退火与采样，旧行为）')
    ap.add_argument('-o', '--output')
    args = ap.parse_args()

    if args.fast or args.grid_only:
        plan, res, secs = solve(args.graph, args.problem, args.cores,
                                fast=args.fast, seed=args.seed)
    else:
        plan, res, secs = solve_standard(args.graph, args.problem, args.cores,
                                         seed=args.seed)
    out = Path(args.output) if args.output else Path(
        str(Path(args.graph).with_suffix('')) + '_multicore_res.json')
    out.write_text(json.dumps(plan, ensure_ascii=False, indent=1) + '\n',
                   encoding='utf-8')
    n_sub = len(set(plan['node_to_subgraph'].values()))
    print('OK: {} ops -> {} subgraphs on {} cores in {:.2f}s; output={}'.format(
        len(plan['node_to_subgraph']), n_sub, len(plan['core_schedules']),
        secs, out))
    if res:
        print('    official makespan={} added_copy_bytes={}'.format(
            res['makespan'], res['added_copy_bytes']))


if __name__ == '__main__':
    main()
