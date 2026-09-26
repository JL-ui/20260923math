# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Sonnet 5（型号 claude-sonnet-5）、Claude Opus 5.5（型号 claude-opus-5-5）
# 开发机构：Anthropic 公司
# 版本发布日期：Claude Sonnet 5 为 2026-06-30，Claude Opus 5.5 为 2026-09-22
"""检查 variants.build 的确定性与一致性（T05 验收）。

    python solution/check_variants.py

对 case_001 / case_016 / case_044 × 问题 2 × N=4：
  1. 每个标签 build 两次，plan_hash 相同；
  2. c* 标签的 plan_hash 与 experiment.run_portfolio 生成的同名候选相同；
  3. a* 标签经 default_cache().evaluate 的 makespan 与 results/ablation.csv 完全相等。
全部通过打印 ALL OK 并以 0 退出。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from npu import evaluate, experiment, plots, variants            # noqa: E402

CASES = ('case_001', 'case_016', 'case_044')
PROBLEM, NCORES = 2, 4


def portfolio_hashes(case):
    """运行 run_portfolio，按候选顺序截获送去评估的方案哈希。"""
    cache = evaluate.default_cache()
    seen = []
    orig = cache.evaluate

    def spy(problem, case_, plan):
        seen.append(evaluate.plan_hash(evaluate.canonical_plan(plan)))
        return orig(problem, case_, plan)

    cache.evaluate = spy
    try:
        recs = experiment.run_portfolio(case, PROBLEM, NCORES, save_plan=False)
    finally:
        cache.evaluate = orig
    out, it = {}, iter(seen)
    for r in recs:
        if str(r.get('error', '')).startswith('PLAN'):
            continue
        out[r['variant']] = next(it)
    return out


def main():
    abl = {}
    for r in plots.read_csv('ablation.csv'):
        if int(r['problem']) == PROBLEM and int(r['num_cores'] or 0) == NCORES:
            abl[(r['case'], r['variant'])] = r['makespan']
    bad = []
    for case in CASES:
        g = experiment.get_graph(case)
        port = portfolio_hashes(case)
        for label in variants.LABELS(PROBLEM, NCORES):
            h1 = evaluate.plan_hash(variants.build(g, label, PROBLEM, NCORES))
            h2 = evaluate.plan_hash(variants.build(g, label, PROBLEM, NCORES))
            if h1 != h2:
                bad.append((case, label, 'nondeterministic'))
                continue
            if label.startswith('c') and label[1:].isdigit() and label in port:
                if port[label] != h1:
                    bad.append((case, label, 'differs from run_portfolio'))
            if label.startswith('a_'):
                plan = variants.build(g, label, PROBLEM, NCORES)
                res = evaluate.default_cache().evaluate(PROBLEM, case, plan)
                want = abl.get((case, label[2:]))
                if res.get('makespan') != want:
                    bad.append((case, label, 'makespan {} != ablation.csv {}'.format(
                        res.get('makespan'), want)))
        print('{}: {} labels, {} portfolio candidates compared'.format(
            case, len(variants.LABELS(PROBLEM, NCORES)),
            sum(1 for k in port if k.startswith('c'))), flush=True)
    evaluate.default_cache().flush()
    if bad:
        for b in bad:
            print('MISMATCH', *b)
        return 1
    print('ALL OK')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
