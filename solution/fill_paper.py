"""把论文中的 @@占位符@@ 用 results/summary.json 的实测数字替换。

    python solution/fill_paper.py paper/论文.md -o paper/论文_final.md

设计意图：论文正文里的每一个数字都必须能追溯到实验记录，禁止手工填写。
脚本会列出所有未被替换的占位符并以非零码退出，避免"漏填"悄悄发生。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from npu import paths, plots                                    # noqa: E402


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
        g = s.get(key, {}).get('speedup_geomean', {})
        v[f'P{p}_CURVE'] = _curve(g)
        for n in (2, 3, 4, 5):
            val = g.get(str(n), g.get(n))
            v[f'P{p}_SU_N{n}'] = '{:.2f}'.format(val) if val else '--'
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('markdown')
    ap.add_argument('-o', '--output')
    args = ap.parse_args()
    values = build_values()
    text = Path(args.markdown).read_text(encoding='utf-8')
    for k, val in values.items():
        text = text.replace(f'@@{k}@@', str(val))
    left = sorted(set(re.findall(r'@@([A-Z0-9_]+)@@', text)))
    out = Path(args.output) if args.output else Path(args.markdown)
    out.write_text(text, encoding='utf-8')
    print('filled {} placeholders -> {}'.format(len(values), out))
    if left:
        print('WARNING unresolved placeholders:', left)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
