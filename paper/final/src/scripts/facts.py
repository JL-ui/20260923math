"""从 results/ 抽取论文中出现的全部数字，写成 facts.json（键 → 值、格式化文本、来源）。

    python paper/final/src/scripts/facts.py

只读 results/ 与 data/（图特征来自 results/features.json），不运行任何求解或评估。
正文 Markdown 用 {{KEY}} 引用这些值；build.py 在排版前替换，并据此生成《数字溯源表》。
"""
from __future__ import annotations

import csv
import glob
import json
import math
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path

from scipy import stats as sps

ROOT = Path(__file__).resolve().parents[4]
RES = ROOT / 'results'
OUT = Path(__file__).resolve().parents[1] / 'data'
OUT.mkdir(parents=True, exist_ok=True)

F: dict = {}


def put(key, raw, text, src):
    if key in F:
        raise KeyError('duplicate fact ' + key)
    F[key] = {'raw': raw, 'v': text, 'src': src}


def f2(x):
    return f'{x:.2f}'


def f3(x):
    return f'{x:.3f}'


def pct(x, d=1, sign=False):
    s = f'{100 * x:+.{d}f}%' if sign else f'{100 * x:.{d}f}%'
    return s.replace('-', '−')


def big(x):
    """1.23×10^9 形式（Markdown 数学）。"""
    if x == 0:
        return '0'
    e = int(math.floor(math.log10(abs(x))))
    m = x / 10 ** e
    return f'${m:.2f}\\times10^{{{e}}}$'


def thou(x):
    return f'{int(round(x)):,}'


def pval(p):
    if p == 0:
        return '$p<10^{-300}$'
    if p < 1e-3:
        e = int(math.floor(math.log10(p)))
        m = p / 10 ** e
        return f'$p={m:.1f}\\times10^{{{e}}}$'
    return f'$p={p:.3f}$'


def read(name):
    with open(RES / name, encoding='utf-8') as fh:
        return list(csv.DictReader(fh))


def amean(v):
    return sum(v) / len(v)


def gmean(v):
    return math.exp(sum(math.log(x) for x in v) / len(v))


S = json.loads((RES / 'summary.json').read_text(encoding='utf-8'))
final = read('final.csv')
feat = {r['case']: r for r in json.loads((RES / 'features.json').read_text(encoding='utf-8'))}
single = json.loads((RES / 'singlecore_baseline.json').read_text(encoding='utf-8'))
CASES = sorted(feat)
P = (1, 2, 3)
NS = (2, 3, 4, 5)

# ---------------------------------------------------------------- 主结果
su = defaultdict(dict)   # (p,n) -> case -> speedup
mk = defaultdict(dict)
for r in final:
    k = (int(r['problem']), int(r['num_cores']))
    su[k][r['case']] = float(r['speedup'])
    mk[k][r['case']] = int(r['makespan'])
for p in P:
    blk = S[f'problem{p}']
    for n in NS:
        v = list(su[(p, n)].values())
        assert len(v) == 100
        m = amean(v)
        assert abs(m - blk['speedup_mean'][str(n)]) < 1e-4, (p, n)
        src = f'results/final.csv（problem={p}, num_cores={n} 的 speedup 列算术平均；与 summary.json problem{p}.speedup_mean 一致）'
        put(f'SU_P{p}_N{n}', m, f2(m), src)
        put(f'SU4_P{p}_N{n}', m, f'{m:.4f}', src)
        put(f'MED_P{p}_N{n}', st.median(v), f2(st.median(v)), f'results/final.csv speedup 中位数（P{p}, N={n}）')
        put(f'MIN_P{p}_N{n}', min(v), f2(min(v)), f'results/final.csv speedup 最小值（P{p}, N={n}）')
        put(f'MAX_P{p}_N{n}', max(v), f2(max(v)), f'results/final.csv speedup 最大值（P{p}, N={n}）')
        put(f'GEO_P{p}_N{n}', gmean(v), f2(gmean(v)), f'results/final.csv speedup 几何平均（P{p}, N={n}，补充指标）')
        lo, hi = blk['speedup_ci'][str(n)]
        put(f'CI_P{p}_N{n}', (lo, hi), f'[{lo:.2f}, {hi:.2f}]',
            f'results/summary.json problem{p}.speedup_ci["{n}"]（bootstrap 10000 次，算术平均的 95% 百分位区间）')
        sup = sum(1 for x in v if x > n + 1e-9)
        put(f'SUPER_P{p}_N{n}', sup, str(sup), f'results/final.csv：P{p}, N={n} 中 speedup>{n} 的用例数')
        put(f'EFF_P{p}_N{n}', m / n, pct(m / n, 0), f'SU_P{p}_N{n}/{n}')
        put(f'EFFMED_P{p}_N{n}', st.median(v) / n, pct(st.median(v) / n, 0), f'MED_P{p}_N{n}/{n}')

allsu = [float(r['speedup']) for r in final]
put('MIN_ALL', min(allsu), f2(min(allsu)), 'results/final.csv 全部 1200 行 speedup 最小值')
put('N_FINAL_ROWS', len(final), str(len(final)), 'results/final.csv 行数')

# 单调性：MK(N) <= MK(N-1)，N=2 与单核比较
viol = 0
for p in P:
    for c in CASES:
        prev = single[c]['makespan']
        for n in NS:
            cur = mk[(p, n)][c]
            if cur > prev:
                viol += 1
            prev = cur
put('MONO_VIOL', viol, str(viol), 'results/final.csv + singlecore_baseline.json：逐用例 MK(N)>MK(N−1) 的次数')

# 最难用例（P2 N=4）
worst = sorted(su[(2, 4)].items(), key=lambda t: t[1])[:6]
put('WORST_P2N4', worst, '、'.join(f'{c}（{s:.2f}）' for c, s in worst), 'results/final.csv P2 N=4 speedup 最小的 6 个用例')
worst1 = sorted(su[(1, 4)].items(), key=lambda t: t[1])[:4]
put('WORST_P1N4', worst1, '、'.join(f'{c}（{s:.2f}）' for c, s in worst1), 'results/final.csv P1 N=4 speedup 最小的 4 个用例')
best2 = max(su[(2, 5)].items(), key=lambda t: t[1])
put('BEST_P2N5_CASE', best2[0], best2[0], 'results/final.csv P2 N=5 speedup 最大用例')

