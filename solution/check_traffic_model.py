"""搬运量解析模型与官方评估器的一致性检验。

`graphlib.scene_a_copy_bytes` / `scene_b_copy_bytes` 按《评估器机制说明》H 节
的规则预测"切图边界搬运字节"。官方评估器输出的
`scheduled_copy_bytes − spill_added_copy_bytes` 正是同一口径（后者是核内
换入换出，属于 Step2 的运行时决策，解析模型不预测）。本脚本逐个用例比对。

    python solution/check_traffic_model.py --cases case_001 ... -n 4
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from npu import algorithms, evaluate, experiment, graphlib, paths  # noqa: E402


def check(case: str, ncores: int, problem: int):
    g = experiment.get_graph(case)
    plan = evaluate.canonical_plan(algorithms.cap_ls(g, ncores, problem))
    mapping = {int(k): int(v) for k, v in plan['node_to_subgraph'].items()}
    core_of_sub = {}
    for k, order in enumerate(plan['core_schedules']):
        for sg in order:
            core_of_sub[sg] = k
    if problem == 1:
        predicted = graphlib.scene_a_copy_bytes(g, mapping)
    else:
        predicted = graphlib.scene_b_copy_bytes(g, mapping, core_of_sub)
    res = evaluate.default_cache().evaluate(problem, case, plan)
    if not res.get('feasible'):
        return None
    actual = res['scheduled_copy_bytes'] - res['spill_added_copy_bytes']
    return {'case': case, 'problem': problem, 'num_cores': ncores,
            'predicted_bytes': predicted, 'actual_boundary_bytes': actual,
            'abs_err': abs(predicted - actual),
            'rel_err': (predicted - actual) / actual if actual else 0.0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cases', nargs='*')
    ap.add_argument('-n', '--cores', type=int, default=4)
    args = ap.parse_args()
    cases = args.cases or paths.all_cases()[:30]
    rows = []
    for case in cases:
        for problem in (1, 2, 3):
            r = check(case, args.cores, problem)
            if r:
                rows.append(r)
                flag = 'OK ' if r['abs_err'] == 0 else '!! '
                print('{}{} P{} predicted={:>12,} actual={:>12,} rel_err={:+.3%}'
                      .format(flag, case, problem, r['predicted_bytes'],
                              r['actual_boundary_bytes'], r['rel_err']))
    evaluate.default_cache().flush()
    exact = sum(1 for r in rows if r['abs_err'] == 0)
    print('\n逐位一致 {}/{}；最大相对误差 {:.4%}'.format(
        exact, len(rows), max((abs(r['rel_err']) for r in rows), default=0)))
    experiment.write_csv(rows, paths.RESULTS_DIR / 'traffic_model_check.csv')


if __name__ == '__main__':
    main()
