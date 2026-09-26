# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Sonnet 5（型号 claude-sonnet-5）、Claude Opus 5.5（型号 claude-opus-5-5）
# 开发机构：Anthropic 公司
# 版本发布日期：Claude Sonnet 5 为 2026-06-30，Claude Opus 5.5 为 2026-09-22
"""导出最终提交用的方案文件。

对每个 (用例, 问题, 核数) 取实验中官方评估 Makespan 最小的方案，按题目
附录 B.5 的命名规则写到 `results/final_plans/p<问题>/n<核数>/<case>_multicore_res.json`。
同时生成一份 `manifest.csv` 记录每个方案的官方指标，便于逐个复核。

    python solution/export_plans.py
    # 复核示例：
    python code/multicore_cut_evaluate_problem_2.py data/case_001.json \
           results/final_plans/p2/n4/case_001_multicore_res.json --config data/config.txt
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from npu import evaluate, experiment, paths, plots               # noqa: E402


def main():
    final_path = paths.RESULTS_DIR / 'final.csv'
    if final_path.is_file():
        rows = plots.read_csv('final.csv')
    else:
        rows = plots.read_csv('main.csv') + plots.read_csv('p3_compare.csv')
    best = {}
    for r in rows:
        if not r['feasible'] or not r.get('plan_path'):
            continue
        ep = int(r.get('eval_problem') or r['problem'])
        if ep != int(r['problem']):
            continue
        key = (r['case'], int(r['problem']), int(r['num_cores'] or 0))
        if key not in best or r['makespan'] < best[key]['makespan']:
            best[key] = r
    out_root = paths.RESULTS_DIR / 'final_plans'
    manifest = []
    for (case, problem, n), r in sorted(best.items()):
        src = paths.ROOT / r['plan_path']
        if not src.is_file():
            continue
        dst_dir = out_root / f'p{problem}' / f'n{n}'
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / f'{case}_multicore_res.json'
        shutil.copyfile(src, dst)
        manifest.append({
            'case': case, 'problem': problem, 'num_cores': n,
            'makespan': r['makespan'], 'speedup': round(r['speedup'] or 0, 4),
            'added_copy_bytes': r['added_copy_bytes'],
            'cache_hit_rate': r.get('cache_hit_rate'),
            'n_subgraphs': r['n_subgraphs'],
            'plan': str(dst.relative_to(paths.ROOT)),
        })
    # N=1 方案（整图单子图）对三个问题相同
    for case in paths.all_cases():
        plan = evaluate.make_plan(
            {v: 0 for v in experiment.get_graph(case).nodes}, [[0]])
        for problem in (1, 2, 3):
            d = out_root / f'p{problem}' / 'n1'
            d.mkdir(parents=True, exist_ok=True)
            (d / f'{case}_multicore_res.json').write_text(
                json.dumps(plan, ensure_ascii=False), encoding='utf-8')
    experiment.write_csv(manifest, out_root / 'manifest.csv')
    print('exported {} plans -> {}'.format(len(manifest), out_root))


if __name__ == '__main__':
    main()