# 超线性与单核换入换出
sc_spill = {c: single[c]['spill_added_copy_bytes'] for c in CASES}
sup_cases = [c for c, s in su[(2, 4)].items() if s > 4]
with_spill = sum(1 for c in sup_cases if sc_spill[c] > 0)
put('SUPER_P2N4_SPILL', with_spill, str(with_spill), 'P2 N=4 超线性用例中，单核基准 spill_added_copy_bytes>0 的个数（singlecore_baseline.json）')
put('SC_SPILL_CASES', sum(1 for c in CASES if sc_spill[c] > 0), str(sum(1 for c in CASES if sc_spill[c] > 0)),
    'results/singlecore_baseline.json：spill_added_copy_bytes>0 的用例数')
put('SC_SPILL_MAX', max(sc_spill.values()), big(max(sc_spill.values())), 'singlecore_baseline.json spill_added_copy_bytes 最大值（字节）')
put('SC_SPILL_TOTAL', sum(sc_spill.values()), big(sum(sc_spill.values())), 'singlecore_baseline.json spill_added_copy_bytes 总和（字节）')

# 搬运量
for p in P:
    blk = S[f'problem{p}']
    for n in NS:
        t = blk['added_copy_total'][str(n)]
        put(f'ADD_P{p}_N{n}', t, big(t), f'summary.json problem{p}.added_copy_total["{n}"]（= final.csv added_copy_bytes 求和）')
    t4 = blk['added_copy_total']['4']
    sp = blk['spill_added_total']['4']
    pa = blk['partition_added_total']['4']
    put(f'ADDPART_P{p}', pa / t4, pct(pa / t4), f'summary.json problem{p}.partition_added_total["4"]/added_copy_total["4"]')
    put(f'ADDSPILL_P{p}', sp / t4, pct(sp / t4), f'summary.json problem{p}.spill_added_total["4"]/added_copy_total["4"]')
    z = sum(1 for r in final if int(r['problem']) == p and r['num_cores'] == '4' and int(r['added_copy_bytes']) == 0)
    put(f'ZEROADD_P{p}', z, str(z), f'final.csv P{p} N=4 added_copy_bytes=0 的用例数')
chk = sum(int(r['added_copy_bytes']) for r in final if r['problem'] == '2' and r['num_cores'] == '4')
assert chk == S['problem2']['added_copy_total']['4']
put('ADD_VS_SC_P2N4', S['problem2']['added_copy_total']['4'] / sum(sc_spill.values()) - 1,
    pct(S['problem2']['added_copy_total']['4'] / sum(sc_spill.values()) - 1, 0, sign=True),
    'ADD_P2_N4 / SC_SPILL_TOTAL − 1')

# 子图数
for p in P:
    v = [int(r['n_subgraphs']) for r in final if int(r['problem']) == p and r['num_cores'] == '4']
    put(f'NSUB_MED_P{p}', st.median(v), f'{st.median(v):g}', f'final.csv P{p} N=4 n_subgraphs 中位数')

# 冠军来源
def origin(label):
    if label.startswith('cross'):
        return 'cross'
    if label.startswith('embed'):
        return 'embed'
    if label.startswith('a_'):
        return 'ablation'
    if label.startswith('b_'):
        return 'baseline'
    if label.startswith('g_'):
        return 'granularity'
    if label.startswith('sa'):
        return 'anneal'
    if label.startswith('s') and label[1:].isdigit():
        return 'sample'
    if label.startswith('c') and label[1:].isdigit():
        i = int(label[1:])
        if i >= 14:
            return 'op'
        if i in (12, 13):
            return 'alap'
        return 'grid'
    if label == 'single':
        return 'single'
    return 'other'


orig = {p: Counter() for p in P}
for r in final:
    orig[int(r['problem'])][origin(r['variant'].split(':', 1)[1])] += 1
for p in P:
    for k in ('grid', 'alap', 'op', 'sample', 'anneal', 'ablation', 'baseline', 'granularity', 'embed', 'cross', 'single'):
        put(f'ORIG_P{p}_{k}', orig[p][k], str(orig[p][k]), f'final.csv P{p} 的 variant 前缀计数（{k}）；400 个配置')
pool_rows = read('pool.csv')
put('POOL_ROWS', len(pool_rows), thou(len(pool_rows)), 'results/pool.csv 行数（保底池内全部经官方评估的候选）')
exc = json.loads((RES / 'pool_condition4_exceptions.json').read_text(encoding='utf-8'))
put('COND4_COUNT', exc['count'], str(exc['count']), 'pool_condition4_exceptions.json count')
put('COND4_MAXREL', exc['max_rel_observed'], f"{100 * exc['max_rel_observed']:.4f}%", 'pool_condition4_exceptions.json max_rel_observed')
put('COND4_LIST', exc['exceptions'], '、'.join(f"{e['case']}（$N={e['num_cores']}$，{e['p3_makespan']} 对 {e['p2_makespan']}）" for e in exc['exceptions']),
    'pool_condition4_exceptions.json exceptions')

# P2 vs P3 冠军逐用例
eq = hi = lo = 0
for c in CASES:
    a, b = mk[(2, 4)][c], mk[(3, 4)][c]
    eq += a == b
    hi += b < a
    lo += b > a
put('P2P3_EQ', eq, str(eq), 'final.csv N=4：P3 冠军 makespan == P2 冠军的用例数')
put('P2P3_HI', hi, str(hi), 'final.csv N=4：P3 冠军更快的用例数')
put('P2P3_LO', lo, str(lo), 'final.csv N=4：P3 冠军更慢的用例数')

# ---------------------------------------------------------------- 复核
vf = read('verify_final.csv')
put('VERIFY_N', len(vf), thou(len(vf)), 'results/verify_final.csv 行数（官方 CLI 复核的方案数，N=1..5）')
put('VERIFY_MISMATCH', sum(1 for r in vf if r['match'] != 'True'), str(sum(1 for r in vf if r['match'] != 'True')),
    'verify_final.csv match≠True 的行数')
tm = read('traffic_model_check.csv')
put('TRAFFIC_N', len(tm), str(len(tm)), 'results/traffic_model_check.csv 行数')
ncache = sum(len(json.loads(Path(f).read_text(encoding='utf-8')))
             for p in ('p1', 'p2', 'p3') for f in glob.glob(str(RES / 'cache' / p / '*.json')))
put('TOTAL_EVALS', ncache, thou(ncache), 'results/cache/p{1,2,3}/*.json 条目总数（固定配置下去重的官方评估次数）')

# ---------------------------------------------------------------- 数据特征
def fstat(key, fn, fmt):
    v = [fn(feat[c]) for c in CASES]
    return min(v), st.median(v), max(v)


