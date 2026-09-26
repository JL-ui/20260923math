# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Sonnet 5（型号 claude-sonnet-5）、Claude Opus 5.5（型号 claude-opus-5-5）
# 开发机构：Anthropic 公司
# 版本发布日期：Claude Sonnet 5 为 2026-06-30，Claude Opus 5.5 为 2026-09-22
"""T13 优先级采样报告 -> results/sampling_report.json。

采样样本 s_k 只有被官方评估过才有记录；K 的比较取"c* 候选 ∪ {已评估的 s_j, j≤K}"
的最优 Makespan，K=0 即 T13 之前的口径。
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from npu import paths, plots, stats                              # noqa: E402


def main():
    rows = [r for r in plots.read_csv('main.csv')
            if int(r['problem']) in (2, 3) and r['feasible'] and r['makespan']
            and (r.get('eval_problem') in (None, '', r['problem']))
            and r['variant'] != '_best']
    groups = defaultdict(list)
    for r in rows:
        groups[(r['case'], int(r['problem']), int(r['num_cores']))].append(r)
    rep = {'new_official_evals': sum(1 for r in rows if r['variant'].startswith('s')),
           'champion_s_configs': 0, 'configs': len(groups), 'by_K': {}}
    speed = {K: defaultdict(list) for K in (0, 1, 4, 16)}
    champ_cfg = []
    for key, rs in groups.items():
        base = next((float(r['baseline_makespan']) for r in rs if r.get('baseline_makespan')), None)
        if not base:
            continue
        for K in speed:
            cand = [float(r['makespan']) for r in rs
                    if not r['variant'].startswith('s') or int(r['variant'][1:]) <= K]
            if cand:
                speed[K][(key[1], key[2])].append(base / min(cand))
        best = min(rs, key=lambda r: float(r['makespan']))
        if best['variant'].startswith('s'):
            champ_cfg.append({'case': key[0], 'problem': key[1], 'num_cores': key[2],
                              'variant': best['variant']})
    rep['champion_s_configs'] = len(champ_cfg)
    rep['champion_s_examples'] = champ_cfg[:20]
    for K, d in speed.items():
        rep['by_K'][str(K)] = {f'P{p}_N{n}': round(stats.amean(v), 4)
                               for (p, n), v in sorted(d.items())}
    (paths.RESULTS_DIR / 'sampling_report.json').write_text(
        json.dumps(rep, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps(rep, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
