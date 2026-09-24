"""汇总实验结果 → 论文正文数字、附录表格与全部图表。

    python solution/make_report.py [--figures] [--tables] [--summary]

所有输出都由 results/*.csv 生成，禁止手工修改。
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from npu import paths, plots, stats                             # noqa: E402

TABLE_DIR = paths.PAPER_DIR / 'tables'


def _fmt(x, nd=0):
    if x is None:
        return '--'
    if nd == 0:
        return '{:,}'.format(int(x))
    return '{:.{}f}'.format(x, nd)


def _champion_csv() -> str:
    """保底池冠军表存在时用 final.csv，否则回退到 main.csv。"""
    return 'final.csv' if (paths.RESULTS_DIR / 'final.csv').is_file() else 'main.csv'


def best_per_case(rows, problem, eval_problem=None):
    out = {}
    for r in rows:
        if not r['feasible'] or r['makespan'] is None:
            continue
        if int(r['problem']) != problem:
            continue
        if eval_problem is not None and int(r.get('eval_problem') or 0) != eval_problem:
            continue
        key = (r['case'], int(r['num_cores'] or 0))
        if key not in out or r['makespan'] < out[key]['makespan']:
            out[key] = r
    return out


# --------------------------------------------------------------------------
# 附录表：逐用例 Makespan / 额外搬运量 / 命中率
# --------------------------------------------------------------------------

def appendix_tables(main_rows, n1_rows, p3_rows, cores=(1, 2, 3, 4, 5),
                    final_mode=False):
    """``final_mode``：main_rows 为保底池冠军表（含问题 3 冠军），三个问题一律取它。"""
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    singles = json.loads((paths.RESULTS_DIR / 'singlecore_baseline.json')
                         .read_text(encoding='utf-8'))
    n1 = {}
    for r in n1_rows:
        if r['feasible']:
            n1[(r['case'], int(r['problem']))] = r
    made = []
    for problem in (1, 2, 3):
        rows = main_rows if (problem != 3 or final_mode) else (p3_rows or main_rows)
        ep = 3 if problem == 3 else problem
        best = best_per_case(rows, problem, eval_problem=ep)
        out_rows = []
        for case in paths.all_cases():
            base = singles.get(case, {})
            rec = {'case': case,
                   'baseline_makespan': base.get('makespan'),
                   'baseline_added': base.get('added_copy_bytes')}
            for n in cores:
                if n == 1:
                    r = n1.get((case, problem))
                    mk = r['makespan'] if r else base.get('makespan')
                    add = r['added_copy_bytes'] if r else base.get('added_copy_bytes')
                    hit = r.get('cache_hit_rate') if r else None
                    sp = 1.0
                else:
                    r = best.get((case, n))
                    mk = r['makespan'] if r else None
                    add = r['added_copy_bytes'] if r else None
                    hit = r.get('cache_hit_rate') if r else None
                    sp = (base['makespan'] / mk) if (mk and base.get('makespan')) else None
                rec[f'makespan_n{n}'] = mk
                rec[f'added_n{n}'] = add
                rec[f'speedup_n{n}'] = round(sp, 4) if sp else None
                if problem == 3:
                    rec[f'hit_n{n}'] = round(hit, 4) if hit is not None else None
            out_rows.append(rec)
        path = TABLE_DIR / f'appendix_problem{problem}.csv'
        with path.open('w', newline='', encoding='utf-8') as fh:
            w = csv.DictWriter(fh, fieldnames=list(out_rows[0]))
            w.writeheader()
            w.writerows(out_rows)
        made.append(path)
        # Markdown 版（论文附录直接粘贴）
        per = 4 if problem == 3 else 3
        head = ['用例', '单核基准 Makespan']
        for n in cores:
            if n == 1:
                continue
            head += [f'N={n} Makespan', f'N={n} 额外搬运(B)', f'N={n} 加速比']
            if problem == 3:
                head.append(f'N={n} 命中率')
        md = ['| ' + ' | '.join(head) + ' |',
              '|' + '---|' * len(head)]
        for rec in out_rows:
            cells = [rec['case'], _fmt(rec['baseline_makespan'])]
            for n in cores:
                if n == 1:
                    continue
                cells += [_fmt(rec[f'makespan_n{n}']), _fmt(rec[f'added_n{n}']),
                          _fmt(rec[f'speedup_n{n}'], 3)]
                if problem == 3:
                    cells.append(_fmt(rec.get(f'hit_n{n}'), 3))
            md.append('| ' + ' | '.join(cells) + ' |')
        (TABLE_DIR / f'appendix_problem{problem}.md').write_text(
            '\n'.join(md), encoding='utf-8')
        made.append(TABLE_DIR / f'appendix_problem{problem}.md')
    # 问题 3 专用：无 L2 vs 只读 Cache
    if p3_rows:
        pairs = defaultdict(dict)
        for r in plots.best_plan_rows(p3_rows):
            if r['feasible']:
                pairs[(r['case'], int(r['num_cores'] or 0))][
                    int(r.get('eval_problem') or 0)] = r
        out_rows = []
        for (case, n), d in sorted(pairs.items()):
            if 2 not in d or 3 not in d:
                continue
            out_rows.append({
                'case': case, 'num_cores': n,
                'makespan_noL2': d[2]['makespan'],
                'makespan_L2': d[3]['makespan'],
                'added_noL2': d[2]['added_copy_bytes'],
                'added_L2': d[3]['added_copy_bytes'],
                'cache_hit_rate': round(d[3].get('cache_hit_rate') or 0.0, 4),
                'cache_speedup': round(d[2]['makespan'] / d[3]['makespan'], 4)
                if d[3]['makespan'] else None,
            })
        path = TABLE_DIR / 'appendix_problem3_cache.csv'
        with path.open('w', newline='', encoding='utf-8') as fh:
            w = csv.DictWriter(fh, fieldnames=list(out_rows[0]))
            w.writeheader()
            w.writerows(out_rows)
        made.append(path)
    return made


# --------------------------------------------------------------------------
# 正文数字
# --------------------------------------------------------------------------

def summary(main_rows, n1_rows, base_rows, abl_rows, p3_rows, run_rows=None):
    """``main_rows`` 为冠军记录（final.csv，存在时）；``run_rows`` 为原始 main.csv，
    只用于运行时间统计。"""
    out = {}
    run_rows = main_rows if run_rows is None else run_rows
    for problem in (1, 2, 3):
        rows = main_rows
        ep = 3 if problem == 3 else problem
        best = best_per_case(rows, problem, eval_problem=ep)
        per_n = defaultdict(list)
        per_stratum = defaultdict(lambda: defaultdict(list))
        adds = defaultdict(list)
        hits = defaultdict(list)
        for (case, n), r in best.items():
            if r['speedup']:
                per_n[n].append(r['speedup'])
                per_stratum[n][stats.strata(case)].append(r['speedup'])
            if r['added_copy_bytes'] is not None:
                adds[n].append(r['added_copy_bytes'])
            if r.get('cache_hit_rate') is not None:
                hits[n].append(r['cache_hit_rate'])
        out[f'problem{problem}'] = {
            'speedup_geomean': {n: round(plots.geomean(v), 4)
                                for n, v in sorted(per_n.items())},
            'speedup_mean': {n: round(sum(v) / len(v), 4)
                             for n, v in sorted(per_n.items())},
            'speedup_median': {n: round(st.median(v), 4)
                               for n, v in sorted(per_n.items())},
            'speedup_min': {n: round(min(v), 4) for n, v in sorted(per_n.items())},
            'speedup_max': {n: round(max(v), 4) for n, v in sorted(per_n.items())},
            'cases': {n: len(v) for n, v in sorted(per_n.items())},
            'added_copy_total': {n: int(sum(v)) for n, v in sorted(adds.items())},
            'added_copy_median': {n: int(st.median(v)) for n, v in sorted(adds.items())},
            'cache_hit_mean': {n: round(sum(v) / len(v), 4)
                               for n, v in sorted(hits.items()) if v},
            'speedup_ci': {n: [round(x, 4) for x in stats.bootstrap_ci(v, 'amean')]
                           for n, v in sorted(per_n.items())},
            'speedup_by_strata': {n: {s: stats.describe(per_stratum[n][s])
                                      for s in stats.STRATA}
                                  for n in sorted(per_n)},
        }
    # 基线对比
    cmp_rows = defaultdict(lambda: defaultdict(list))
    for r in base_rows:
        if r['feasible'] and r['speedup']:
            cmp_rows[(int(r['problem']), int(r['num_cores'] or 0))][
                r['algorithm']].append(r['speedup'])
    fails = defaultdict(lambda: [0, 0])
    for r in base_rows:
        key = (int(r['problem']), r['algorithm'])
        fails[key][1] += 1
        if not r['feasible']:
            fails[key][0] += 1
    out['baseline_speedup'] = {
        f'p{p}_n{n}': {a: round(stats.amean(v), 4) for a, v in sorted(d.items())}
        for (p, n), d in sorted(cmp_rows.items())}
    out['baseline_speedup_geomean'] = {
        f'p{p}_n{n}': {a: round(plots.geomean(v), 4) for a, v in sorted(d.items())}
        for (p, n), d in sorted(cmp_rows.items())}
    out['baseline_failrate'] = {
        f'p{p}_{a}': round(f[0] / f[1], 4) for (p, a), f in sorted(fails.items())}
    for problem in (1, 2, 3):
        for n in (2, 3, 4, 5):
            rows = main_rows
            ep = 3 if problem == 3 else problem
            best = best_per_case(rows, problem, eval_problem=ep)
            v = [r['speedup'] for (c, nn), r in best.items()
                 if nn == n and r['speedup']]
            if v:
                out['baseline_speedup'].setdefault(f'p{problem}_n{n}', {})[
                    'capls'] = round(stats.amean(v), 4)
                out['baseline_speedup_geomean'].setdefault(f'p{problem}_n{n}', {})[
                    'capls'] = round(plots.geomean(v), 4)
    # 消融
    abl = defaultdict(lambda: defaultdict(list))
    for r in abl_rows:
        if r['feasible'] and r['speedup']:
            abl[int(r['problem'])][r['variant']].append(r['speedup'])
    out['ablation'] = {f'problem{p}': {v: round(stats.amean(s), 4)
                                       for v, s in sorted(d.items())}
                       for p, d in sorted(abl.items())}
    out['ablation_geomean'] = {f'problem{p}': {v: round(plots.geomean(s), 4)
                                               for v, s in sorted(d.items())}
                               for p, d in sorted(abl.items())}
    abl_fail = defaultdict(lambda: [0, 0])
    for r in abl_rows:
        abl_fail[(int(r['problem']), r['variant'])][1] += 1
        if not r['feasible']:
            abl_fail[(int(r['problem']), r['variant'])][0] += 1
    out['ablation_failrate'] = {f'p{p}_{v}': round(f[0] / f[1], 4)
                                for (p, v), f in sorted(abl_fail.items())}
    # L2 净收益
    if p3_rows:
        pairs = defaultdict(dict)
        for r in plots.best_plan_rows(p3_rows):
            if r['feasible']:
                pairs[(r['case'], int(r['num_cores'] or 0))][
                    int(r.get('eval_problem') or 0)] = r
        gain = defaultdict(list)
        hit = defaultdict(list)
        for (case, n), d in pairs.items():
            if 2 in d and 3 in d and d[3]['makespan']:
                gain[n].append(d[2]['makespan'] / d[3]['makespan'])
                if d[3].get('cache_hit_rate') is not None:
                    hit[n].append(d[3]['cache_hit_rate'])
        out['l2_gain'] = {n: round(stats.amean(v), 4) for n, v in sorted(gain.items())}
        out['l2_gain_geomean'] = {n: round(plots.geomean(v), 4)
                                  for n, v in sorted(gain.items())}
        out['l2_gain_max'] = {n: round(max(v), 4) for n, v in sorted(gain.items())}
        out['l2_hit_rate'] = {n: round(sum(v) / len(v), 4)
                              for n, v in sorted(hit.items()) if v}
    # 与理论下界的距离
    out['bound_gap'] = {}
    for problem in (1, 2, 3):
        g = plots.bound_gap(_champion_csv(), problem)
        out['bound_gap'][f'problem{problem}'] = {
            n: round(plots.geomean(v), 4) for n, v in sorted(g.items())}
    # 运行时间（始终取原始 main.csv 的逐候选记录）
    rt = [r['runtime_s'] for r in run_rows if r['runtime_s']]
    ev = [r['eval_s'] for r in run_rows if r['eval_s']]
    if rt:
        out['runtime'] = {'mean': round(sum(rt) / len(rt), 3),
                          'median': round(st.median(rt), 3),
                          'p95': round(sorted(rt)[int(len(rt) * .95)], 3),
                          'max': round(max(rt), 3),
                          'n': len(rt)}
    if ev:
        out['eval_time'] = {'mean': round(sum(ev) / len(ev), 3),
                            'max': round(max(ev), 3)}
    # 配对比较（N=4）：CAP-LS 冠军 vs 各基线；完整 vs 各消融变体。
    # a 为本文方法，rel > 0 表示本文方法更好；每个问题内做 Holm 校正。
    out['paired'] = {}
    for problem in (1, 2, 3):
        rows = main_rows
        ep = 3 if problem == 3 else problem
        best = best_per_case(rows, problem, eval_problem=ep)
        ours = {(c, n): r['speedup'] for (c, n), r in best.items()
                if n == 4 and r['speedup']}
        res = {}
        for algo in ('random', 'topo', 'balance', 'comm'):
            other = {(r['case'], 4): r['speedup'] for r in base_rows
                     if int(r['problem']) == problem
                     and int(r['num_cores'] or 0) == 4
                     and r['algorithm'] == algo
                     and r['feasible'] and r['speedup']}
            res[f'capls_vs_{algo}'] = stats.paired(ours, other)
        by_var = defaultdict(dict)
        for r in abl_rows:
            if (int(r['problem']) == problem and int(r['num_cores'] or 0) == 4
                    and r['feasible'] and r['speedup']):
                by_var[r['variant']][(r['case'], 4)] = r['speedup']
        for variant in sorted(by_var):
            if variant != 'full':
                res[f'full_vs_{variant}'] = stats.paired(by_var['full'],
                                                         by_var[variant])
        adj = stats.holm({k: d['p'] for k, d in res.items()})
        for k, d in res.items():
            d['p_holm'] = adj[k]
        out['paired'][f'problem{problem}'] = res
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--figures', action='store_true')
    ap.add_argument('--tables', action='store_true')
    ap.add_argument('--summary', action='store_true')
    args = ap.parse_args()
    if not (args.figures or args.tables or args.summary):
        args.figures = args.tables = args.summary = True

    main_rows = plots.read_csv('main.csv')
    final_rows = plots.read_csv('final.csv') or main_rows
    n1_rows = plots.read_csv('n1.csv')
    base_rows = plots.read_csv('baseline.csv')
    abl_rows = plots.read_csv('ablation.csv')
    p3_rows = plots.read_csv('p3_compare.csv')
    champ_csv = _champion_csv()

    if args.tables:
        for p in appendix_tables(final_rows, n1_rows, p3_rows,
                                 final_mode=(champ_csv == 'final.csv')):
            print('table ->', p)
    if args.summary:
        s = summary(final_rows, n1_rows, base_rows, abl_rows, p3_rows,
                    run_rows=main_rows)
        path = paths.RESULTS_DIR / 'summary.json'
        path.write_text(json.dumps(s, ensure_ascii=False, indent=1),
                        encoding='utf-8')
        print(json.dumps(s, ensure_ascii=False, indent=1))
        print('summary ->', path)
    if args.figures:
        plots.fig_architecture()
        plots.fig_example_dag()
        plots.fig_partition_sketch()
        plots.fig_framework()
        if main_rows:
            plots.fig_speedup(main_csv=champ_csv)
            plots.fig_speedup_box(main_csv=champ_csv)
            plots.fig_runtime(main_csv='main.csv')
            for p in (1, 2, 3):
                plots.fig_makespan_compare(p, 4, main_csv=champ_csv)
                plots.fig_addedcopy_compare(p, 4, main_csv=champ_csv)
                plots.fig_pareto(main_csv=champ_csv, problem=p, ncores=4)
            plots.fig_feature_effect(main_csv=champ_csv, problem=2, ncores=4)
        if p3_rows:
            plots.fig_cache()
            plots.fig_p3_curve()
        if abl_rows:
            plots.fig_ablation()
        plots.fig_granularity()
        plots.fig_sensitivity()
        if main_rows:
            plots.fig_subgraph_count(main_csv=champ_csv)
            plots.fig_lower_bound(main_csv=champ_csv)


if __name__ == '__main__':
    main()