FEATS = [
    ('NOPS', lambda r: r['n_ops'], lambda x: thou(x)),
    ('DEPTH', lambda r: r['depth'], lambda x: f'{x:g}'),
    ('WIDTH', lambda r: r['avg_width'], lambda x: f'{x:.1f}'),
    ('NCOMP', lambda r: r['n_components'], lambda x: f'{x:g}'),
    ('RHO', lambda r: r['largest_component_frac'], lambda x: f'{x:.3f}'),
    ('CP', lambda r: r['cp_over_total'], lambda x: f'{x:.4f}'),
    ('CDDR', lambda r: r['compute_over_ddr'], lambda x: f'{x:.1f}'),
    ('UBP', lambda r: r['ub_pressure'], lambda x: f'{x:.1f}'),
]
for name, fn, fmt in FEATS:
    a, b, c = fstat(name, fn, fmt)
    put(f'FEAT_{name}_MIN', a, fmt(a), f'results/features.json 最小值（{name}）')
    put(f'FEAT_{name}_MED', b, fmt(b), f'results/features.json 中位数（{name}）')
    put(f'FEAT_{name}_MAX', c, fmt(c), f'results/features.json 最大值（{name}）')
put('N_ONECOMP', sum(1 for c in CASES if feat[c]['n_components'] == 1), str(sum(1 for c in CASES if feat[c]['n_components'] == 1)),
    'features.json n_components==1 的用例数')
put('N_RHO05', sum(1 for c in CASES if feat[c]['largest_component_frac'] >= 0.5),
    str(sum(1 for c in CASES if feat[c]['largest_component_frac'] >= 0.5)), 'features.json largest_component_frac≥0.5 的用例数')
put('N_COMP40', sum(1 for c in CASES if feat[c]['n_components'] >= 40), str(sum(1 for c in CASES if feat[c]['n_components'] >= 40)),
    'features.json n_components≥40 的用例数')
f16 = feat['case_016']
put('C016_NOPS', f16['n_ops'], thou(f16['n_ops']), 'features.json case_016 n_ops')
put('C016_DEPTH', f16['depth'], str(f16['depth']), 'features.json case_016 depth')
put('C016_WIDTH', f16['avg_width'], f'{f16["avg_width"]:.1f}', 'features.json case_016 avg_width')
put('C016_PAR', f16['total_cycles'] / f16['critical_path_cycles'], f'{f16["total_cycles"] / f16["critical_path_cycles"]:.1f}',
    'features.json case_016 total_cycles/critical_path_cycles')
put('C016_SU4', su[(2, 4)]['case_016'], f2(su[(2, 4)]['case_016']), 'final.csv case_016 P2 N=4 speedup')
put('C016_SU4_P1', su[(1, 4)]['case_016'], f2(su[(1, 4)]['case_016']), 'final.csv case_016 P1 N=4 speedup')

# 分层与相关
for p in P:
    for n in ('4',):
        for sk, tag in (('rho<0.2', 'A'), ('0.2<=rho<0.5', 'B'), ('rho>=0.5', 'C')):
            d = S[f'problem{p}']['speedup_by_strata'][n][sk]
            put(f'STRAT_P{p}_{tag}_N', d['n'], str(d['n']), f'summary.json problem{p}.speedup_by_strata["4"]["{sk}"].n')
            put(f'STRAT_P{p}_{tag}_MEAN', d['amean'], f2(d['amean']), f'…["{sk}"].amean')
            put(f'STRAT_P{p}_{tag}_MED', d['median'], f2(d['median']), f'…["{sk}"].median')
            put(f'STRAT_P{p}_{tag}_MIN', d['min'], f2(d['min']), f'…["{sk}"].min')
y = [su[(2, 4)][c] for c in CASES]
CORR = [
    ('RHO', [feat[c]['largest_component_frac'] for c in CASES]),
    ('CP', [feat[c]['cp_over_total'] for c in CASES]),
    ('LWIDTH', [math.log10(feat[c]['avg_width']) for c in CASES]),
    ('LCDDR', [math.log10(feat[c]['compute_over_ddr']) for c in CASES]),
    ('LNOPS', [math.log10(feat[c]['n_ops']) for c in CASES]),
]
for name, x in CORR:
    r, p_ = sps.pearsonr(x, y)
    rho, _ = sps.spearmanr(x, y)
    put(f'CORR_{name}', r, f'{r:+.2f}'.replace('-', '−'), f'features.json × final.csv(P2,N=4) Pearson r（{name}）')
    put(f'SCORR_{name}', rho, f'{rho:+.2f}'.replace('-', '−'), f'features.json × final.csv(P2,N=4) Spearman ρ（{name}）')

# ---------------------------------------------------------------- 基线
BL = [('random', 'B1'), ('topo', 'B2'), ('balance', 'B3'), ('comm', 'B4')]
for p in P:
    for n in NS:
        d = S['baseline_speedup'][f'p{p}_n{n}']
        for a, tag in BL:
            put(f'BL_{tag}_P{p}_N{n}', d[a], f2(d[a]), f'summary.json baseline_speedup["p{p}_n{n}"]["{a}"]（算术平均）')
    d = S['baseline_speedup'][f'p{p}_n4']
    for a, tag in BL:
        imp = d['capls'] / d[a] - 1
        put(f'IMP_{tag}_P{p}', imp, pct(imp, 0, sign=True), f'baseline_speedup p{p}_n4: capls/{a} − 1')
        pr = S['paired'][f'problem{p}'][f'capls_vs_{a}']
        put(f'WTL_{tag}_P{p}', (pr['win'], pr['tie'], pr['loss']), f"{pr['win']}/{pr['tie']}/{pr['loss']}",
            f'summary.json paired.problem{p}.capls_vs_{a} win/tie/loss')
        put(f'PH_{tag}_P{p}', pr['p_holm'], pval(pr['p_holm']), f'summary.json paired.problem{p}.capls_vs_{a}.p_holm（Wilcoxon，Holm 校正）')
    for a, tag in BL:
        put(f'BLFAIL_{tag}_P{p}', S['baseline_failrate'][f'p{p}_{a}'], pct(S['baseline_failrate'][f'p{p}_{a}']),
            f'summary.json baseline_failrate p{p}_{a}')
    put(f'BLADD_B3_P{p}', S['baseline_added_total'][f'p{p}_n4']['balance'], big(S['baseline_added_total'][f'p{p}_n4']['balance']),
        f'summary.json baseline_added_total p{p}_n4 balance')
    put(f'BLADD_B4_P{p}', S['baseline_added_total'][f'p{p}_n4']['comm'], big(S['baseline_added_total'][f'p{p}_n4']['comm']),
        f'summary.json baseline_added_total p{p}_n4 comm')

