"""把论文中的 @@占位符@@ 用 results/summary.json 的实测数字替换。

    python solution/fill_paper.py paper/论文.md -o paper/论文_final.md

设计意图：论文正文里的每一个数字都必须能追溯到实验记录，禁止手工填写。
脚本会列出所有未被替换的占位符并以非零码退出，避免"漏填"悄悄发生。
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from npu import paths, plots, stats                             # noqa: E402


def _curve(d, keys=(1, 2, 3, 4, 5), unit_at_one=True):
    """N=1 按题目定义恒为 1.00（单核基准自身）。"""
    out = []
    for k in keys:
        if k == 1 and unit_at_one:
            out.append('1.00')
            continue
        v = d.get(str(k), d.get(k))
        out.append('{:.2f}'.format(v) if v else '--')
    return ' / '.join(out)


def build_values() -> dict:
    s = json.loads((paths.RESULTS_DIR / 'summary.json').read_text(encoding='utf-8'))
    s_all = s
    v = {}
    for p in (1, 2, 3):
        key = f'problem{p}'
        g = s.get(key, {}).get('speedup_mean', {})
        v[f'P{p}_CURVE'] = _curve(g)
        for n in (2, 3, 4, 5):
            val = g.get(str(n), g.get(n))
            v[f'P{p}_SU_N{n}'] = '{:.2f}'.format(val) if val else '--'
        geo = s.get(key, {}).get('speedup_geomean', {})
        for n in (2, 3, 4, 5):
            val = geo.get(str(n), geo.get(n))
            v[f'P{p}_GEO_N{n}'] = '{:.2f}'.format(val) if val else '--'
        ci = s.get(key, {}).get('speedup_ci', {})
        ci4 = ci.get('4', ci.get(4))
        v[f'P{p}_CI_N4'] = '[{:.2f}, {:.2f}]'.format(*ci4) if ci4 else '--'
        strat = s.get(key, {}).get('speedup_by_strata', {})
        s4 = strat.get('4', strat.get(4, {}))
        v[f'P{p}_SU_N4_STRATA'] = ' / '.join(
            '{:.2f}'.format(s4[k]['amean']) if s4.get(k, {}).get('n') else '--'
            for k in stats.STRATA)
        med = s.get(key, {}).get('speedup_median', {})
        v[f'P{p}_MED_N4'] = '{:.2f}'.format(med.get('4', med.get(4, 0)) or 0)
        mx = s.get(key, {}).get('speedup_max', {})
        v[f'P{p}_MAX_N4'] = '{:.2f}'.format(mx.get('4', mx.get(4, 0)) or 0)
        mn = s.get(key, {}).get('speedup_min', {})
        v[f'P{p}_MIN_N4'] = '{:.2f}'.format(mn.get('4', mn.get(4, 0)) or 0)

    gain = s.get('l2_gain', {})
    v['L2_GAIN_N4'] = '{:.3f}'.format(gain.get('4', gain.get(4, 0)) or 0)
    v['L2_GAIN_CURVE'] = _curve(gain, unit_at_one=False)
    v['L2_GAIN_CURVE3'] = ' / '.join(
        '{:.3f}'.format(gain.get(str(k), gain.get(k, 0)) or 0) for k in (1, 2, 3, 4, 5))
    v['L2_GAIN_MAX'] = '{:.2f}'.format(
        (s.get('l2_gain_max', {}) or {}).get('4', 0) or 0)
    hit = s.get('l2_hit_rate', {})
    v['HIT_N4'] = '{:.1%}'.format(hit.get('4', hit.get(4, 0)) or 0)
    v['L2_GAIN_ROW'] = ' | '.join(
        '{:.3f}'.format(gain.get(str(k), gain.get(k, 0)) or 0) for k in (1, 2, 3, 4, 5))
    v['HIT_ROW'] = ' | '.join(
        '{:.1%}'.format(hit.get(str(k), hit.get(k, 0)) or 0) for k in (1, 2, 3, 4, 5))
    v['HIT_CURVE'] = ' / '.join(
        '{:.1%}'.format(hit.get(str(k), hit.get(k, 0)) or 0) for k in (1, 2, 3, 4, 5))

    base = s.get('baseline_speedup', {}).get('p2_n4', {})
    ours = base.get('capls')
    if ours:
        parts = []
        for name, label in (('random', '随机'), ('topo', '拓扑等分'),
                            ('balance', '负载均衡'), ('comm', '通信聚类')):
            if base.get(name):
                parts.append('{} {:+.0%}'.format(label, ours / base[name] - 1))
        v['GAIN_VS_BASE'] = '、'.join(parts)
    abl = s.get('ablation', {})
    for p in (1, 2, 3):
        d = abl.get(f'problem{p}', {})
        if d.get('full') and d.get('no_level'):
            v[f'ABL_LEVEL_P{p}'] = '{:.1%}'.format(1 - d['no_level'] / d['full'])
    d2 = abl.get('problem2', {})
    if d2.get('full') and d2.get('no_level'):
        v['ABL_LEVEL'] = '{:.1%}'.format(1 - d2['no_level'] / d2['full'])
    rt = s.get('runtime', {})
    v['RUNTIME_N'] = '{:,}'.format(rt.get('n', 0))
    v['RUNTIME_MED'] = '{:.2f}'.format(rt.get('median', 0))
    v['RUNTIME_P95'] = '{:.1f}'.format(rt.get('p95', 0))
    v['RUNTIME_MAX'] = '{:.1f}'.format(rt.get('max', 0))

    # --- 表格：基线对比 ---
    names = [('random', 'B1 随机（官方 stub）'), ('topo', 'B2 拓扑等分'),
             ('balance', 'B3 负载均衡'), ('comm', 'B4 通信聚类'),
             ('capls', '**CAP-LS（本文）**')]
    lines = ['| 算法 | 问题 1 | 问题 2 | 问题 3 |', '|---|---|---|---|']
    for key, label in names:
        cells = []
        for p in (1, 2, 3):
            d = s_all.get('baseline_speedup', {}).get(f'p{p}_n4', {})
            cells.append('{:.2f}'.format(d[key]) if d.get(key) else '--')
        lines.append('| {} | {} |'.format(label, ' | '.join(cells)))
    fail = s_all.get('baseline_failrate', {})
    if fail:
        cells = []
        for p in (1, 2, 3):
            vals = [fail.get(f'p{p}_{k}') for k, _ in names[:4]]
            vals = [x for x in vals if x is not None]
            cells.append('{:.1%}'.format(max(vals)) if vals else '--')
        lines.append('| 基线不可行率（最大） | {} |'.format(' | '.join(cells)))
    v['TABLE_BASELINE'] = chr(10).join(lines)

    # --- 表格：消融 ---
    order = ['full', 'no_level', 'no_sync', 'no_comm', 'no_balance',
             'no_localsearch', 'no_cache_aware']
    label = {'full': '完整 CAP-LS', 'no_level': '去同步层次分层',
             'no_sync': '去同步深度代价', 'no_comm': '去通信感知切图',
             'no_balance': '去负载均衡', 'no_localsearch': '去局部搜索',
             'no_cache_aware': '去 L2 感知'}
    lines = ['| 变体 | 问题 1 | 问题 2 | 问题 3 |', '|---|---|---|---|']
    for name in order:
        cells = []
        for p in (1, 2, 3):
            d = s_all.get('ablation', {}).get(f'problem{p}', {})
            if d.get(name):
                delta = (d[name] / d['full'] - 1) if d.get('full') else 0
                cells.append('{:.2f}（{:+.1%}）'.format(d[name], delta)
                             if name != 'full' else '{:.2f}'.format(d[name]))
            else:
                cells.append('--')
        lines.append('| {} | {} |'.format(label[name], ' | '.join(cells)))
    v['TABLE_ABLATION'] = chr(10).join(lines)

    # --- 表格：配对比较（N=4，Holm 校正后的 p 值）---
    pair_rows = [('capls_vs_random', 'CAP-LS 对 B1 随机'),
                 ('capls_vs_topo', 'CAP-LS 对 B2 拓扑等分'),
                 ('capls_vs_balance', 'CAP-LS 对 B3 负载均衡'),
                 ('capls_vs_comm', 'CAP-LS 对 B4 通信聚类')]
    pair_rows += [(f'full_vs_{name}', '完整 CAP-LS 对{}'.format(label[name]))
                  for name in order if name != 'full']
    pr = s_all.get('paired', {})
    lines = ['| 比较对象 | 问题 1 | 问题 2 | 问题 3 |', '|---|---|---|---|']
    for key, text in pair_rows:
        cells = []
        for p in (1, 2, 3):
            d = pr.get(f'problem{p}', {}).get(key)
            if not d or not d.get('n'):
                cells.append('--')
                continue
            pv = d.get('p_holm', d['p'])
            ptxt = 'p<0.001' if pv < 0.001 else 'p={:.3f}'.format(pv)
            cells.append('{:+.1%}（{}，胜/平/负 {}/{}/{}）'.format(
                d['rel'], ptxt, d['win'], d['tie'], d['loss']))
        lines.append('| {} | {} |'.format(text, ' | '.join(cells)))
    v['TABLE_PAIRED'] = chr(10).join(lines)

    _extra_values(s_all, v)

    # 评估总次数 = 所有缓存条目数
    total = 0
    for d in paths.CACHE_DIR.glob('p*'):
        for f in d.glob('*.json'):
            try:
                total += len(json.loads(f.read_text(encoding='utf-8')))
            except (json.JSONDecodeError, OSError):
                pass
    v['TOTAL_EVALS'] = '{:,}'.format(total)
    return v


MINUS = '−'


def _sgn(x, fmt):
    """带符号格式化，负号用 U+2212（与论文其余部分一致）。"""
    return format(x, fmt).replace('-', MINUS)


def _sci(x):
    """把整数字节数写成 $m\\times10^{e}$。"""
    m, e = '{:.2e}'.format(x).split('e')
    return '$' + m + r'\times10^{' + str(int(e)) + '}$'


def _load_json(name):
    p = paths.RESULTS_DIR / name
    return json.loads(p.read_text(encoding='utf-8')) if p.is_file() else {}


def _by_key(d, k):
    return d.get(str(k), d.get(k))


ABL2_LABEL = {
    'full_c2': '完整（c2 基准）', 'no_comm': '去通信感知切图', 'no_sync': '去同步深度代价',
    'no_localsearch': '去局部搜索', 'no_level': '去同步层次分层（块即子图）',
    'no_level_no_comm': '同时去分层与通信感知', 'max_ops500': '子图算子数上限 500',
    'op_full': '单算子子图（α=0.8, μ=1, ν=0.5）', 'op_mu0': '单算子子图，μ=0',
    'op_nu0': '单算子子图，ν=0', 'op_alpha1': '单算子子图，α=1',
    'lvl_alap': '层次 ALAP 填充', 'lvl_compress': '层次 ALAP 压缩'}


def _rj(name):
    f = paths.RESULTS_DIR / name
    return json.loads(f.read_text(encoding='utf-8')) if f.is_file() else {}


def _t23_values(s, v):
    """T23.6：T11–T20 各任务结果段落所用的占位符（数据源见各 results/*.json）。"""
    op = _rj('op_mode_report.json')
    if op:
        v['OP_CHAMP_CFGS'] = op['op_champion_configs']
        v['OP_FEAS'] = '{}/{}'.format(op['op_candidates_feasible'], op['op_candidates_total'])
        v['SPILL_BEFORE_T11'] = '{:.0f}'.format(op['p2_n4_spill_champions_before_T11'] / 1e6)
        v['SPILL_AFTER_T11'] = '{:.0f}'.format(op['p2_n4_spill_champions_after_T11'] / 1e6)
    sm = _rj('sampling_report.json')
    if sm:
        v['SAMP_EVALS'] = sm['new_official_evals']
        v['SAMP_CHAMP'] = sm['champion_s_configs']
        v['SAMP_CONFIGS'] = sm['configs']
        k = sm['by_K']
        for p in (2, 3):
            for K in (0, 1, 4, 16):
                v[f'SAMP_K{K}_P{p}_N4'] = '{:.3f}'.format(k[str(K)][f'P{p}_N4'])
            v[f'SAMP_GAIN_P{p}_N4'] = _sgn(k['16'][f'P{p}_N4'] / k['0'][f'P{p}_N4'] - 1, '+.1%')
    an = _rj('p1_anneal_report.json')
    if an:
        v['SA_CHAMP_MAIN'] = an['sa_champion_configs_main']
        v['SA_CHAMP_POOL'] = an['sa_champion_configs_pool']
        v['SA_ITERS'] = an['anneal_iters']
        v['SA_MED_S'] = '{:.1f}'.format(an['anneal_seconds']['median'])
        v['SA_MAX_S'] = '{:.0f}'.format(an['anneal_seconds']['max'])
        v['SA_OVER'] = an['anneal_seconds']['configs_over_limit']
    l2 = _rj('l2_sources.json').get('by_n', {}).get('4')
    if l2:
        hit = l2['official_hit_bytes']
        miss = l2['official_miss_bytes']
        for key, name in (('input_reuse', 'INPUT'), ('cross_core_mid', 'CROSS'),
                          ('spill_reload', 'SPILL')):
            v[f'L2SRC_{name}'] = '{:.1%}'.format(l2[f'hit_{key}'] / hit)
        for key, name in (('first_miss', 'FIRST'), ('concurrent_first_read', 'CONC'),
                          ('fifo_evicted', 'FIFO')):
            v[f'L2SRC_{name}'] = '{:.1%}'.format(l2[f'miss_{key}'] / miss)
    sp = defaultdict(dict)
    for r in plots.read_csv('final.csv'):
        if r['feasible'] and r['speedup'] and r['num_cores'] == 4 and int(r['problem']) in (2, 3):
            sp[r['case']][int(r['problem'])] = r['speedup']
    both = [x for x in sp.values() if 2 in x and 3 in x]
    v['P2P3_EQUAL'] = sum(1 for x in both if abs(x[3] - x[2]) <= 1e-9)
    v['P2P3_ABOVE'] = sum(1 for x in both if x[3] > x[2] + 1e-9)
    v['P2P3_BELOW'] = sum(1 for x in both if x[3] < x[2] - 1e-9)
    abl2 = s.get('ablation2', {})
    for p in (1, 2, 3):
        for name, e in abl2.get(f'problem{p}', {}).items():
            pr = e.get('paired')
            if pr:
                v[f'ABL2_REL_{name}_P{p}'] = _sgn(pr['rel'], '+.1%')
                v[f'ABL2_P_{name}_P{p}'] = '{:.2g}'.format(pr['p_holm'])
    pa = s.get('portfolio_analysis', {})
    for p in (1, 2, 3):
        c = pa.get('greedy', {}).get(f'P{p}', [])
        if c:
            v[f'GREEDY_FIRST_P{p}'] = c[0]['label']
            v[f'GREEDY_K1_P{p}'] = '{:.3f}'.format(c[0]['amean'])
            v[f'GREEDY_K4_P{p}'] = '{:.3f}'.format(c[min(3, len(c) - 1)]['amean'])
            v[f'GREEDY_ALL_P{p}'] = '{:.3f}'.format(c[-1]['amean'])
            v[f'GREEDY_STEPS_P{p}'] = len(c)
        ps = pa.get('proxy_selection', {}).get(f'P{p}')
        if ps:
            v[f'CHAMP_P{p}_N4'] = '{:.3f}'.format(ps['champion_amean'])
            v[f'PROXY_CHAMP_LOSS_P{p}_N4'] = '{:.3f}'.format(ps['proxy_loss_vs_champion'])


def _t16_values(s, v):
    """T16：TABLE_ABLATION2、TABLE_GREEDY、PROXY_ONLY_P2_N4 及相关数字。"""
    abl2 = s.get('ablation2', {})
    lines = ['| 变体 | 问题 1 | 问题 2 | 问题 3 |', '|---|---|---|---|']
    for name, lab in ABL2_LABEL.items():
        cells = []
        for p in (1, 2, 3):
            e = abl2.get(f'problem{p}', {}).get(name)
            base = abl2.get(f'problem{p}', {}).get('full_c2')
            if not e:
                cells.append('--')
                continue
            m = e['describe']['amean']
            if name == 'full_c2' or not base:
                cells.append('{:.3f}'.format(m))
            else:
                pr = e.get('paired', {})
                cells.append('{:.3f}（{}，p_Holm={:.3g}）'.format(
                    m, _sgn(m / base['describe']['amean'] - 1, '+.1%'),
                    pr.get('p_holm', float('nan'))))
        lines.append('| {} | {} |'.format(lab, ' | '.join(cells)))
    v['TABLE_ABLATION2'] = chr(10).join(lines)

    cv = s.get('cv_select', {})
    if 'cv_loss_max' in cv:
        v['CV_LOSS'] = '{:.1%}'.format(cv['cv_loss_max'])

    pa = s.get('portfolio_analysis', {})
    greedy = pa.get('greedy', {})
    lines = ['| 已选候选数 k | 问题 1 | 问题 2 | 问题 3 |', '|---|---|---|---|']
    kmax = max((len(c) for c in greedy.values()), default=0)
    for k in list(range(1, min(kmax, 8) + 1)) + ([kmax] if kmax > 8 else []):
        cells = []
        for p in (1, 2, 3):
            c = greedy.get(f'P{p}', [])
            if not c:
                cells.append('--')
            else:
                x = c[min(k, len(c)) - 1]
                cells.append('{:.3f}（{}）'.format(x['amean'], x['label']))
        lines.append('| {} | {} |'.format(k, ' | '.join(cells)))
    v['TABLE_GREEDY'] = chr(10).join(lines)

    ps = pa.get('proxy_selection', {})
    if 'P2' in ps:
        v['PROXY_ONLY_P2_N4'] = '{:.3f}'.format(ps['P2']['proxy_only_amean'])
        v['PROXY_LOSS_P2_N4'] = '{:.3f}'.format(ps['P2']['proxy_loss_vs_official_main'])
        v['OFFICIAL_MAIN_P2_N4'] = '{:.3f}'.format(ps['P2']['official_main_amean'])
    for p in (1, 2, 3):
        e = ps.get(f'P{p}')
        if e:
            v[f'PROXY_ONLY_P{p}_N4'] = '{:.3f}'.format(e['proxy_only_amean'])
            v[f'PROXY_LOSS_P{p}_N4'] = '{:.3f}'.format(e['proxy_loss_vs_official_main'])


def _extra_values(s, v):
    """T23 新增的占位符：数据来自 summary.json 之外的结果文件
    （final.csv、bounds.json、model_validation_summary_*.json、op_mode_report.json 等）。"""
    final = [r for r in plots.read_csv('final.csv') if r['feasible']]
    feats = {f['case']: f for f in json.loads(
        (paths.RESULTS_DIR / 'features.json').read_text(encoding='utf-8'))}

    # ---- 并行效率、分层表 ----
    for p in (1, 2, 3):
        sp = s.get(f'problem{p}', {})
        m4 = _by_key(sp.get('speedup_mean', {}), 4)
        d4 = _by_key(sp.get('speedup_median', {}), 4)
        v[f'P{p}_EFF_N4'] = '{:.0%}'.format(m4 / 4) if m4 else '--'
        v[f'P{p}_MEDEFF_N4'] = '{:.0%}'.format(d4 / 4) if d4 else '--'
    strat = _by_key(s.get('problem2', {}).get('speedup_by_strata', {}), 4) or {}
    lines = ['| 分层 | 用例数 | 算术平均 | 中位数 | 最小值 |', '|---|---|---|---|---|']
    for key, text in (('rho<0.2', r'$\rho_{\max}<0.2$（分量碎片化）'),
                      ('0.2<=rho<0.5', r'$0.2\le\rho_{\max}<0.5$'),
                      ('rho>=0.5', r'$\rho_{\max}\ge0.5$（单一主分量）')):
        d = strat.get(key) or {}
        if d.get('n'):
            lines.append('| {} | {} | **{:.2f}** | {:.2f} | {:.2f} |'.format(
                text, d['n'], d['amean'], d['median'], d['min']))
    v['TABLE_STRATA'] = chr(10).join(lines)

    # ---- 由 final.csv 派生的数字 ----
    sp_all = [r['speedup'] for r in final if r['speedup']]
    v['MIN_SPEEDUP_ALL'] = '{:.2f}'.format(min(sp_all)) if sp_all else '--'
    p2n4 = sorted((r for r in final if int(r['problem']) == 2
                   and r['num_cores'] == 4 and r['speedup']),
                  key=lambda r: r['speedup'])
    v['HARDEST_P2_N4'] = '、'.join('{}（{:.2f}）'.format(r['case'], r['speedup'])
                                for r in p2n4[:6])
    c16 = [r['speedup'] for r in p2n4 if r['case'] == 'case_016']
    v['CASE016_P2_N4'] = '{:.2f}'.format(c16[0]) if c16 else '--'
    v['SUPER_P2_N4'] = str(sum(1 for r in p2n4 if r['speedup'] > 4))
    v['SUPER_P2_N2'] = str(sum(1 for r in final if int(r['problem']) == 2
                               and r['num_cores'] == 2 and r['speedup']
                               and r['speedup'] > 2))
    v['ZERO_ADDED_P2_N4'] = str(sum(1 for r in p2n4 if r['added_copy_bytes'] == 0))
    subg = []
    for p in (1, 2, 3):
        vals = [r['n_subgraphs'] for r in final
                if int(r['problem']) == p and r['n_subgraphs']]
        subg.append('{:,}'.format(int(st.median(vals))) if vals else '--')
    v['SUBG_MED'] = ' / '.join(subg)

    def corr(key, log):
        xs, ys = [], []
        for r in p2n4:
            x = feats[r['case']][key]
            if x is None or x == float('inf') or (log and x <= 0):
                continue
            xs.append(math.log(x) if log else x)
            ys.append(r['speedup'])
        return _sgn(float(np.corrcoef(xs, ys)[0, 1]), '+.2f')
    for name, key, lg in (('RHO', 'largest_component_frac', False),
                          ('CP', 'cp_over_total', False),
                          ('WIDTH', 'avg_width', True),
                          ('BW', 'compute_over_ddr', True),
                          ('NOPS', 'n_ops', True)):
        v[f'CORR_{name}'] = corr(key, lg)

    # ---- 搬运量 ----
    p2 = s.get('problem2', {})
    added = _by_key(p2.get('added_copy_total', {}), 4)
    spill = _by_key(p2.get('spill_added_total', {}), 4)
    part = _by_key(p2.get('partition_added_total', {}), 4)
    v['ADDED_TOTAL_P2_N4'] = _sci(added)
    v['CUT_SHARE_P2_N4'] = '{:.1%}'.format(part / (part + spill))
    v['SPILL_SHARE_P2_N4'] = '{:.1%}'.format(spill / (part + spill))
    b3 = (s.get('baseline_added_total', {}).get('p2_n4', {}) or {}).get('balance')
    v['ADDED_TOTAL_B3_P2_N4'] = _sci(b3)
    singles = _load_json('singlecore_baseline.json')
    single_spill = sum(int(x.get('added_copy_bytes') or 0) for x in singles.values())
    v['SINGLE_SPILL_TOTAL'] = _sci(single_spill)
    v['ADDED_VS_SINGLE_P2_N4'] = _sgn(added / single_spill - 1, '+.0%')
    op = _load_json('op_mode_report.json')
    v['SPILL_DROP_OP'] = ('{:.0%}'.format(op['spill_drop_frac'])
                          if op.get('spill_drop_frac') is not None else '--')

    # ---- 基线 / 消融 / L2 ----
    bs = s.get('baseline_speedup', {})
    v['RANDOM_P1_N4'] = '{:.2f}'.format(bs['p1_n4']['random'])
    v['BASE_P2_N4_B2'] = '{:.2f}'.format(bs['p2_n4']['topo'])
    v['BASE_P2_N4_B3'] = '{:.2f}'.format(bs['p2_n4']['balance'])
    v['BASE_B4_N4'] = ' / '.join('{:.2f}'.format(bs[f'p{p}_n4']['comm'])
                                 for p in (1, 2, 3))
    v['GAIN_VS_B4'] = '、'.join(
        '问题 {} {}'.format(p, _sgn(bs[f'p{p}_n4']['capls'] / bs[f'p{p}_n4']['comm'] - 1,
                                  '+.0%')) for p in (1, 2, 3))
    abl = s.get('ablation', {})
    for p in (1, 2, 3):
        d = abl.get(f'problem{p}', {})
        for name in ('no_comm', 'no_balance', 'no_sync', 'no_localsearch',
                     'no_cache_aware', 'no_level'):
            if d.get('full') and d.get(name):
                v[f'ABL_REL_{name}_P{p}'] = _sgn(d[name] / d['full'] - 1, '+.1%')
    _t16_values(s, v)
    _t23_values(s, v)
    gain, hit = s.get('l2_gain', {}), s.get('l2_hit_rate', {})
    for n in (1, 2, 3, 4, 5):
        v[f'L2_GAIN_N{n}'] = '{:.3f}'.format(_by_key(gain, n) or 0)
        v[f'HIT_N{n}'] = '{:.1%}'.format(_by_key(hit, n) or 0)
    gmax = s.get('l2_gain_max', {})
    v['L2_GT1_N5'] = str(_by_key(s.get('l2_gain_gt1pct', {}), 5))
    v['L2_MAX_N5'] = '{:.2f}'.format(_by_key(gmax, 5) or 0)
    v['L2_MAXCASE_N5'] = str(_by_key(s.get('l2_gain_maxcase', {}), 5))
    v['L2_HITNZ_N1'] = str(_by_key(s.get('l2_hit_nonzero', {}), 1))
    v['L2_HITMAX_N1'] = '{:.0%}'.format(_by_key(s.get('l2_hit_max', {}), 1) or 0)
    v['L2_GAINMAX_N1'] = '{:.2f}'.format(_by_key(gmax, 1) or 0)

    # ---- 下界 ----
    bounds = _load_json('bounds.json')
    v['LB_SINGLE_MED'] = '{:.2f}'.format(bounds['single_over_lb1_median'])
    v['BOUND_EFF_N4'] = ' / '.join(
        '{:.2f}'.format(bounds['efficiency'][f'p{p}_n4']['amean']) for p in (1, 2, 3))
    bg = s.get('bound_gap', {})
    lines = ['| | $N=2$ | $N=3$ | $N=4$ | $N=5$ |', '|---|---|---|---|---|']
    for p in (1, 2, 3):
        lines.append('| 问题 {} | {} |'.format(p, ' | '.join(
            '{:.2f}'.format(_by_key(bg.get(f'problem{p}', {}), n)) for n in (2, 3, 4, 5))))
    v['TABLE_BOUND'] = chr(10).join(lines)
    v['BOUND_GAP_P3_N5'] = '{:.0%}'.format(_by_key(bg['problem3'], 5) - 1)

    # ---- 代理检验（用例内指标）----
    mv = {px: _load_json(f'model_validation_summary_{px}.json') for px in ('legacy', 'sim')}
    for px, d in mv.items():
        for p in (1, 2, 3):
            m = d.get(f'problem{p}', {})
            v[f'PROXY_SP_P{p}_{px.upper()}'] = '{:.2f}'.format(m['spearman_median'])
            v[f'PROXY_R3_P{p}_{px.upper()}'] = '{:.0%}'.format(m['recall3'])
    v['PROXY_POOLED_P2_LEGACY'] = '{:.2f}'.format(
        mv['legacy']['problem2']['pooled_spearman'])
    lines = ['| 问题 | 代理 | Spearman 中位 | Kendall $\\tau$ 中位 | Top-1 减速比（中位/P90/最大） '
             '| Top-3 减速比 | Top-5 减速比 | Recall@1 / @3 / @5 |',
             '|---|---|---|---|---|---|---|---|']
    for p in (1, 2, 3):
        for px, name in (('legacy', '旧代理'), ('sim', '事件模拟')):
            m = mv[px].get(f'problem{p}', {})
            slow = ' | '.join('{:.1%} / {:.1%} / {:.0%}'.format(
                m[f'top{k}_slowdown_median'], m[f'top{k}_slowdown_p90'],
                m[f'top{k}_slowdown_max']) for k in (1, 3, 5))
            lines.append('| 问题 {} | {} | {:.2f} | {:.2f} | {} | {} |'.format(
                p, name, m['spearman_median'], m['kendall_median'], slow,
                ' / '.join('{:.0%}'.format(m[f'recall{k}']) for k in (1, 3, 5))))
    v['TABLE_PROXY'] = chr(10).join(lines)

    # ---- 条件 4 的已知例外 ----
    c4 = _load_json('pool_condition4_exceptions.json')
    v['COND4_COUNT'] = str(c4.get('count', 0))
    v['COND4_MAXREL'] = '{:.2%}'.format(c4.get('max_rel_observed', 0.0))

    # ---- 粒度扫描（25 个用例，N=4，单配置；算术平均）----
    gran = [r for r in plots.read_csv('granularity.csv') if r['feasible'] and r['speedup']]
    by = defaultdict(lambda: defaultdict(list))
    for r in gran:
        by[int(r['problem'])][float(r['variant'])].append(r['speedup'])
    betas = sorted({b for p in by for b in by[p]})
    means = {p: {b: sum(x) / len(x) for b, x in by[p].items()} for p in by}
    lines = ['| $\\beta$ | ' + ' | '.join('{:g}'.format(b) for b in betas) + ' |',
             '|---|' + '---|' * len(betas)]
    for p in (1, 2, 3):
        best = max(means[p].values())
        lines.append('| 问题 {} | '.format(p) + ' | '.join(
            ('**{:.2f}**' if means[p][b] == best else '{:.2f}').format(means[p][b])
            for b in betas) + ' |')
    v['TABLE_GRAN'] = chr(10).join(lines)
    big, small, plateau = [], [], 0.0
    bestb, l025, l05, flat23 = [], [], [], []
    for p in (1, 2, 3):
        best = max(means[p].values())
        big.append('{:.0%}'.format(1 - means[p][2.0] / best))
        small.append('{:.0%}'.format(1 - means[p][0.03] / best))
        flat = [means[p][b] for b in (0.12, 0.25, 0.5)]
        plateau = max(plateau, (best - min(flat)) / best)
        bestb.append('{:g}'.format(max(means[p], key=means[p].get)))
        l025.append('{:.1%}'.format(1 - means[p][0.25] / best))
        l05.append('{:.1%}'.format(1 - means[p][0.5] / best))
        if p in (2, 3):
            flat23.append((best - min(flat)) / best)
    v['GRAN_LOSS_BIG'] = ' / '.join(big)
    v['GRAN_LOSS_SMALL'] = ' / '.join(small)
    v['GRAN_PLATEAU'] = '{:.1%}'.format(plateau)
    v['GRAN_BEST_BETA'] = ' / '.join(bestb)
    v['GRAN_LOSS_025'] = ' / '.join(l025)
    v['GRAN_LOSS_05'] = ' / '.join(l05)
    v['GRAN_PLATEAU_P23'] = '{:.1%}'.format(max(flat23))
    v['GRAN_N'] = str(len({r['case'] for r in gran}))
    _sens_table(v)


SENS_ROWS = (('bandwidth', 'DDR 总带宽 (B/cycle)', 1),
             ('L1', 'L1 容量 (KB)', 1024),
             ('UB', 'UB 容量 (KB)', 1024),
             ('cache_capacity_bytes', 'L2 容量 (KB)', 1024),
             ('cache_bandwidth_bytes_per_cycle', 'L2 带宽 (B/cycle)', 1),
             ('cross_core_copy_delay_cycles', '跨核同步延迟 (cycle，问题 2)', 1),
             ('task_cross_core_wait_cycles', '场景 A 跨核等待 (cycle，问题 1)', 1))


def _sens_table(v):
    """TABLE_SENS：Makespan 相对同一用例默认配置的倍数（几何平均，比值型指标）。"""
    from npu import plots
    rows = plots.read_csv('sensitivity.csv')
    mk, default = defaultdict(dict), {}
    for r in rows:
        if not r['feasible'] or not r['makespan']:
            continue
        mk[(r['knob'], r['case'])][int(float(r['value']))] = r['makespan']
        if str(r['is_default']).lower() == 'true':
            default[(r['knob'], r['case'])] = r['makespan']
    lines = ['| 参数 | 取值 → Makespan 相对倍数 |', '|---|---|']
    for knob, label, unit in SENS_ROWS:
        cases = [c for (k, c) in default if k == knob]
        vals = sorted({x for (k, c), d in mk.items() if k == knob for x in d})
        cells = []
        for x in vals:
            ratios = [default[(knob, c)] / mk[(knob, c)][x]
                      for c in cases if x in mk[(knob, c)]]
            if not ratios:
                continue
            gm = math.exp(sum(math.log(t) for t in ratios) / len(ratios))
            is_def = all(mk[(knob, c)].get(x) == default[(knob, c)] for c in cases
                         if x in mk[(knob, c)])
            txt = '{}: {:.3f}'.format(int(x / unit) if x % unit == 0 else x / unit, gm)
            cells.append('**{}**'.format(txt) if is_def else txt)
        lines.append('| {} | {} |'.format(label, ' 　'.join(cells)))
    v['TABLE_SENS'] = chr(10).join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('markdown')
    ap.add_argument('-o', '--output')
    args = ap.parse_args()
    values = build_values()
    text = Path(args.markdown).read_text(encoding='utf-8')
    for k, val in values.items():
        text = text.replace(f'@@{k}@@', str(val))
    left = sorted(set(re.findall(r'@@([A-Za-z0-9_]+)@@', text)))
    out = Path(args.output) if args.output else Path(args.markdown)
    out.write_text(text, encoding='utf-8')
    print('filled {} placeholders -> {}'.format(len(values), out))
    if left:
        print('WARNING unresolved placeholders:', left)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
