"""把实验结果压缩成一页可读摘要（供撰写论文正文时核对数字）。

    python solution/digest.py
"""

from __future__ import annotations

import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from npu import paths, plots                                     # noqa: E402


def sec(title):
    print('\n' + '=' * 72)
    print(title)
    print('=' * 72)


def main():
    feats = {f['case']: f for f in json.loads(
        (paths.RESULTS_DIR / 'features.json').read_text(encoding='utf-8'))}
    main_rows = plots.read_csv('main.csv')
    p3_rows = plots.read_csv('p3_compare.csv')
    base_rows = plots.read_csv('baseline.csv')
    abl_rows = plots.read_csv('ablation.csv')
    gran_rows = plots.read_csv('granularity.csv')
    sens_rows = plots.read_csv('sensitivity.csv')

    sec('1. 主结果：加速比（几何平均 / 中位 / min / max / 超线性用例数）')
    for problem in (1, 2, 3):
        rows = p3_rows if (problem == 3 and p3_rows) else main_rows
        ep = 3 if problem == 3 else problem
        best = {}
        for r in rows:
            if not r['feasible'] or int(r['problem']) != problem:
                continue
            if int(r.get('eval_problem') or 0) != ep:
                continue
            k = (r['case'], int(r['num_cores'] or 0))
            if k not in best or r['makespan'] < best[k]['makespan']:
                best[k] = r
        for n in (2, 3, 4, 5):
            v = [r['speedup'] for (c, nn), r in best.items()
                 if nn == n and r['speedup']]
            if not v:
                continue
            sup = sum(1 for x in v if x > n)
            print('  P{} N={}  geo={:.3f}  med={:.3f}  min={:.3f}  max={:.3f}  '
                  'n={}  超线性={}'.format(problem, n, plots.geomean(v),
                                          st.median(v), min(v), max(v), len(v), sup))
        v4 = {c: r for (c, nn), r in best.items() if nn == 4}
        if v4:
            worst = sorted(v4.items(), key=lambda kv: kv[1]['speedup'] or 0)[:6]
            print('  P{} N=4 最差 6 例: {}'.format(problem, ', '.join(
                '{}={:.2f}'.format(c[5:], r['speedup'] or 0) for c, r in worst)))
            add = [r['added_copy_bytes'] for r in v4.values()
                   if r['added_copy_bytes'] is not None]
            print('  P{} N=4 额外搬运: 总 {:,} B, 中位 {:,} B, 零增量用例 {}'.format(
                problem, sum(add), int(st.median(add)),
                sum(1 for x in add if x == 0)))
            ns = [r['n_subgraphs'] for r in v4.values() if r['n_subgraphs']]
            print('  P{} N=4 子图数: 中位 {} 范围 [{}, {}]'.format(
                problem, int(st.median(ns)), min(ns), max(ns)))

    sec('2. 难例分层（问题 2、N=4，按最大连通分量占比）')
    best = plots.best_rows([r for r in main_rows if int(r['problem']) == 2
                            and int(r['num_cores'] or 0) == 4])
    layers = {'ρmax<0.2': [], '0.2≤ρmax<0.5': [], 'ρmax≥0.5': []}
    for (c, p, n), r in best.items():
        f = feats.get(c)
        if not f or not r['speedup']:
            continue
        rho = f['largest_component_frac']
        key = ('ρmax<0.2' if rho < 0.2 else
               '0.2≤ρmax<0.5' if rho < 0.5 else 'ρmax≥0.5')
        layers[key].append(r['speedup'])
    for k, v in layers.items():
        if v:
            print('  {:14s} n={:3d}  geo={:.3f}  med={:.3f}  min={:.3f}'.format(
                k, len(v), plots.geomean(v), st.median(v), min(v)))

    sec('3. 基线对比（几何平均加速比 + 不可行率）')
    for problem in (1, 2, 3):
        cells = {}
        for r in base_rows:
            if int(r['problem']) != problem or int(r['num_cores'] or 0) != 4:
                continue
            cells.setdefault(r['algorithm'], {'ok': [], 'bad': 0})
            if r['feasible'] and r['speedup']:
                cells[r['algorithm']]['ok'].append(r['speedup'])
            elif not r['feasible']:
                cells[r['algorithm']]['bad'] += 1
        ours = plots.best_rows([r for r in (p3_rows if problem == 3 and p3_rows
                                            else main_rows)
                                if int(r['problem']) == problem
                                and int(r['num_cores'] or 0) == 4
                                and int(r.get('eval_problem') or 0) == problem])
        v = [r['speedup'] for r in ours.values() if r['speedup']]
        line = '  P{}  '.format(problem)
        for a in ('random', 'topo', 'balance', 'comm'):
            d = cells.get(a)
            if d and d['ok']:
                line += '{}={:.2f}(fail {}) '.format(a, plots.geomean(d['ok']),
                                                     d['bad'])
        if v:
            line += '| CAP-LS={:.2f}'.format(plots.geomean(v))
        print(line)

    sec('4. 消融（几何平均加速比，N 合并）')
    for problem in (1, 2, 3):
        d = defaultdict(list)
        fails = defaultdict(int)
        for r in abl_rows:
            if int(r['problem'] or 0) != problem:
                continue
            if r['feasible'] and r['speedup']:
                d[r['variant']].append(r['speedup'])
            elif not r['feasible']:
                fails[r['variant']] += 1
        full = plots.geomean(d.get('full', []))
        parts = []
        for k in ('full', 'no_level', 'no_sync', 'no_comm', 'no_balance',
                  'no_localsearch', 'no_cache_aware'):
            if d.get(k):
                g = plots.geomean(d[k])
                parts.append('{}={:.3f}({:+.1%}{})'.format(
                    k, g, g / full - 1 if full else 0,
                    ',fail{}'.format(fails[k]) if fails[k] else ''))
        print('  P{}: {}'.format(problem, '  '.join(parts)))

    sec('5. 问题 3：L2 收益（同一方案，problem2 vs problem3）')
    pairs = defaultdict(dict)
    for r in plots.best_plan_rows(p3_rows):
        if r['feasible']:
            pairs[(r['case'], int(r['num_cores'] or 0))][
                int(r.get('eval_problem') or 0)] = r
    byn = defaultdict(list)
    hits = defaultdict(list)
    for (case, n), d in pairs.items():
        if 2 in d and 3 in d and d[3]['makespan']:
            byn[n].append(d[2]['makespan'] / d[3]['makespan'])
            if d[3].get('cache_hit_rate') is not None:
                hits[n].append(d[3]['cache_hit_rate'])
    for n in sorted(byn):
        v = byn[n]
        h = hits.get(n, [])
        print('  N={}  gain geo={:.4f} max={:.3f} >1.01的用例={} / {}   '
              'hit mean={:.3f} max={:.3f} 非零={}'.format(
                  n, plots.geomean(v), max(v), sum(1 for x in v if x > 1.01),
                  len(v), sum(h) / len(h) if h else 0, max(h) if h else 0,
                  sum(1 for x in h if x > 0)))
    # 收益最大的用例
    tops = sorted(((d[2]['makespan'] / d[3]['makespan'], case, n)
                   for (case, n), d in pairs.items()
                   if 2 in d and 3 in d and d[3]['makespan']), reverse=True)[:8]
    print('  收益最大: ' + ', '.join('{}@N{}={:.2f}'.format(c[5:], n, g)
                                     for g, c, n in tops))

    sec('6. 粒度敏感性（几何平均加速比 vs β）')
    d = defaultdict(lambda: defaultdict(list))
    for r in gran_rows:
        if r['feasible'] and r['speedup']:
            d[int(r['problem'])][r['variant']].append(r['speedup'])
    for p in sorted(d):
        items = sorted(d[p].items(), key=lambda kv: float(kv[0]))
        print('  P{}: {}'.format(p, '  '.join(
            'β={}:{:.3f}'.format(k, plots.geomean(v)) for k, v in items)))

    sec('7. 硬件敏感性（相对默认配置的 Makespan 倍数，几何平均）')
    by = defaultdict(lambda: defaultdict(dict))
    default_value = {}
    for r in sens_rows:
        if not r['feasible'] or not r['makespan']:
            continue
        by[r['knob']][r['case']][float(r['value'])] = r['makespan']
        if str(r.get('is_default')).lower() == 'true':
            default_value[r['knob']] = float(r['value'])
    for knob in by:
        base = default_value.get(knob)
        xs = sorted({v for t in by[knob].values() for v in t})
        out = []
        for v in xs:
            ratios = [t[base] / t[v] for t in by[knob].values()
                      if v in t and base in t and t[v]]
            if ratios:
                out.append('{:g}:{:.3f}'.format(v, plots.geomean(ratios)))
        print('  {:34s} {}'.format(knob, '  '.join(out)))

    sec('8. 运行时间')
    rt = [r['runtime_s'] for r in main_rows if r['runtime_s']]
    ev = [r['eval_s'] for r in main_rows if r['eval_s']]
    if rt:
        print('  单候选算法时间: 中位 {:.2f}s  p95 {:.1f}s  max {:.1f}s  (n={})'
              .format(st.median(rt), sorted(rt)[int(len(rt) * .95)], max(rt), len(rt)))
    if ev:
        print('  官方评估时间:   中位 {:.2f}s  p95 {:.1f}s  max {:.1f}s'.format(
            st.median(ev), sorted(ev)[int(len(ev) * .95)], max(ev)))
    n_eval = 0
    for f in (paths.CACHE_DIR).glob('p*/*.json'):
        try:
            n_eval += len(json.loads(f.read_text(encoding='utf-8')))
        except Exception:                                        # noqa: BLE001
            pass
    print('  去重后的官方评估调用总数: {:,}'.format(n_eval))

    sec('9. 与理论下界的距离')
    for problem in (1, 2, 3):
        g = plots.bound_gap('main.csv', problem)
        print('  P{}: '.format(problem) + '  '.join(
            'N={}:{:.2f}'.format(n, plots.geomean(v)) for n, v in sorted(g.items())))


if __name__ == '__main__':
    main()