# 单配置对单配置：ablation2 full_c2 vs B4（通信聚类），N=4
ab2 = read('ablation2.csv')
bl = read('baseline.csv')
for p in P:
    a = {(r['case'], r['num_cores']): float(r['speedup']) for r in ab2
         if int(r['problem']) == p and r['variant'] == 'full_c2' and r['speedup']}
    b = {(r['case'], r['num_cores']): float(r['speedup']) for r in bl
         if int(r['problem']) == p and r['algorithm'] == 'comm' and r['speedup']}
    keys = sorted(k for k in a if k in b and k[1] == '4')
    xa = [a[k] for k in keys]
    xb = [b[k] for k in keys]
    w = sps.wilcoxon(xa, xb, zero_method='wilcox')
    rel = amean(xa) / amean(xb) - 1
    put(f'SC_C2_P{p}', amean(xa), f2(amean(xa)), f'ablation2.csv full_c2 P{p} N=4 speedup 算术平均（n={len(keys)}）')
    put(f'SC_B4_P{p}', amean(xb), f2(amean(xb)), f'baseline.csv comm P{p} N=4 同一批用例的算术平均（n={len(keys)}）')
    put(f'SC_REL_P{p}', rel, pct(rel, 1, sign=True), 'SC_C2/SC_B4 − 1')
    put(f'SC_P_P{p}', w.pvalue, pval(w.pvalue), f'scipy.stats.wilcoxon(full_c2, comm) P{p} N=4')
    put(f'SC_N_P{p}', len(keys), str(len(keys)), '配对用例数')

# ---------------------------------------------------------------- 消融（T16 重建）
AB = ['no_comm', 'no_sync', 'no_localsearch', 'no_level', 'no_level_no_comm', 'max_ops500',
      'op_full', 'op_mu0', 'op_nu0', 'op_alpha1', 'lvl_alap', 'lvl_compress']
for p in P:
    d = S['ablation2'][f'problem{p}']
    put(f'AB_P{p}_full_c2', d['full_c2']['describe']['amean'], f3(d['full_c2']['describe']['amean']),
        f'summary.json ablation2.problem{p}.full_c2.describe.amean')
    put(f'AB_P{p}_n', d['full_c2']['describe']['n'] // 4, str(d['full_c2']['describe']['n'] // 4),
        f'summary.json ablation2.problem{p}.full_c2.describe.n / 4（用例数）')
    for v in AB:
        if v not in d:
            continue
        put(f'AB_P{p}_{v}', d[v]['describe']['amean'], f3(d[v]['describe']['amean']),
            f'summary.json ablation2.problem{p}.{v}.describe.amean')
        put(f'ABR_P{p}_{v}', d[v]['paired']['rel'], pct(d[v]['paired']['rel'], 1, sign=True),
            f'summary.json ablation2.problem{p}.{v}.paired.rel')
        put(f'ABP_P{p}_{v}', d[v]['paired']['p_holm'], pval(d[v]['paired']['p_holm']),
            f'summary.json ablation2.problem{p}.{v}.paired.p_holm')

# ---------------------------------------------------------------- 粒度
gr = read('granularity.csv')
gcases = sorted(set(r['case'] for r in gr))
put('GRAN_N', len(gcases), str(len(gcases)), 'results/granularity.csv 用例数')
betas = ['0.03', '0.06', '0.12', '0.25', '0.5', '1.0', '2.0']
gm = {}
for p in P:
    for b in betas:
        v = [float(r['speedup']) for r in gr if int(r['problem']) == p and r['variant'] == b]
        gm[(p, b)] = amean(v)
        put(f'GRAN_P{p}_{b}', amean(v), f2(amean(v)), f'granularity.csv P{p} β={b} speedup 算术平均（{len(v)} 个用例，N=4）')
    bb = max(betas, key=lambda b: gm[(p, b)])
    put(f'GRAN_BEST_P{p}', bb, f'{float(bb):g}', f'granularity.csv P{p} 算术平均最大的 β')
    for b in ('0.03', '2.0', '0.25', '0.5'):
        loss = 1 - gm[(p, b)] / gm[(p, bb)]
        put(f'GRAN_LOSS_P{p}_{b}', loss, pct(loss, 1), f'1 − GRAN_P{p}_{b}/GRAN_P{p}_best')
    rng_ = [gm[(p, b)] for b in ('0.12', '0.25', '0.5')]
    put(f'GRAN_PLAT_P{p}', max(rng_) / min(rng_) - 1, pct(max(rng_) / min(rng_) - 1, 1),
        f'granularity.csv P{p} β∈[0.12,0.5] 内最大/最小 − 1')

# ---------------------------------------------------------------- 硬件敏感性
se = read('sensitivity.csv')
defmk = {}
for r in se:
    if r['is_default'] == 'True':
        defmk[(r['case'], r['knob'], r['problem'])] = int(r['makespan'])
mult = defaultdict(list)
for r in se:
    if r['feasible'] != 'True':
        continue
    d = defmk[(r['case'], r['knob'], r['problem'])]
    mult[(r['knob'], r['value'])].append(d / int(r['makespan']))
put('SENS_N', len(set(r['case'] for r in se)), str(len(set(r['case'] for r in se))), 'sensitivity.csv 用例数')
knob_vals = defaultdict(list)
for (k, v) in mult:
    knob_vals[k].append(v)
SENS = {}
for k, vs in knob_vals.items():
    vs = sorted(vs, key=float)
    SENS[k] = [(v, gmean(mult[(k, v)])) for v in vs]
    for v in vs:
        put(f'SENS_{k}_{v}', gmean(mult[(k, v)]), f3(gmean(mult[(k, v)])),
            f'sensitivity.csv knob={k} value={v}：几何平均（默认 makespan / 该取值 makespan）')

# ---------------------------------------------------------------- 问题 3：L2
for n in ('1', '2', '3', '4', '5'):
    put(f'L2G_N{n}', S['l2_gain'][n], f3(S['l2_gain'][n]), f'summary.json l2_gain["{n}"]（同一方案 P2/P3 makespan 比的算术平均，p3_compare.csv）')
    put(f'L2H_N{n}', S['l2_hit_rate'][n], pct(S['l2_hit_rate'][n]), f'summary.json l2_hit_rate["{n}"]（按字节命中率均值）')
    put(f'L2GT_N{n}', S['l2_gain_gt1pct'][n], str(S['l2_gain_gt1pct'][n]), f'summary.json l2_gain_gt1pct["{n}"]')
    put(f'L2MAX_N{n}', S['l2_gain_max'][n], f2(S['l2_gain_max'][n]), f'summary.json l2_gain_max["{n}"]')
    put(f'L2MAXC_N{n}', S['l2_gain_maxcase'][n], S['l2_gain_maxcase'][n], f'summary.json l2_gain_maxcase["{n}"]')
    put(f'L2NZ_N{n}', S['l2_hit_nonzero'][n], str(S['l2_hit_nonzero'][n]), f'summary.json l2_hit_nonzero["{n}"]')
    put(f'L2HMAX_N{n}', S['l2_hit_max'][n], pct(S['l2_hit_max'][n], 0), f'summary.json l2_hit_max["{n}"]')
