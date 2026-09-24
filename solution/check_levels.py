"""单调层指派检查（T12 验收 1）。

    python solution/check_levels.py --jobs 16

对全部用例 × N=2..5 × 3 种随机核分配（assign.random_assign，种子 0/1/2），
三种非 ASAP 模式（alap_fill / compress / alap_compress）都必须通过
levels.check_monotone，且按 (层, 核) 成形的方案经官方评估（问题 2，走缓存）可行。
全部通过打印 LEVELS OK。
"""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from npu import assign, evaluate, experiment, levels, partition, paths, stratify  # noqa: E402

MODES = ('alap_fill', 'compress', 'alap_compress')


def task(case):
    g = experiment.get_graph(case)
    cache = evaluate.default_cache()
    bad = []
    count = 0
    for n in (2, 3, 4, 5):
        bs = partition.make_blocks(g, n, block_cap=0.35)
        rank = {v: i for i, v in enumerate(bs.sigma)}
        for seed in (0, 1, 2):
            core = assign.random_assign(bs, n, seed=seed)
            core_of_op = {v: core[bs.block_of[v]] for v in g.nodes}
            for mode in MODES:
                count += 1
                try:
                    lv = levels.assign_levels(g, core_of_op, mode)
                    levels.check_monotone(g, core_of_op, lv)
                    mapping, schedules, _ = stratify.build_subgraphs(
                        g, core_of_op, n, rank, levels=lv)
                    res = cache.evaluate(2, case, evaluate.make_plan(mapping, schedules))
                except Exception as exc:                        # noqa: BLE001
                    bad.append((case, n, seed, mode, '{}: {}'.format(
                        type(exc).__name__, str(exc)[:160])))
                    continue
                if not res.get('feasible'):
                    bad.append((case, n, seed, mode, res.get('error', '')[:160]))
    cache.flush()
    return count, bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--jobs', type=int, default=16)
    ap.add_argument('--cases', nargs='*')
    args = ap.parse_args()
    cases = args.cases or paths.all_cases()
    total, bad = 0, []
    with ProcessPoolExecutor(max_workers=args.jobs) as ex:
        futs = [ex.submit(task, c) for c in cases]
        for i, fut in enumerate(as_completed(futs), 1):
            c, b = fut.result()
            total += c
            bad.extend(b)
            if i % 20 == 0 or i == len(futs):
                print(f'{i}/{len(futs)} checked={total} failures={len(bad)}', flush=True)
    for b in bad:
        print('FAIL', *b)
    if bad:
        return 1
    print('LEVELS OK ({} plans)'.format(total))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
