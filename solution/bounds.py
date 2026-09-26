# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Sonnet 5（型号 claude-sonnet-5）、Claude Opus 5.5（型号 claude-opus-5-5）
# 开发机构：Anthropic 公司
# 版本发布日期：Claude Sonnet 5 为 2026-06-30，Claude Opus 5.5 为 2026-09-22
"""界与参照（T19）。

    python solution/bounds.py --jobs 16 [--skip-empirical]

1. 逐用例 MK / LB（plots.lower_bound，数据源 final.csv），CDF 数据写 results/bounds_cdf.csv；
2. 单核归一化效率 (LB_N / MK_N) / (LB_1 / MK_1)，MK_1 为官方单核基准；
3. 可达加速比上界 MK_1 / LB_N 与"达到上界的比例" speedup / (MK_1 / LB_N)；
4. 大预算经验参照：pilot20 的前 15 个用例（samples.json 顺序）、问题 2、N=4，
   每个用例 200 个方案（seed = 0..199，block_cap 按 (0.08, 0.15, 0.35, 0.6) 循环，
   init='random'），全部官方评估（走缓存）；经验参照 = min(这 200 个, final.csv 冠军)。
输出 results/bounds.json（第 4 部分的逐方案记录另写 results/bounds_empirical.csv）。
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from npu import algorithms, evaluate, experiment, paths, plots, stats  # noqa: E402

EMP_CAPS = (0.08, 0.15, 0.35, 0.6)
EMP_PLANS = 200


def emp_task(case):
    g = experiment.get_graph(case)
    cache = evaluate.default_cache()
    rows = []
    for seed in range(EMP_PLANS):
        cap = EMP_CAPS[seed % len(EMP_CAPS)]
        plan = algorithms.cap_ls(g, 4, 2, block_cap=cap, init='random', seed=seed)
        res = cache.evaluate(2, case, plan)
        rows.append({'case': case, 'seed': seed, 'block_cap': cap,
                     'feasible': bool(res.get('feasible')),
                     'makespan': res.get('makespan')})
    cache.flush()
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--jobs', type=int, default=16)
    ap.add_argument('--skip-empirical', action='store_true')
    args = ap.parse_args()
    feats = {f['case']: f for f in json.loads(
        (paths.RESULTS_DIR / 'features.json').read_text(encoding='utf-8'))}
    final = plots.read_csv('final.csv')
    out = {'ratio': {}, 'efficiency': {}, 'upper_bound': {}}
    cdf_rows = []
    single_ratio = []
    for case in paths.all_cases():
        mk1 = evaluate.singlecore_baseline(case).get('makespan')
        if mk1:
            single_ratio.append(mk1 / plots.lower_bound(feats[case], 1))
    out['single_over_lb1_median'] = round(st.median(single_ratio), 4)
    groups = defaultdict(list)
    for r in final:
        if r['feasible']:
            groups[(int(r['problem']), int(r['num_cores']))].append(r)
    for (p, n), rows in sorted(groups.items()):
        ratios, effs, ubs, reach = [], [], [], []
        for r in rows:
            f = feats[r['case']]
            lb_n = plots.lower_bound(f, n)
            lb_1 = plots.lower_bound(f, 1)
            mk1 = r['baseline_makespan']
            ratio = r['makespan'] / lb_n
            ratios.append(ratio)
            cdf_rows.append({'problem': p, 'num_cores': n, 'case': r['case'],
                             'mk_over_lb': round(ratio, 4)})
            if mk1:
                effs.append((lb_n / r['makespan']) / (lb_1 / mk1))
                ub = mk1 / lb_n
                ubs.append(ub)
                reach.append(r['speedup'] / ub)
        key = f'p{p}_n{n}'
        out['ratio'][key] = stats.describe(ratios)
        out['efficiency'][key] = stats.describe(effs)
        out['upper_bound'][key] = {'speedup_upper': stats.describe(ubs),
                                   'fraction_of_upper': stats.describe(reach)}
    cdf_rows.sort(key=lambda r: (r['problem'], r['num_cores'], r['mk_over_lb'], r['case']))
    counts = defaultdict(int)
    for r in cdf_rows:
        counts[(r['problem'], r['num_cores'])] += 1
        r['cdf'] = round(counts[(r['problem'], r['num_cores'])]
                         / len(groups[(r['problem'], r['num_cores'])]), 4)
    experiment.write_csv(cdf_rows, paths.RESULTS_DIR / 'bounds_cdf.csv')

    if not args.skip_empirical:
        samples = json.loads((paths.RESULTS_DIR / 'samples.json').read_text(encoding='utf-8'))
        cases = samples['pilot20'][:15]
        emp = []
        with ProcessPoolExecutor(max_workers=args.jobs) as ex:
            for fut in as_completed([ex.submit(emp_task, c) for c in cases]):
                emp.extend(fut.result())
        emp.sort(key=lambda r: (r['case'], r['seed']))
        experiment.write_csv(emp, paths.RESULTS_DIR / 'bounds_empirical.csv')
        champ = {r['case']: r['makespan'] for r in final
                 if int(r['problem']) == 2 and int(r['num_cores']) == 4}
        per_case = {}
        for case in cases:
            rs = [r for r in emp if r['case'] == case]
            ok = [r['makespan'] for r in rs if r['feasible']]
            best_rand = min(ok) if ok else None
            ref = min([x for x in (best_rand, champ.get(case)) if x])
            per_case[case] = {'records': len(rs), 'feasible': len(ok),
                              'best_random': best_rand,
                              'champion': champ.get(case), 'reference': ref,
                              'gap': round(champ[case] / ref - 1, 4)}
        gaps = [d['gap'] for d in per_case.values()]
        out['empirical'] = {'cases': per_case,
                            'gap_mean': round(sum(gaps) / len(gaps), 4),
                            'gap_max': round(max(gaps), 4),
                            'champion_is_reference': sum(1 for g in gaps if g == 0)}
    (paths.RESULTS_DIR / 'bounds.json').write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps({k: v for k, v in out.items() if k != 'empirical'},
                     ensure_ascii=False)[:1500])
    if 'empirical' in out:
        print('empirical gap mean={gap_mean} max={gap_max}'.format(**out['empirical']))


if __name__ == '__main__':
    main()