ls = json.loads((RES / 'l2_sources.json').read_text(encoding='utf-8'))['by_n']['4']
hitt = ls['official_hit_bytes']
misst = ls['official_miss_bytes']
for k in ('hit_input_reuse', 'hit_cross_core_mid', 'hit_spill_reload'):
    put(f'L2S_{k}', ls[k] / hitt, pct(ls[k] / hitt), f'l2_sources.json by_n["4"].{k}/official_hit_bytes')
for k in ('miss_first_miss', 'miss_concurrent_first_read', 'miss_fifo_evicted', 'miss_oversize'):
    put(f'L2S_{k}', ls[k] / misst, pct(ls[k] / misst), f'l2_sources.json by_n["4"].{k}/official_miss_bytes')
# 赛题口径：无 L2（问题 2 评估器下的最终方案）对只读 Cache（问题 3 评估器下的最终方案）
n1 = read('n1.csv')
n1mk = {(int(r['problem']), r['case']): int(r['makespan']) for r in n1}
n1hit = {r['case']: float(r['cache_hit_rate'] or 0) for r in n1 if r['problem'] == '3'}
hitmap = {(r['case'], int(r['num_cores'])): float(r['cache_hit_rate'] or 0) for r in final if r['problem'] == '3'}
CMP = {}
for n in (1, 2, 3, 4, 5):
    g_, h_, su_nol2, su_l2 = [], [], [], []
    for c in CASES:
        base = single[c]['makespan']
        if n == 1:
            a, b, h = n1mk[(2, c)], n1mk[(3, c)], n1hit[c]
        else:
            a, b, h = mk[(2, n)][c], mk[(3, n)][c], hitmap[(c, n)]
        g_.append(a / b)
        h_.append(h)
        su_nol2.append(base / a)
        su_l2.append(base / b)
    CMP[n] = (g_, h_, su_nol2, su_l2)
    put(f'CG_N{n}', amean(g_), f3(amean(g_)), f'N={n}：逐用例 MK(无 L2)/MK(只读 Cache) 的算术平均；N≥2 取 final.csv 问题 2/3 冠军，N=1 取 n1.csv')
    put(f'CGMAX_N{n}', max(g_), f2(max(g_)), '同上最大值')
    put(f'CGMAXC_N{n}', CASES[g_.index(max(g_))], CASES[g_.index(max(g_))], '同上最大值所在用例')
    put(f'CGGT_N{n}', sum(x > 1.01 for x in g_), str(sum(x > 1.01 for x in g_)), '同上 >1.01 的用例数')
    put(f'CGLT_N{n}', sum(x < 1 for x in g_), str(sum(x < 1 for x in g_)), '同上 <1 的用例数')
    put(f'CH_N{n}', amean(h_), pct(amean(h_)), f'N={n}：只读 Cache 配置下 cache_hit_rate 的算术平均（final.csv P3 / n1.csv）')
    put(f'CSU_NOL2_N{n}', amean(su_nol2), f2(amean(su_nol2)), f'N={n}：无 L2 配置相对单核基准的平均加速比')
    put(f'CSU_L2_N{n}', amean(su_l2), f2(amean(su_l2)), f'N={n}：只读 Cache 配置相对单核基准（无 L2）的平均加速比')
(OUT / 'p3_compare_final.json').write_text(json.dumps({n: {'gain': v[0], 'hit': v[1]} for n, v in CMP.items()}), encoding='utf-8')
put('N1_EQ_P1', sum(1 for c in CASES if n1mk[(1, c)] == single[c]['makespan']), str(sum(1 for c in CASES if n1mk[(1, c)] == single[c]['makespan'])),
    'n1.csv：问题 1 评估器下整图单核方案 makespan 与官方单核基准相等的用例数')

l2rows = read('l2_sources.csv')
put('L2S_CONFIGS', len(l2rows), str(len(l2rows)), 'l2_sources.csv 行数')

# ---------------------------------------------------------------- 运行时间
rt = S['runtime']
put('RT_MED', rt['median'], f'{rt["median"]:.2f}', 'summary.json runtime.median（单候选 S1–S3 算法时间，秒）')
put('RT_P95', rt['p95'], f'{rt["p95"]:.1f}', 'summary.json runtime.p95')
put('RT_MAX', rt['max'], f'{rt["max"]:.1f}', 'summary.json runtime.max')
put('RT_N', rt['n'], thou(rt['n']), 'summary.json runtime.n')
put('EVAL_MAX', S['eval_time']['max'], thou(S['eval_time']['max']), 'summary.json eval_time.max（秒）')
main = read('main.csv')
A = defaultdict(float)
E = defaultdict(float)
SA = defaultdict(float)
for r in main:
    if r['variant'] == '_best':
        continue
    k = (int(r['problem']), r['case'], r['num_cores'])
    A[k] += float(r['runtime_s'] or 0)
    E[k] += float(r['eval_s'] or 0)
    pr = json.loads(r['params'] or '{}') if r.get('params') else {}
    if 'anneal_seconds' in pr:
        SA[k] = max(SA[k], pr['anneal_seconds'])
TT = {k: A[k] + E[k] + SA[k] for k in A}
per_case_p1 = {}
for p in P:
    v = sorted(x for k, x in TT.items() if k[0] == p)
    put(f'E2E_MED_P{p}', st.median(v), f'{st.median(v):.1f}', f'main.csv P{p}：每个 (用例,N) 的 Σruntime_s+Σeval_s(+退火秒数) 中位数')
    put(f'E2E_P90_P{p}', v[int(0.9 * len(v))], thou(v[int(0.9 * len(v))]), f'同上 90 分位')
    put(f'E2E_MAX_P{p}', v[-1], thou(v[-1]), f'同上最大值')
    put(f'E2E_LE300_P{p}', sum(x <= 300 for x in v), str(sum(x <= 300 for x in v)), f'同上 ≤300 s 的配置数（共 {len(v)}）')
    put(f'E2E_LE600_P{p}', sum(x <= 600 for x in v), str(sum(x <= 600 for x in v)), f'同上 ≤600 s 的配置数（共 {len(v)}）')
    alg = sorted(A[k] + SA[k] for k in A if k[0] == p)
    put(f'ALG_MED_P{p}', st.median(alg), f'{st.median(alg):.1f}', f'main.csv P{p}：每个 (用例,N) 的 Σruntime_s(+退火) 中位数（不含官方评估）')
    put(f'ALG_LE600_P{p}', sum(x <= 600 for x in alg), str(sum(x <= 600 for x in alg)), f'同上 ≤600 s 的配置数')
    put(f'ALG_MAX_P{p}', alg[-1], thou(alg[-1]), f'同上最大值')
