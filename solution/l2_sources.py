# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Sonnet 5（型号 claude-sonnet-5）、Claude Opus 5.5（型号 claude-opus-5-5）
# 开发机构：Anthropic 公司
# 版本发布日期：Claude Sonnet 5 为 2026-06-30，Claude Opus 5.5 为 2026-09-22
"""问题 3 的 L2 命中/未命中来源拆分（T17.2）。

    python solution/l2_sources.py --jobs 16

对 results/final.csv 中问题 3 的全部冠军方案，以 evaluate.evaluate_plan(3, ..., full=True)
重跑官方评估（缓存不保存事件流），读取 cache_events：

命中（hit）按张量分类：
  * input_reuse     图输入张量（无可切分生产者）；
  * spill_reload    张量的生产算子与事件所在核相同（核内换出后再换入）；
  * cross_core_mid  其余（跨核中间张量）。
未命中（miss）按张量逐个按时间排序，第一个之后的 miss：
  * oversize               张量大于 Cache 容量，永远不会被写入（规格外的补充类，避免误归入下一类）；
  * concurrent_first_read  此前没有该张量的 insert 事件（多核并发首读）；
  * fifo_evicted           此前有 insert 且之后被 FIFO 淘汰。
每个张量的第一个 miss 记为 first_miss（冷启动，不可避免）。

输出 results/l2_sources.csv（每配置一行）与 results/l2_sources.json（汇总）。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from npu import evaluate, experiment, paths, plots               # noqa: E402

HIT_KINDS = ('input_reuse', 'spill_reload', 'cross_core_mid')
MISS_KINDS = ('first_miss', 'oversize', 'concurrent_first_read', 'fifo_evicted')


def split_events(g, plan, events, cache_capacity):
    mapping = {int(k): int(v) for k, v in plan['node_to_subgraph'].items()}
    core_of_sub = {sg: k for k, order in enumerate(plan['core_schedules'])
                   for sg in order}
    out = {f'hit_{k}': 0 for k in HIT_KINDS}
    out.update({f'miss_{k}': 0 for k in MISS_KINDS})
    inserted_at = {}                 # tid -> 插入时刻（最近一次）
    evicted_at = {}                  # tid -> 最近一次被淘汰的时刻
    seen_miss = set()
    for ev in events:                # 事件按发生顺序记录
        tid = ev['tensor_id']
        if ev['event'] == 'insert':
            inserted_at[tid] = ev['time']
            for old in ev.get('evicted_tensor_ids', ()):
                evicted_at[old] = ev['time']
            continue
        size = ev['size_bytes']
        if ev['event'] == 'hit':
            prods = g.producers.get(tid, ())
            if not prods:
                kind = 'input_reuse'
            elif any(core_of_sub[mapping[o]] == ev['core_id'] for o in prods):
                kind = 'spill_reload'
            else:
                kind = 'cross_core_mid'
            out[f'hit_{kind}'] += size
        elif ev['event'] == 'miss':
            if tid not in seen_miss:
                seen_miss.add(tid)
                kind = 'first_miss'
            elif size > cache_capacity:
                kind = 'oversize'
            elif tid not in inserted_at:
                kind = 'concurrent_first_read'
            else:
                kind = 'fifo_evicted'
            out[f'miss_{kind}'] += size
    return out


def task(case, n, plan_path):
    g = experiment.get_graph(case)
    plan = json.loads((paths.ROOT / plan_path).read_text(encoding='utf-8'))
    res = evaluate.evaluate_plan(3, case, plan, full=True)
    if not res.get('feasible'):
        return {'case': case, 'num_cores': n, 'error': res.get('error', '')}
    full = res.pop('_result')
    cap = paths.official_config()['cache_capacity_bytes']
    row = {'case': case, 'num_cores': n, 'makespan': res['makespan'],
           'official_hit_bytes': res['cache_hit_bytes'],
           'official_miss_bytes': res['cache_miss_bytes'],
           'hit_rate': res['cache_hit_rate']}
    row.update(split_events(g, plan, full['cache_events'], cap))
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--jobs', type=int, default=16)
    args = ap.parse_args()
    finals = [r for r in plots.read_csv('final.csv') if int(r['problem']) == 3]
    feats = {f['case']: f['n_ops'] for f in json.loads(
        (paths.RESULTS_DIR / 'features.json').read_text(encoding='utf-8'))}
    finals.sort(key=lambda r: -feats.get(r['case'], 0))
    rows = []
    with ProcessPoolExecutor(max_workers=args.jobs) as ex:
        futs = [ex.submit(task, r['case'], int(r['num_cores']), r['plan_path'])
                for r in finals]
        for i, fut in enumerate(as_completed(futs), 1):
            rows.append(fut.result())
            if i % 25 == 0 or i == len(futs):
                print(f'{i}/{len(futs)}', flush=True)
    rows.sort(key=lambda r: (r['num_cores'], r['case']))
    experiment.write_csv(rows, paths.RESULTS_DIR / 'l2_sources.csv')
    summary = {'by_n': {}}
    ok = [r for r in rows if not r.get('error')]
    for n in sorted({r['num_cores'] for r in ok}):
        sub = [r for r in ok if r['num_cores'] == n]
        d = {k: sum(r[k] for r in sub)
             for k in [f'hit_{x}' for x in HIT_KINDS] + [f'miss_{x}' for x in MISS_KINDS]
             + ['official_hit_bytes', 'official_miss_bytes']}
        misses = sum(d[f'miss_{x}'] for x in MISS_KINDS)
        d['hit_sum_equals_official'] = (
            sum(d[f'hit_{x}'] for x in HIT_KINDS) == d['official_hit_bytes'])
        d['miss_sum_equals_official'] = misses == d['official_miss_bytes']
        d['concurrent_first_read_share_of_miss'] = (
            round(d['miss_concurrent_first_read'] / misses, 4) if misses else 0.0)
        d['configs'] = len(sub)
        summary['by_n'][str(n)] = d
    summary['hit_sum_equals_official'] = all(
        v['hit_sum_equals_official'] for v in summary['by_n'].values())
    summary['errors'] = sum(1 for r in rows if r.get('error'))
    (paths.RESULTS_DIR / 'l2_sources.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
