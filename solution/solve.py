"""单用例求解入口：生成官方格式的多核切图与调度方案。

    python solution/solve.py data/case_001.json --problem 2 --cores 4 \
           -o data/case_001_multicore_res.json

默认使用多起点组合（候选逐个交官方评估器打分取最优）；加 `--fast` 只跑
单个默认配置，不调用评估器。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from npu import algorithms, evaluate, graphlib, paths            # noqa: E402


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

    level = 'fast' if g.n > 12000 else 'full'
    grid = algorithms.candidate_params(problem, cores, level)
    if level == 'full' and g.n > 6000:
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
    ap.add_argument('-o', '--output')
    args = ap.parse_args()

    plan, res, secs = solve(args.graph, args.problem, args.cores,
                            fast=args.fast, seed=args.seed)
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