pc = defaultdict(float)
for (p, c, n), x in TT.items():
    if p == 1:
        pc[c] = max(pc[c], x)
over = sorted([c for c in pc if pc[c] > 600])
put('E2E_P1_OVER_CASES', over, '、'.join(o.replace('case_', '') for o in over), 'P1 任一 N 端到端 >600 s 的用例')
put('E2E_P1_OVER_N', len(over), str(len(over)), '上述用例数')
v = sorted(x for k, x in TT.items() if k[0] == 1 and k[1] not in ('case_014', 'case_072', 'case_076', 'case_091'))
put('E2E_P1_NOBIG_LE600', sum(x <= 600 for x in v), str(sum(x <= 600 for x in v)), 'P1 去掉 4 个大图后 ≤600 s 的配置数')
put('E2E_P1_NOBIG_N', len(v), str(len(v)), 'P1 去掉 4 个大图后的配置数')
big4 = {c: max(TT[(1, c, n)] for n in ('2', '3', '4', '5')) for c in ('case_014', 'case_072', 'case_076', 'case_091')}
put('E2E_BIG4_MAX', max(big4.values()), thou(max(big4.values())), '4 个大图 P1 端到端最大值（秒）')
put('E2E_BIG4_MIN', min(big4.values()), thou(min(big4.values())), '4 个大图 P1 端到端（逐用例最大 N）中的最小值（秒）')
an = json.loads((RES / 'p1_anneal_report.json').read_text(encoding='utf-8'))
put('SA_MED', an['anneal_seconds']['median'], f"{an['anneal_seconds']['median']:.1f}", 'p1_anneal_report.json anneal_seconds.median')
put('SA_MAX', an['anneal_seconds']['max'], thou(an['anneal_seconds']['max']), 'p1_anneal_report.json anneal_seconds.max')
put('SA_OVER60', an['anneal_seconds']['configs_over_limit'], str(an['anneal_seconds']['configs_over_limit']),
    'p1_anneal_report.json anneal_seconds.configs_over_limit（>60 s）')
put('SA_ITERS', an['anneal_iters'], str(an['anneal_iters']), 'p1_anneal_report.json anneal_iters')
put('SA_CHAMP_MAIN', an['sa_champion_configs_main'], str(an['sa_champion_configs_main']), 'p1_anneal_report.json sa_champion_configs_main')
fe = json.loads((RES / 'fasteval_slow_case_verification.json').read_text(encoding='utf-8'))
mx = max(fe['candidates'], key=lambda c: c['official_cached_s'])
put('BIGEVAL_MAX', mx['official_cached_s'], thou(mx['official_cached_s']), 'fasteval_slow_case_verification.json 最慢一次官方评估（秒）')
put('BIGEVAL_CASE', f"{mx['case']}（N={mx['num_cores']}）", f"{mx['case']}（N={mx['num_cores']}）", '同上')

# ---------------------------------------------------------------- 代理检验
for tag, fn in (('LEG', 'model_validation_summary_legacy.json'), ('SIM', 'model_validation_summary_sim.json')):
    d = json.loads((RES / fn).read_text(encoding='utf-8'))
    for p in P:
        q = d[f'problem{p}']
        put(f'PX_{tag}_P{p}_SP', q['spearman_median'], f2(q['spearman_median']), f'{fn} problem{p}.spearman_median')
        put(f'PX_{tag}_P{p}_KT', q['kendall_median'], f2(q['kendall_median']), f'{fn} problem{p}.kendall_median')
        put(f'PX_{tag}_P{p}_POOL', q['pooled_spearman'], f2(q['pooled_spearman']), f'{fn} problem{p}.pooled_spearman')
        for k in ('recall1', 'recall3', 'recall5'):
            put(f'PX_{tag}_P{p}_{k}', q[k], pct(q[k], 0), f'{fn} problem{p}.{k}')
        for k in ('top1_slowdown_p90', 'top3_slowdown_p90', 'top1_slowdown_max'):
            put(f'PX_{tag}_P{p}_{k}', q[k], pct(q[k], 1), f'{fn} problem{p}.{k}')

pa = json.loads((RES / 'portfolio_analysis.json').read_text(encoding='utf-8'))
for p in P:
    q = pa['proxy_selection'][f'P{p}']
    put(f'PSEL_P{p}_PROXY', q['proxy_only_amean'], f2(q['proxy_only_amean']), f'portfolio_analysis.json proxy_selection.P{p}.proxy_only_amean')
    put(f'PSEL_P{p}_OFF', q['official_main_amean'], f2(q['official_main_amean']), f'… official_main_amean')
    put(f'PSEL_P{p}_CH', q['champion_amean'], f2(q['champion_amean']), f'… champion_amean')
    g = pa['greedy'][f'P{p}']
    for row in g[:4]:
        put(f'GR_P{p}_K{row["k"]}', row['amean'], f3(row['amean']), f'portfolio_analysis.json greedy.P{p}[k={row["k"]}]（{row["label"]}）')
    put(f'GR_P{p}_KLAST', g[-1]['amean'], f3(g[-1]['amean']), f'portfolio_analysis.json greedy.P{p} 最后一步')
    put(f'GR_P{p}_NLAST', g[-1]['k'], str(g[-1]['k']), f'portfolio_analysis.json greedy.P{p} 步数')
cv = S['cv_select']
cvl = [cv['problems'][f'problem{p}'][f][k] for p in P for f in ('train_A', 'train_B') for k in ('out_of_fold_loss',)]
put('CV_LOSS_MAX', max(cvl), pct(max(cvl), 1), 'summary.json cv_select 各问题各折 out_of_fold_loss 最大值')

# ---------------------------------------------------------------- T11/T13
om = json.loads((RES / 'op_mode_report.json').read_text(encoding='utf-8'))
put('OP_FEAS', f"{om['op_candidates_feasible']}/{om['op_candidates_total']}", f"{om['op_candidates_feasible']}/{om['op_candidates_total']}",
    'op_mode_report.json op_candidates_feasible/total')
