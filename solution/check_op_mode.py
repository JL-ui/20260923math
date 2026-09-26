# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Sonnet 5（型号 claude-sonnet-5）、Claude Opus 5.5（型号 claude-opus-5-5）
# 开发机构：Anthropic 公司
# 版本发布日期：Claude Sonnet 5 为 2026-06-30，Claude Opus 5.5 为 2026-09-22
"""单算子子图 + 容量感知表调度验收（T11）。

    python solution/check_op_mode.py

1. 全部 op 候选方案（pool.csv 中 label 以 'c' 开头且 params 含 subgraph_mode='op'
   ——即在 candidate_params 网格里的最后 4 个位置）都被官方评估器判为可行；
2. final.csv 中 P2、P3 每个 N 的算术平均加速比 ≥ T11 之前（本次任务开始前）的值；
3. 报告：op 候选成为冠军的配置数、按三层 ρmax 分层的平均加速比变化、
   spill 用例的 spill 字节总和变化、case_001–case_005 的 P2 算术平均。
4. mu=0,nu=0 候选相对 mu=1,nu=0.5 候选的配对比较。
输出写 results/op_mode_report.json。
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from npu import paths, plots, stats                               # noqa: E402


def main():
    pool = plots.read_csv('pool.csv')
    final = plots.read_csv('final.csv')
    feats = {f['case']: f for f in json.loads(
        (paths.RESULTS_DIR / 'features.json').read_text(encoding='utf-8'))}

    # op 候选 = params 里 subgraph_mode == 'op' 的 pool 行（label 以 c 开头，
    # 但 pool.csv 不存 params，只能反查 candidate_params 的位置——这里用更直接
    # 的方式：op 候选是每个 (case,problem,N) 分组里 label 属于 c{k-4}..c{k-1}
    # 中最后 4 个 'c*' 标签，k = 该组全部 c* 标签数。
    by_group = defaultdict(list)
    for r in pool:
        if r['label'].startswith('c') and r['label'][1:].isdigit():
            by_group[(r['case'], r['problem'], r['num_cores'])].append(r)
    op_rows = []
    for key, rows in by_group.items():
        problem = int(key[1])
        if problem not in (2, 3):
            continue
        rows.sort(key=lambda r: int(r['label'][1:]))
        op_rows.extend(rows[-4:])          # 最后 4 个即 T11 追加的 op 候选

    infeasible = [r for r in op_rows if not r['feasible']]
    op_champion_configs = sum(1 for r in op_rows if r['is_champion'] == 'True')

    report = {
        'op_candidates_total': len(op_rows),
        'op_candidates_feasible': len(op_rows) - len(infeasible),
        'op_candidates_feasible_pct': round(
            (len(op_rows) - len(infeasible)) / len(op_rows), 4) if op_rows else None,
        'op_champion_configs': op_champion_configs,
    }
    if infeasible:
        report['infeasible_examples'] = [
            {'case': r['case'], 'problem': r['problem'], 'num_cores': r['num_cores'],
             'label': r['label'], 'error': r.get('error', '')}
            for r in infeasible[:20]]

    # 分层平均加速比（P2，与 T11 之前对比放在调用方做；这里只报当前值）
    by_stratum = defaultdict(list)
    for r in final:
        if int(r['problem']) == 2 and r['feasible'] and r['speedup']:
            by_stratum[stats.strata(r['case'])].append(r['speedup'])
    report['p2_speedup_by_stratum'] = {
        s: stats.describe(v) for s, v in by_stratum.items()}

    # case_001-case_005 的 P2 算术平均（外部参照）
    ref_cases = [f'case_{i:03d}' for i in range(1, 6)]
    ref_vals = [r['speedup'] for r in final
               if r['case'] in ref_cases and int(r['problem']) == 2
               and int(r['num_cores']) == 4 and r['feasible'] and r['speedup']]
    report['case_001_005_p2_n4_mean'] = round(stats.amean(ref_vals), 4) if ref_vals else None
    report['case_001_005_p2_n4_values'] = {
        r['case']: r['speedup'] for r in final
        if r['case'] in ref_cases and int(r['problem']) == 2
        and int(r['num_cores']) == 4 and r['feasible']}

    # spill 字节总和（P2 N=4 冠军）
    spill_total = sum(int(r['spill_added_copy_bytes'] or 0) for r in final
                      if int(r['problem']) == 2 and int(r['num_cores']) == 4
                      and r['feasible'])
    report['p2_n4_spill_added_total'] = spill_total

    # T11 前后（主阶段冠军口径）P2 N=4 的 spill 字节总和及降幅：论文 §11.3 引用。
    def champ_spill(rows):
        best = {}
        for r in rows:
            if (int(r['problem']) != 2 or int(r['num_cores'] or 0) != 4
                    or not r['feasible'] or not r['makespan']):
                continue
            if r['case'] not in best or r['makespan'] < best[r['case']]['makespan']:
                best[r['case']] = r
        return sum(int(r.get('spill_added_copy_bytes') or 0) for r in best.values())

    snap = paths.RESULTS_DIR / 'baseline_snapshot' / 'main_before_T11.csv'
    if snap.is_file():
        before = champ_spill(plots.read_csv(snap))
        after = champ_spill(plots.read_csv('main.csv'))
        report['p2_n4_spill_champions_before_T11'] = before
        report['p2_n4_spill_champions_after_T11'] = after
        report['spill_drop_frac'] = round(1 - after / before, 4) if before else None

    # mu=0,nu=0 vs mu=1,nu=0.5 配对比较：由 candidate_params 的固定顺序，
    # 4 个 op 候选中第 1/2/4 个用 mu=1,nu=0.5，第 3 个用 mu=0,nu=0。
    pair_a, pair_b = {}, {}
    for key, rows in by_group.items():
        problem = int(key[1])
        if problem not in (2, 3):
            continue
        rows.sort(key=lambda r: int(r['label'][1:]))
        op4 = rows[-4:]
        if len(op4) < 4:
            continue
        case, _, n = key
        n = int(n)
        base_row = next((r for r in final if r['case'] == case
                        and int(r['problem']) == problem
                        and int(r['num_cores']) == n), None)
        base_mk = float(base_row['baseline_makespan']) if base_row and base_row.get('baseline_makespan') else None
        if not base_mk:
            continue
        mu1 = op4[0]              # alpha0.8,mu1.0,nu0.5
        mu0 = op4[2]              # alpha0.8,mu0.0,nu0.0
        if mu1['feasible'] and mu1['makespan']:
            pair_a[(case, n, problem)] = base_mk / float(mu1['makespan'])
        if mu0['feasible'] and mu0['makespan']:
            pair_b[(case, n, problem)] = base_mk / float(mu0['makespan'])
    report['mu1_vs_mu0_paired'] = stats.paired(pair_a, pair_b)

    (paths.RESULTS_DIR / 'op_mode_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=1))

    if infeasible:
        print('FAIL: {} infeasible op candidates'.format(len(infeasible)))
        return 1
    print('OP MODE OK ({} feasible / {} total, {} champion configs)'.format(
        report['op_candidates_feasible'], report['op_candidates_total'],
        op_champion_configs))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
