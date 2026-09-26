# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Sonnet 5（型号 claude-sonnet-5）、Claude Opus 5.5（型号 claude-opus-5-5）
# 开发机构：Anthropic 公司
# 版本发布日期：Claude Sonnet 5 为 2026-06-30，Claude Opus 5.5 为 2026-09-22
"""快速评估器与官方评估器的差分测试（T09）。

    python solution/check_fasteval.py --jobs 16

测试集：
  * results/plans/ 与 results/plans_final/ 下的全部方案文件；
  * results/samples.json 中 pilot20 的 20 个用例 × N=2..5 × 问题 1..3 × variants.LABELS。
官方结果**只取缓存**（default_cache().get），缓存未命中的方案跳过、不做官方评估；
对命中的方案调用 evaluate.evaluate_fast，比较 evaluate._summarise 产出的全部字段
（eval_seconds 除外），要求完全相等。明细写 results/fasteval_diff.csv。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from npu import evaluate, experiment, paths, variants            # noqa: E402

PLAN_RE = re.compile(r'^(case_\d+)_p(\d)_n(\d)')


def _strip(res):
    return {k: v for k, v in res.items() if k not in ('eval_seconds', 'cached')}


def compare_case(case, file_jobs, build_jobs):
    """file_jobs: [(problem, path)]；build_jobs: [(problem, N, label)]。"""
    cache = evaluate.default_cache()
    g = None
    seen = set()
    rows = []
    items = []
    for problem, path in file_jobs:
        plan = evaluate.canonical_plan(json.loads(Path(path).read_text(encoding='utf-8')))
        items.append((problem, plan, Path(path).name))
    for problem, n, label in build_jobs:
        if g is None:
            g = experiment.get_graph(case)
        try:
            plan = variants.build(g, label, problem, n)
        except Exception:                                        # noqa: BLE001
            continue
        items.append((problem, plan, f'{label}@p{problem}n{n}'))
    for problem, plan, source in items:
        h = evaluate.plan_hash(plan)
        if (problem, h) in seen:
            continue
        seen.add((problem, h))
        official = cache.get(problem, case, plan)
        if official is None:
            continue
        t0 = time.perf_counter()
        fast = evaluate.evaluate_fast(problem, case, plan)
        secs = time.perf_counter() - t0
        a, b = _strip(official), _strip(fast)
        diff = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
        rows.append({'case': case, 'problem': problem, 'source': source,
                     'plan_hash': h, 'equal': not diff,
                     'diff_fields': ';'.join(diff),
                     'official_makespan': a.get('makespan'),
                     'fast_makespan': b.get('makespan'),
                     'official_eval_s': official.get('eval_seconds'),
                     'fast_eval_s': round(secs, 3)})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--jobs', type=int, default=16)
    ap.add_argument('--cases', nargs='*')
    ap.add_argument('--out', default=str(paths.RESULTS_DIR / 'fasteval_diff.csv'))
    args = ap.parse_args()
    files = defaultdict(list)
    for d in (paths.RESULTS_DIR / 'plans', paths.RESULTS_DIR / 'plans_final'):
        for f in sorted(d.glob('case_*.json')):
            m = PLAN_RE.match(f.stem)
            if not m:
                continue
            case, problem = m.group(1), int(m.group(2))
            probs = (2, 3) if problem == 3 else (problem,)   # p3 对照阶段两种视角均可能缓存
            for p in probs:
                files[case].append((p, str(f)))
    samples = json.loads((paths.RESULTS_DIR / 'samples.json').read_text(encoding='utf-8'))
    builds = defaultdict(list)
    for case in samples['pilot20']:
        for n in (2, 3, 4, 5):
            for p in (1, 2, 3):
                for label in variants.LABELS(p, n):
                    builds[case].append((p, n, label))
    cases = sorted(set(files) | set(builds))
    if args.cases:
        cases = [c for c in cases if c in args.cases]
    feats = {f['case']: f['n_ops'] for f in json.loads(
        (paths.RESULTS_DIR / 'features.json').read_text(encoding='utf-8'))}
    cases.sort(key=lambda c: -feats.get(c, 0))
    rows = []
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.jobs) as ex:
        futs = {ex.submit(compare_case, c, files.get(c, []), builds.get(c, [])): c
                for c in cases}
        for i, fut in enumerate(as_completed(futs), 1):
            rows.extend(fut.result())
            bad = sum(1 for r in rows if not r['equal'])
            print('[fasteval] {}/{} {} compared={} mismatches={} {:.0f}s'.format(
                i, len(cases), futs[fut], len(rows), bad, time.time() - t0), flush=True)
    rows.sort(key=lambda r: (r['case'], r['problem'], r['source']))
    experiment.write_csv(rows, Path(args.out))
    by_p = defaultdict(int)
    for r in rows:
        by_p[r['problem']] += 1
    bad = sum(1 for r in rows if not r['equal'])
    print('compared={} (P1={} P2={} P3={}) mismatches={}'.format(
        len(rows), by_p[1], by_p[2], by_p[3], bad))
    return 0 if bad == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