put('OP_SPILL_BEFORE', om['p2_n4_spill_champions_before_T11'], big(om['p2_n4_spill_champions_before_T11']),
    'op_mode_report.json p2_n4_spill_champions_before_T11')
put('OP_SPILL_AFTER', om['p2_n4_spill_champions_after_T11'], big(om['p2_n4_spill_champions_after_T11']),
    'op_mode_report.json p2_n4_spill_champions_after_T11')
put('OP_SPILL_DROP', om['spill_drop_frac'], pct(om['spill_drop_frac'], 0), 'op_mode_report.json spill_drop_frac')
mm = om['mu1_vs_mu0_paired']
put('OP_MU_REL', mm['rel'], pct(mm['rel'], 1, sign=True), 'op_mode_report.json mu1_vs_mu0_paired.rel')
put('OP_MU_WTL', f"{mm['win']}/{mm['tie']}/{mm['loss']}", f"{mm['win']}/{mm['tie']}/{mm['loss']}", 'op_mode_report.json mu1_vs_mu0_paired')
put('OP_MU_P', mm['p'], pval(mm['p']), 'op_mode_report.json mu1_vs_mu0_paired.p')
sr = json.loads((RES / 'sampling_report.json').read_text(encoding='utf-8'))
put('SMP_EVALS', sr['new_official_evals'], thou(sr['new_official_evals']), 'sampling_report.json new_official_evals')
put('SMP_CHAMP', sr['champion_s_configs'], str(sr['champion_s_configs']), 'sampling_report.json champion_s_configs')

# ---------------------------------------------------------------- 下界
bd = json.loads((RES / 'bounds.json').read_text(encoding='utf-8'))
for p in P:
    for n in NS:
        q = bd['ratio'][f'p{p}_n{n}']
        put(f'LB_P{p}_N{n}', q['amean'], f2(q['amean']), f'bounds.json ratio.p{p}_n{n}.amean（MK/LB）')
        put(f'LBMED_P{p}_N{n}', q['median'], f2(q['median']), f'bounds.json ratio.p{p}_n{n}.median')
        e = bd['efficiency'][f'p{p}_n{n}']
        put(f'LBEFF_P{p}_N{n}', e['amean'], f2(e['amean']), f'bounds.json efficiency.p{p}_n{n}.amean（单核归一化效率）')
        u = bd['upper_bound'][f'p{p}_n{n}']['fraction_of_upper']
        put(f'LBUP_P{p}_N{n}', u['amean'], pct(u['amean'], 0), f'bounds.json upper_bound.p{p}_n{n}.fraction_of_upper.amean')


for p in P:
    for n in NS:
        su_up = bd['upper_bound'][f'p{p}_n{n}']['speedup_upper']
        put(f'SUUP_P{p}_N{n}', su_up['amean'], f2(su_up['amean']),
            f'bounds.json upper_bound.p{p}_n{n}.speedup_upper.amean（MK_1/LB_N）')
put('SC_OVER_LB1', bd['single_over_lb1_median'], f2(bd['single_over_lb1_median']),
    'bounds.json single_over_lb1_median（单核基准 / 单核下界 的中位数）')

# 规模分档（问题一候选裁剪）
_nops = [r['n_ops'] for r in json.loads((RES / 'features.json').read_text(encoding='utf-8'))]
put('N_BIG12K', sum(x > 12000 for x in _nops), str(sum(x > 12000 for x in _nops)),
    'features.json n_ops>12000 的用例数（问题一只评估前 4 个候选）')
put('N_MID6K', sum(6000 < x <= 12000 for x in _nops), str(sum(6000 < x <= 12000 for x in _nops)),
    'features.json 6000<n_ops≤12000 的用例数（问题一只评估前 8 个候选）')
put('N_SMALL6K', sum(x <= 6000 for x in _nops), str(sum(x <= 6000 for x in _nops)),
    'features.json n_ops≤6000 的用例数')
_tc = read('traffic_model_check.csv')
put('TRAFFIC_CASES', len({r['case'] for r in _tc}), str(len({r['case'] for r in _tc})),
    'traffic_model_check.csv 不同用例数（N=4，三个问题）')
_te = max(float(r['rel_err']) for r in _tc)
put('TRAFFIC_MAXERR', _te, pct(_te, 4), 'traffic_model_check.csv rel_err 最大值')

# 大图代理兜底的 4 个用例在问题一的最终加速比
_BIG4 = ['case_014', 'case_072', 'case_076', 'case_091']
for n in NS:
    _v = [float(r['speedup']) for r in final if r['problem'] == '1' and r['num_cores'] == str(n) and r['case'] in _BIG4]
    put(f'BIG4_SUMIN_N{n}', min(_v), f2(min(_v)), f'final.csv P1 N={n} 四个大图（014/072/076/091）speedup 最小值')
    put(f'BIG4_SUMAX_N{n}', max(_v), f2(max(_v)), f'final.csv P1 N={n} 四个大图 speedup 最大值')
_pa = json.loads((RES / 'portfolio_analysis.json').read_text(encoding='utf-8'))['proxy_selection']
for p in P:
    _x = _pa[f'P{p}']['proxy_vs_official_main']
    put(f'PSEL_P{p}_LOSSN', _x['loss'], str(_x['loss']), f'portfolio_analysis.json proxy_selection.P{p}.proxy_vs_official_main.loss（N=4，代理选择劣于官方择优的用例数）')
    put(f'PSEL_P{p}_REL', _x['rel'], pct(_x['rel'], 1, sign=True), f'portfolio_analysis.json proxy_selection.P{p}.proxy_vs_official_main.rel')

# 退火超过 60 s 的配置按核数分布（main.csv params.anneal_seconds）
_sa = set()
for r in read('main.csv'):
    if r['problem'] != '1' or not r.get('params'):
        continue
    _prm = json.loads(r['params'])
    if 'anneal_seconds' in _prm:
        _sa.add((r['case'], r['num_cores'], _prm['anneal_seconds']))
_over = [x for x in _sa if x[2] > 60]
_n23 = sum(x[1] in ('2', '3') for x in _over)
put('SA_OVER60_N23', _n23, str(_n23), 'main.csv P1 params.anneal_seconds>60 且 N∈{2,3} 的配置数')
put('SA_OVER60_CASES', len({x[0] for x in _over}), str(len({x[0] for x in _over})), 'main.csv P1 退火超过 60 s 的不同用例数')

