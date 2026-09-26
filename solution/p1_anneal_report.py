# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Sonnet 5（型号 claude-sonnet-5）、Claude Opus 5.5（型号 claude-opus-5-5）
# 开发机构：Anthropic 公司
# 版本发布日期：Claude Sonnet 5 为 2026-06-30，Claude Opus 5.5 为 2026-09-22
"""T14 验收报告：P1 代理驱动模拟退火（sa1..sa3）的效果与耗时。

    python solution/p1_anneal_report.py

数据来源：
  * results/main.csv                          T14 之后的主阶段记录（含 sa* 行）；
  * results/baseline_snapshot/main_before_T14.csv   T14 之前的主阶段记录；
  * results/final.csv                         保底池冠军。
输出 results/p1_anneal_report.json：
  * sa_champion_configs_main / _pool  sa* 成为冠军的配置数（主阶段口径 / 保底池口径）；
  * new_official_evals_per_config     每配置新增官方评估次数的分布
                                       （常规用例应恰为 3；大图 P1 走 top-1 兜底，为 1）；
  * anneal_seconds                    每配置退火耗时（median / max / 超过 60 s 的配置数）；
  * p1_speedup_mean                   T14 前后各 N 的算术平均加速比（主阶段口径）。
"""

from __future__ import annotations

import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from npu import p1_anneal, paths, plots, stats                    # noqa: E402

LIMIT_S = 60.0


def best_speedups(rows):
    """{(case, N): 最优官方 makespan 对应的加速比}，只看问题 1。"""
    best = {}
    for r in rows:
        if int(r['problem']) != 1 or not r['feasible'] or not r['makespan']:
            continue
        key = (r['case'], int(r['num_cores']))
        if key not in best or r['makespan'] < best[key]['makespan']:
            best[key] = r
    return best


def main():
    after = plots.read_csv('main.csv')
    before = plots.read_csv(paths.RESULTS_DIR / 'baseline_snapshot' / 'main_before_T14.csv')
    final = plots.read_csv('final.csv')

    sa_rows = defaultdict(list)                 # (case, N) -> [row]
    for r in after:
        if int(r['problem']) == 1 and str(r.get('variant', '')).startswith('sa'):
            sa_rows[(r['case'], int(r['num_cores']))].append(r)

    best_after = best_speedups(after)
    champ_main = sum(1 for k, r in best_after.items()
                     if str(r.get('variant', '')).startswith('sa')
                     or (r.get('variant') == '_best'
                         and '"anneal": true' in str(r.get('params', ''))))
    champ_pool = sum(1 for r in final if int(r['problem']) == 1
                     and str(r.get('variant', '')).startswith('pool:sa'))

    evals = defaultdict(int)
    for k, rows in sa_rows.items():
        evals[len(rows)] += 1
    secs = []
    for k, rows in sa_rows.items():
        for r in rows:
            try:
                secs.append((json.loads(r['params']).get('anneal_seconds'), k))
                break                            # 同一配置的 sa 行共享同一次退火耗时
            except (ValueError, TypeError, KeyError):
                continue
    vals = [s for s, _ in secs if s is not None]
    slow = sorted(((s, k) for s, k in secs if s is not None and s > LIMIT_S),
                  reverse=True)

    def per_n(rows_by_key):
        out = defaultdict(list)
        for (case, n), r in rows_by_key.items():
            if r['speedup']:
                out[n].append(r['speedup'])
        return {str(n): round(stats.amean(v), 4) for n, v in sorted(out.items())}

    report = {
        'anneal_iters': p1_anneal.ITERS,
        'anneal_seed': p1_anneal.SEED,
        'configs_with_sa_rows': len(sa_rows),
        'sa_champion_configs_main': champ_main,
        'sa_champion_configs_pool': champ_pool,
        'new_official_evals_per_config': {str(k): v for k, v in sorted(evals.items())},
        'anneal_seconds': {
            'n': len(vals),
            'median': round(st.median(vals), 2) if vals else None,
            'max': round(max(vals), 2) if vals else None,
            'limit': LIMIT_S,
            'configs_over_limit': len(slow),
            'worst': [{'case': k[0], 'num_cores': k[1], 'seconds': round(s, 1)}
                      for s, k in slow[:10]],
        },
        'p1_speedup_mean': {'before': per_n(best_speedups(before)),
                            'after': per_n(best_after)},
    }
    report['no_regression'] = all(
        report['p1_speedup_mean']['after'].get(n, 0)
        >= report['p1_speedup_mean']['before'].get(n, 0)
        for n in report['p1_speedup_mean']['before'])
    (paths.RESULTS_DIR / 'p1_anneal_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
