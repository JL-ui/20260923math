# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Sonnet 5（型号 claude-sonnet-5）、Claude Opus 5.5（型号 claude-opus-5-5）
# 开发机构：Anthropic 公司
# 版本发布日期：Claude Sonnet 5 为 2026-06-30，Claude Opus 5.5 为 2026-09-22
"""模型检验：解析代价模型 F 与官方评估器 Makespan 的一致性。

对每个用例的全部候选方案，同时记录
  * 解析估计（场景 A 用 Task 级事件模拟，场景 B 用每核 Pipe 负载 + 同步深度）
  * 官方评估器给出的 Makespan
然后报告 Pearson / Spearman 相关系数与"用解析模型选出的候选 vs 真最优候选"
的 Makespan 相对差距（即代理模型的选择损失）。

    python solution/validate_model.py --jobs 8 --cases ... -o results/model_validation.csv
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from npu import (algorithms, assign, evaluate, experiment,      # noqa: E402
                 partition, paths, stratify)
from npu.proxy_a import estimate_scene_a_from_plan               # noqa: E402,F401


def _estimate(g, bs, core, num_cores, problem, cfg, plan, proxy='legacy'):
    if proxy == 'sim':
        from npu import simproxy
        return simproxy.estimate(g, plan, problem, cfg)
    if problem == 1:
        mapping = {int(k): int(v) for k, v in plan['node_to_subgraph'].items()}
        return estimate_scene_a_from_plan(g, mapping, plan['core_schedules'], cfg)
    est, _ = assign.estimate_scene_b(
        bs, core, num_cores, cfg,
        cache_capacity=cfg['cache_capacity_bytes'] if problem == 3 else 0)
    return est


def task(case, problem, ncores, proxy='legacy'):
    cfg = paths.official_config()
    g = experiment.get_graph(case)
    rows = []
    for idx, params in enumerate(algorithms.candidate_params(problem, ncores, 'full')):
        params = dict(params)
        active = min(ncores, params.get('cores_used') or ncores)
        try:
            bs = partition.make_blocks(
                g, max(1, active), block_cap=params.get('block_cap', 0.35),
                use_affinity=params.get('use_affinity', True))
            if active <= 1:
                core = [0] * bs.m
            else:
                init = params.get('init', 'lpt')
                if init == 'rr':
                    core = assign.round_robin_assign(bs, active)
                elif init == 'contig':
                    core = assign.contiguous_assign(bs, active)
                else:
                    core = assign.lpt_assign(
                        bs, active, comm_weight=params.get('comm_weight', 0.0))
                state = algorithms.TrafficState(
                    bs, core, active, cfg,
                    sync_penalty=params.get(
                        'sync_weight',
                        cfg['task_cross_core_wait_cycles'] if problem == 1
                        else cfg['cross_core_copy_delay_cycles']),
                    cache_capacity=(cfg['cache_capacity_bytes']
                                    if problem == 3 else 0))
                algorithms._local_search(bs, state, active, problem == 3)
                core = state.core
            if params.get('subgraph_mode') == 'block':
                plan = algorithms._plan_blocks_as_subgraphs(bs, core, ncores)
            else:
                plan = algorithms._plan_from_core_map(
                    g, bs, core, ncores, max_ops=params.get('max_ops'))
            plan = evaluate.canonical_plan(plan)
            est = _estimate(g, bs, core, active, problem, cfg, plan, proxy)
            res = evaluate.default_cache().evaluate(problem, case, plan)
            if not res.get('cached'):
                evaluate.default_cache().flush()     # 大图 P1 单次评估可达半小时
        except Exception as exc:                                # noqa: BLE001
            rows.append({'case': case, 'problem': problem, 'num_cores': ncores,
                         'variant': idx, 'feasible': False,
                         'error': type(exc).__name__})
            continue
        rows.append({'case': case, 'problem': problem, 'num_cores': ncores,
                     'variant': idx, 'feasible': bool(res.get('feasible')),
                     'proxy': proxy,
                     'estimate': round(est, 1),
                     'makespan': res.get('makespan'),
                     'error': res.get('error', '')})
    evaluate.default_cache().flush()
    return rows


def _rank(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    for pos, i in enumerate(order):
        r[i] = pos
    return r


def _corr(xs, ys):
    n = len(xs)
    if n < 3:
        return float('nan')
    mx, my = sum(xs) / n, sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return float('nan')
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def _num(x):
    if x in (None, '', 'None'):
        return None
    return float(x)


def _q(xs, q):
    xs = sorted(xs)
    if not xs:
        return float('nan')
    pos = (len(xs) - 1) * q
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def _r4(x):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) \
        else round(x, 4)


def within_case_report(rows) -> dict:
    """用例内（同一 (case, num_cores) 的候选之间）代理排序质量。

    组内候选按真实 makespan 去重（同值保留候选编号最小者）。
    Spearman / Kendall τ 只在组内候选 ≥ 3 时计算；
    Top-K 减速比 = 代理排序前 K 个中的最小真实 makespan / 组内真实最小 − 1；
    Recall@K = 真实最优是否落在代理前 K 个中。混合秩相关只作附带输出。
    """
    from scipy.stats import kendalltau, spearmanr
    out = {}
    for problem in (1, 2, 3):
        ok = [r for r in rows if int(r['problem']) == problem
              and str(r.get('feasible')).lower() == 'true'
              and _num(r.get('estimate')) and _num(r.get('makespan'))]
        groups = {}
        for r in sorted(ok, key=lambda r: int(r['variant'])):
            g = groups.setdefault((r['case'], int(r['num_cores'])), {})
            mk = _num(r['makespan'])
            if mk not in g:
                g[mk] = _num(r['estimate'])
        sp, kt = [], []
        topk = {1: [], 3: [], 5: []}
        recall = {1: [], 3: [], 5: []}
        for g in groups.values():
            mks = list(g)
            ests = [g[m] for m in mks]
            if len(mks) >= 3:
                s = spearmanr(ests, mks).statistic
                t = kendalltau(ests, mks).statistic
                if not math.isnan(s):
                    sp.append(float(s))
                if not math.isnan(t):
                    kt.append(float(t))
            order = sorted(range(len(mks)), key=lambda i: ests[i])
            best = min(mks)
            for k in (1, 3, 5):
                top = [mks[i] for i in order[:k]]
                topk[k].append(min(top) / best - 1)
                recall[k].append(1.0 if best in top else 0.0)
        pooled = float('nan')
        if len(ok) >= 3:
            pooled = float(spearmanr([_num(r['estimate']) for r in ok],
                                     [_num(r['makespan']) for r in ok]).statistic)
        rep = {
            'n_rows': len(ok), 'n_groups': len(groups), 'n_groups_rank': len(sp),
            'spearman_median': _r4(_q(sp, 0.5)),
            'spearman_mean': _r4(sum(sp) / len(sp)) if sp else None,
            'kendall_median': _r4(_q(kt, 0.5)),
            'kendall_mean': _r4(sum(kt) / len(kt)) if kt else None,
            'pooled_spearman': _r4(pooled),
        }
        for k in (1, 3, 5):
            rep[f'top{k}_slowdown_median'] = _r4(_q(topk[k], 0.5))
            rep[f'top{k}_slowdown_p90'] = _r4(_q(topk[k], 0.9))
            rep[f'top{k}_slowdown_max'] = _r4(max(topk[k])) if topk[k] else None
            rep[f'recall{k}'] = _r4(sum(recall[k]) / len(recall[k])) \
                if recall[k] else None
        out[f'problem{problem}'] = rep
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--jobs', type=int, default=8)
    ap.add_argument('--cases', nargs='*')
    ap.add_argument('--cores', type=int, default=4)
    ap.add_argument('--all', action='store_true',
                    help='全部 100 个用例 × N=2..5')
    ap.add_argument('--proxy', choices=['legacy', 'sim'], default='legacy')
    ap.add_argument('-o', '--output')
    args = ap.parse_args()
    if args.all:
        cases = args.cases or paths.all_cases()
        cores = (2, 3, 4, 5)
        output = args.output or f'results/model_validation_full_{args.proxy}.csv'
    else:
        cases = args.cases or paths.all_cases()[:40]
        cores = (args.cores,)
        output = args.output or 'results/model_validation.csv'
    tasks = [(c, p, n, args.proxy) for c in cases for p in (1, 2, 3) for n in cores]
    # 大图先提交（P1 大图单次官方评估可达半小时），缩短总墙钟时间
    feats = {f['case']: f['n_ops'] for f in json.loads(
        (paths.RESULTS_DIR / 'features.json').read_text(encoding='utf-8'))}
    tasks.sort(key=lambda t: (-feats.get(t[0], 0), t[1], t[2]))
    rows = []
    with ProcessPoolExecutor(max_workers=args.jobs) as ex:
        futs = [ex.submit(task, *t) for t in tasks]
        for i, f in enumerate(as_completed(futs), 1):
            rows.extend(f.result())
            if i % 20 == 0 or i == len(futs):
                print(f'{i}/{len(futs)}', flush=True)
    rows.sort(key=lambda r: (r['case'], r['problem'], r['num_cores'], r['variant']))
    experiment.write_csv(rows, Path(output))

    report = within_case_report(rows)
    report['proxy'] = args.proxy
    report['cases'] = len(cases)
    report['cores'] = list(cores)
    groups = {(r['case'], r['problem'], r['num_cores']) for r in rows
              if r.get('feasible') and r.get('estimate') and r.get('makespan')}
    report['coverage'] = round(len(groups) / len(tasks), 4) if tasks else 0.0
    path = paths.RESULTS_DIR / f'model_validation_summary_{args.proxy}.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1),
                    encoding='utf-8')
    print('\n=== 模型检验（用例内指标）===')
    print(json.dumps(report, ensure_ascii=False, indent=1))
    print('summary ->', path)


if __name__ == '__main__':
    main()