# 优先级采样：K=0 与 K=16 的 N=4 平均加速比（sampling_report.json by_K）
_sr = json.loads((RES / 'sampling_report.json').read_text(encoding='utf-8'))
for p in (2, 3):
    for k in ('0', '16'):
        _v = _sr['by_K'][k][f'P{p}_N4']
        put(f'SMP_K{k}_P{p}_N4', _v, f2(_v), f'sampling_report.json by_K[{k}].P{p}_N4')
_om = json.loads((RES / 'op_mode_report.json').read_text(encoding='utf-8'))
put('OP_CHAMP', _om['op_champion_configs'], str(_om['op_champion_configs']), 'op_mode_report.json op_champion_configs（主实验中单算子子图候选成为冠军的配置数，问题二、三共 800 个）')

_r = F['ADD_P2_N4']['raw'] / F['SC_SPILL_TOTAL']['raw']
put('ADD_OVER_SC_P2N4', _r, pct(_r, 0), 'ADD_P2_N4 / SC_SPILL_TOTAL')

# 敏感性样本（18 个用例）相对全体的 L2 收益代表性（N=4，final.csv 冠军）
_sens_cases = sorted({r['case'] for r in read('sensitivity.csv')})
_mk = {(r['case'], r['problem'], r['num_cores']): float(r['makespan']) for r in final}
_cg4 = {c: _mk[(c, '2', '4')] / _mk[(c, '3', '4')] for c in {r['case'] for r in final}}
_hr4 = {r['case']: float(r['cache_hit_rate'] or 0) for r in final if r['problem'] == '3' and r['num_cores'] == '4'}
_v = sum(_cg4[c] for c in _sens_cases) / len(_sens_cases)
put('SENS_SAMPLE_CG4', _v, f3(_v), 'sensitivity.csv 的 18 个用例在 final.csv 上 N=4 的 MK(P2)/MK(P3) 算术平均')
_v = sum(_hr4[c] for c in _sens_cases) / len(_sens_cases)
put('SENS_SAMPLE_HIT4', _v, pct(_v), 'sensitivity.csv 的 18 个用例在 final.csv P3 N=4 的 cache_hit_rate 算术平均')
_top = sorted(_cg4, key=lambda c: -_cg4[c])[:10]
put('SENS_TOP10_IN', sum(c in _sens_cases for c in _top), str(sum(c in _sens_cases for c in _top)),
    'final.csv N=4 Cache 加速比最高的 10 个用例中落在敏感性样本内的个数')

# 表调度各项的作用：以 op_full 为基准的配对比较（ablation2.csv，N=2..5，Wilcoxon + Holm）
_ab = defaultdict(dict)
for r in read('ablation2.csv'):
    if r['feasible'] == 'True' and r['speedup']:
        _ab[(r['problem'], r['variant'])][(r['case'], r['num_cores'])] = float(r['speedup'])
_raw = {}
for p in (2, 3):
    base = _ab[(str(p), 'op_full')]
    for v in ('op_mu0', 'op_nu0', 'op_alpha1'):
        oth = _ab[(str(p), v)]
        keys = sorted(set(base) & set(oth))
        d = [math.log(oth[k]) - math.log(base[k]) for k in keys]
        rel = (sum(oth[k] for k in keys) / len(keys)) / (sum(base[k] for k in keys) / len(keys)) - 1
        _p = float(sps.wilcoxon(d, zero_method='wilcox').pvalue) if any(d) else 1.0
        _raw[(p, v)] = (rel, _p, len(keys))
_items = sorted(_raw.items(), key=lambda kv: kv[1][1])
_m, _run = len(_items), 0.0
for i, ((p, v), (rel, _p, n)) in enumerate(_items):
    _run = max(_run, min(1.0, (_m - i) * _p))
    put(f'OPV_P{p}_{v}', rel, pct(rel, 1, sign=True), f'ablation2.csv P{p}：{v} 相对 op_full 的算术平均加速比变化（N=2..5 配对，n={n}）')
    put(f'OPVP_P{p}_{v}', _run, pval(_run), f'同上 Wilcoxon 符号秩检验（对数差），6 个比较 Holm 校正')

# 问题一超过 10 分钟的配置：耗时构成（main.csv，串行累加口径同 E2E_*）
_ev, _rt, _sa2 = defaultdict(float), defaultdict(float), defaultdict(float)
for r in read('main.csv'):
    if r['problem'] != '1' or r['variant'] == '_best':
        continue
    k = (r['case'], r['num_cores'])
    _ev[k] += float(r['eval_s'] or 0)
    _rt[k] += float(r['runtime_s'] or 0)
    _prm = json.loads(r['params']) if r.get('params') else {}
    if 'anneal_seconds' in _prm:
        _sa2[k] = max(_sa2[k], _prm['anneal_seconds'])
_tot = {k: _ev[k] + _rt[k] + _sa2[k] for k in _ev}
for tag, sel in (('NOBIG', lambda k: _tot[k] > 600 and k[0] not in _BIG4), ('BIG4', lambda k: k[0] in _BIG4)):
    ks = [k for k in _tot if sel(k)]
    T = sum(_tot[k] for k in ks)
    put(f'OVER_{tag}_N', len(ks), str(len(ks)), f'main.csv P1 {tag} 超时配置数（NOBIG：>600 s 且不含四个大图；BIG4：四个大图全部配置）')
    put(f'OVER_{tag}_EVAL', sum(_ev[k] for k in ks) / T, pct(sum(_ev[k] for k in ks) / T, 0), f'{tag} 配置耗时中官方评估的占比')
    put(f'OVER_{tag}_SA', sum(_sa2[k] for k in ks) / T, pct(sum(_sa2[k] for k in ks) / T, 0), f'{tag} 配置耗时中退火的占比')
    put(f'OVER_{tag}_BUILD', sum(_rt[k] for k in ks) / T, pct(sum(_rt[k] for k in ks) / T, 0), f'{tag} 配置耗时中候选构造的占比')

_ao = sorted({k[0] for k in _rt if _rt[k] + _sa2[k] > 600})
put('ALG_OVER_N', sum(1 for k in _rt if _rt[k] + _sa2[k] > 600), str(sum(1 for k in _rt if _rt[k] + _sa2[k] > 600)), 'main.csv P1 不含评估耗时 >600 s 的配置数')
put('ALG_OVER_CASES', _ao, '、'.join(c.replace('case_', '') for c in _ao), 'main.csv P1 不含评估耗时 >600 s 的用例')

(OUT / 'facts.json').write_text(json.dumps(F, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
(OUT / 'sens_table.json').write_text(json.dumps(SENS, ensure_ascii=False), encoding='utf-8')
print('facts', len(F))
