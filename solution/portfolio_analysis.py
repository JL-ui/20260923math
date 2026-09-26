# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Sonnet 5（型号 claude-sonnet-5）、Claude Opus 5.5（型号 claude-opus-5-5）
# 开发机构：Anthropic 公司
# 版本发布日期：Claude Sonnet 5 为 2026-06-30，Claude Opus 5.5 为 2026-09-22
"""组合层与择优层分析（T16）。

    python solution/portfolio_analysis.py [--jobs 16]

只读 results/pool.csv，不跑官方评估（择优层需要重建候选方案供代理打分，
重建走 variants.build，与保底池同一入口）。

1. 贪心前向选择：主候选标签（c*、s*、sa*），每个问题 N=4，逐步加入使算术平均
   加速比增加最多的标签，输出"候选数 → 算术平均"曲线。
2. 留一消融：从池内全部标签中去掉一个，重新取冠军，输出 N=4 算术平均的变化。
3. 择优层：每个 (case, 问题, N=4) 用代理（simproxy_gate.json 的 pass_rank 为真用
   simproxy.estimate，否则用旧解析代价）在主候选中选一个，与官方择优的冠军比较。

输出 results/portfolio_analysis.json。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from npu import evaluate, experiment, paths, plots, stats, variants   # noqa: E402

N_FOCUS = 4


def is_main_label(label: str) -> bool:
    if label[:1] == 'c' and label[1:].isdigit():
        return True
    return variants.is_sample_label(label) or variants.is_saved_plan_label(label)


def load_pool():
    """{(problem, N): {case: {label: speedup}}}，只含可行且有 Makespan 的行。"""
    base = {}
    out = defaultdict(lambda: defaultdict(dict))
    for r in plots.read_csv('pool.csv'):
        if not r['feasible'] or not r['makespan']:
            continue
        c = r['case']
        if c not in base:
            base[c] = evaluate.singlecore_baseline(c)['makespan']
        out[(int(r['problem']), int(r['num_cores']))][c][r['label']] = (
            base[c] / float(r['makespan']))
    return out


def greedy_curve(cases, labels):
    """cases = {case: {label: speedup}}；返回 [(标签, 算术平均)]，直到全部标签用完或无增益。"""
    best = {c: 0.0 for c in cases}
    chosen, curve = [], []
    remaining = set(labels)
    while remaining:
        gains = {}
        for lab in remaining:
            gains[lab] = sum(max(best[c], cases[c].get(lab, 0.0)) for c in cases)
        lab = max(sorted(remaining), key=lambda x: gains[x])
        if chosen and gains[lab] <= sum(best.values()) + 1e-12:
            break
        for c in cases:
            best[c] = max(best[c], cases[c].get(lab, 0.0))
        chosen.append(lab)
        remaining.discard(lab)
        curve.append((lab, sum(best.values()) / len(cases)))
    return curve


def leave_one_out(cases):
    labels = sorted({l for v in cases.values() for l in v})
    full = {c: max(v.values()) for c, v in cases.items() if v}
    full_mean = stats.amean(list(full.values()))
    rows = []
    for lab in labels:
        vals = []
        for c, v in cases.items():
            rest = [x for l, x in v.items() if l != lab]
            vals.append(max(rest) if rest else 0.0)
        rows.append((lab, stats.amean(vals) - full_mean))
    rows.sort(key=lambda x: x[1])
    return full_mean, rows


def _proxy_pick(args):
    case, problem, n, labels, use_sim = args
    g = experiment.get_graph(case)
    cfg = paths.official_config()
    scores = {}
    for lab in labels:
        try:
            plan = variants.build(g, lab, problem, n)
            from npu import simproxy
            scores[lab] = simproxy.estimate(g, plan, problem, cfg)
        except Exception:                                      # noqa: BLE001
            continue
    return case, problem, scores


def proxy_layer(pool, jobs):
    gate = json.loads((paths.RESULTS_DIR / 'simproxy_gate.json').read_text(encoding='utf-8'))
    use_sim = bool(gate.get('pass_rank'))
    if not use_sim:
        return {'skipped': 'pass_rank=false，旧代理择优未接入本脚本'}
    tasks = []
    for problem in (1, 2, 3):
        cases = pool.get((problem, N_FOCUS), {})
        for c, v in cases.items():
            labels = sorted(l for l in v if is_main_label(l))
            if labels:
                tasks.append((c, problem, N_FOCUS, labels, True))
    picks = defaultdict(dict)
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        for case, problem, scores in ex.map(_proxy_pick, tasks, chunksize=1):
            if scores:
                best = min(scores, key=lambda l: (scores[l], l))
                picks[problem][case] = best
    report = {}
    for problem in (1, 2, 3):
        cases = pool.get((problem, N_FOCUS), {})
        proxy, main_best, champ = {}, {}, {}
        for c, v in cases.items():
            main = {l: x for l, x in v.items() if is_main_label(l)}
            if not main or c not in picks[problem] or picks[problem][c] not in v:
                continue
            proxy[c] = v[picks[problem][c]]
            main_best[c] = max(main.values())
            champ[c] = max(v.values())
        report[f'P{problem}'] = {
            'n': len(proxy),
            'proxy_only_amean': round(stats.amean(list(proxy.values())), 4),
            'official_main_amean': round(stats.amean(list(main_best.values())), 4),
            'champion_amean': round(stats.amean(list(champ.values())), 4),
            'proxy_loss_vs_official_main': round(
                stats.amean(list(main_best.values())) - stats.amean(list(proxy.values())), 4),
            'proxy_loss_vs_champion': round(
                stats.amean(list(champ.values())) - stats.amean(list(proxy.values())), 4),
            'proxy_vs_official_main': stats.paired(proxy, main_best),
            'proxy_vs_champion': stats.paired(proxy, champ),
        }
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--jobs', type=int, default=16)
    args = ap.parse_args()
    pool = load_pool()
    out = {'greedy': {}, 'leave_one_out': {}, 'proxy_selection': None}
    for problem in (1, 2, 3):
        cases = pool.get((problem, N_FOCUS), {})
        main_labels = sorted({l for v in cases.values() for l in v if is_main_label(l)})
        curve = greedy_curve(cases, main_labels)
        out['greedy'][f'P{problem}'] = [
            {'k': i + 1, 'label': lab, 'amean': round(m, 4)}
            for i, (lab, m) in enumerate(curve)]
        full_mean, loo = leave_one_out(cases)
        out['leave_one_out'][f'P{problem}'] = {
            'champion_amean': round(full_mean, 4),
            'worst_10': [{'label': l, 'delta': round(d, 5)} for l, d in loo[:10]],
            'labels': len(loo)}
    out['proxy_selection'] = proxy_layer(pool, args.jobs)
    (paths.RESULTS_DIR / 'portfolio_analysis.json').write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps(out, ensure_ascii=False, indent=1)[:3000])


if __name__ == '__main__':
    main()
