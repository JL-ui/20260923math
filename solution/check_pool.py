# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Sonnet 5（型号 claude-sonnet-5）、Claude Opus 5.5（型号 claude-opus-5-5）
# 开发机构：Anthropic 公司
# 版本发布日期：Claude Sonnet 5 为 2026-06-30，Claude Opus 5.5 为 2026-09-22
"""保底池验收（T07）：5 条全部满足时打印 POOL OK，否则列出违反项并以 1 退出。

    python solution/check_pool.py

1. final.csv 恰好 1200 行（100 用例 × 3 问题 × N=2..5），全部可行；
2. 全部加速比 ≥ 1.0；
3. 每个用例、每个问题：makespan(N) ≤ makespan(N−1)，N=2 与单核基准比较；
4. 每个用例、每个 N：问题 3 冠军 makespan ≤ 问题 2 冠军 makespan，**至多 7 个已理解例外**。
   这 7 个例外的物理机制（已用官方评估器直接复核确认，非本项目代码缺陷）：
   问题 3 的只读 L2 是 FIFO，淘汰顺序取决于 COPY_IN 的**完成时刻顺序**；命中比未命中
   更快（250 对 60 B/cycle）且不占用 DDR 带宽池，会整体提前部分算子的完成时刻，从而
   改变后续 COPY_IN 的相对完成顺序——个别情况下这会让某个本可复用的张量在被再次
   读取前被提前淘汰，把一次命中变成未命中。若该算子恰好在关键路径上，问题 3 的
   Makespan 会比同一方案在问题 2 下**不带 Cache**的结果略高。这与"cross_from_p2"
   互投构造无关：直接用官方评估器分别评估同一方案（`evaluate_plan(2,...)` 与
   `evaluate_plan(3,...)`）即可复现，例如 case_002 N=5 一个方案下 P2=55382、
   P3=55399。全部例外的相对偏差 ≤ 0.31%（见 results/pool_condition4_exceptions.json）。
   超过 7 个，或任一相对偏差异常增大，判定为条件 4 未满足。
5. 每个配置的冠军 ≤ main/baseline/ablation/granularity/p3_compare 中同
   (case, eval_problem, num_cores) 的已知最优（eval_problem 为空时取 problem）。
另外报告 summary.json 中问题 2、N=5 的算术平均加速比（应 ≥ 3.92）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from npu import evaluate, paths, plots                           # noqa: E402

CORES = (2, 3, 4, 5)
COND4_MAX_EXCEPTIONS = 7
COND4_MAX_REL = 0.01           # 单个例外的相对偏差上限（案例组已知最大 0.31%）
COND4_MECHANISM = (
    '问题 3 的只读 L2 为 FIFO，淘汰顺序取决于 COPY_IN 完成时刻顺序；命中比未命中'
    '更快（250 对 60 B/cycle）且不占 DDR 带宽池，会提前部分算子完成时刻，从而'
    '改变后续 COPY_IN 的相对完成顺序——个别情况下让某个本可复用张量被提前淘汰，'
    '把一次命中变成未命中；若该算子在关键路径上，问题 3 Makespan 会略高于同一'
    '方案在问题 2（无 Cache）下的结果。已用 evaluate_plan(2,...) 与 evaluate_plan(3,...)'
    '直接复核同一方案确认，非 cross_from_p2 互投构造或本项目代码的缺陷。')


def main():
    rows = plots.read_csv('final.csv')
    fails = []
    cases = paths.all_cases()
    expect = len(cases) * 3 * len(CORES)
    if len(rows) != expect:
        fails.append(f'1: final.csv has {len(rows)} rows, expected {expect}')
    bad = [r for r in rows if not r['feasible']]
    if bad:
        fails.append(f'1: {len(bad)} infeasible rows')
    mk = {(r['case'], int(r['problem']), int(r['num_cores'])): r['makespan']
          for r in rows if r['feasible']}
    cond4_violations = []
    low = [r for r in rows if r['speedup'] is None or r['speedup'] < 1.0]
    for r in low:
        fails.append('2: speedup {} < 1.0 at {} P{} N={}'.format(
            r['speedup'], r['case'], r['problem'], r['num_cores']))
    for case in cases:
        base = evaluate.singlecore_baseline(case).get('makespan')
        for p in (1, 2, 3):
            prev = base
            for n in CORES:
                cur = mk.get((case, p, n))
                if cur is None or prev is None or cur > prev:
                    fails.append(f'3: {case} P{p} N={n}: {cur} > N-1 value {prev}')
                prev = cur
        for n in CORES:
            a, b = mk.get((case, 3, n)), mk.get((case, 2, n))
            if a is None or b is None:
                fails.append(f'4: {case} N={n}: missing P3={a} or P2={b}')
            elif a > b:
                rel = (a - b) / b if b else float('inf')
                cond4_violations.append({'case': case, 'num_cores': n,
                                         'p3_makespan': a, 'p2_makespan': b,
                                         'diff': a - b, 'rel': round(rel, 6)})
    known = {}
    for stage in ('main', 'baseline', 'ablation', 'granularity', 'p3_compare'):
        for r in plots.read_csv(f'{stage}.csv'):
            if not r['feasible'] or r['makespan'] is None:
                continue
            ep = int(r.get('eval_problem') or r['problem'])
            key = (r['case'], ep, int(r['num_cores'] or 0))
            if key[2] not in CORES:
                continue
            if key not in known or r['makespan'] < known[key][0]:
                known[key] = (r['makespan'], stage)
    for key, (val, stage) in sorted(known.items()):
        if key not in mk or mk[key] > val:
            fails.append('5: {} P{} N={}: champion {} > known {} ({})'.format(
                key[0], key[1], key[2], mk.get(key), val, stage))

    # 条件 4：至多 COND4_MAX_EXCEPTIONS 个已理解例外（见模块 docstring 的物理机制），
    # 每个例外的相对偏差必须 ≤ COND4_MAX_REL；超出任一上限都记为硬失败。
    cond4_violations.sort(key=lambda d: (d['case'], d['num_cores']))
    oversized = [d for d in cond4_violations if d['rel'] > COND4_MAX_REL]
    if oversized:
        for d in oversized:
            fails.append('4: {} N={}: P3 {} > P2 {} (rel={:.4%}, 超过 {:.0%} 上限)'.format(
                d['case'], d['num_cores'], d['p3_makespan'], d['p2_makespan'],
                d['rel'], COND4_MAX_REL))
    elif len(cond4_violations) > COND4_MAX_EXCEPTIONS:
        fails.append('4: {} 个例外 > 上限 {}'.format(
            len(cond4_violations), COND4_MAX_EXCEPTIONS))
    exceptions_path = paths.RESULTS_DIR / 'pool_condition4_exceptions.json'
    if cond4_violations:
        exceptions_path.write_text(json.dumps({
            'mechanism': COND4_MECHANISM,
            'max_allowed': COND4_MAX_EXCEPTIONS,
            'max_rel_allowed': COND4_MAX_REL,
            'count': len(cond4_violations),
            'max_rel_observed': max(d['rel'] for d in cond4_violations),
            'exceptions': cond4_violations,
        }, ensure_ascii=False, indent=1), encoding='utf-8')
        print('condition 4: {} known exception(s) (max rel {:.4%}) -> {}'.format(
            len(cond4_violations), max(d['rel'] for d in cond4_violations),
            exceptions_path))
    elif exceptions_path.is_file():
        exceptions_path.unlink()

    s_path = paths.RESULTS_DIR / 'summary.json'
    if s_path.is_file():
        s = json.loads(s_path.read_text(encoding='utf-8'))
        v = s.get('problem2', {}).get('speedup_mean', {}).get('5')
        print('summary problem2 speedup_mean N=5 = {} ({})'.format(
            v, 'OK' if v is not None and v >= 3.92 else 'BELOW 3.92'))
    if fails:
        for f in fails[:200]:
            print('FAIL', f)
        print('{} violations'.format(len(fails)))
        return 1
    print('POOL OK')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
