"""保底池：对每个 (用例, 问题, 核数) 汇集全部可重建方案，取官方评估最优者为冠军。

    python solution/build_pool.py --jobs 16 [--cases case_001 ...]

对每个用例按 N = 2, 3, 4, 5 递增、问题 1, 2, 3 依次：
  1. 候选 = variants.LABELS(problem, N)；问题 2 另加 x3_c*（问题 3 的候选参数构造、
     问题 2 评估）。问题 2/3 全部走评估缓存；问题 1 缓存未命中时，只有该标签在
     main/baseline/ablation/granularity 中有同配置记录、且记录值小于当前 main.csv
     冠军时才评估，否则跳过（计入 p1_pruned_labels）。凡有记录的标签，评估值必须
     与记录逐位相等，不等者写入 results/pool_mismatch.csv 且不入池。
  2. N−1 嵌入：同问题 N−1 冠军方案末尾追加一个空核（N=2 时由 single 承担）。
  3. 单核兜底：仅当当前最优加速比 < 1.0 时评估 single。
  4. 冠军 = (makespan, added_copy_bytes, 标签字典序) 最小。
在同一 N 的问题 2、3 都完成后做跨问题互投（cross_from_p2 / cross_from_p3）。

输出：results/final.csv（冠军）、results/pool.csv（全部评估过的候选）、
results/plans_final/<case>_p<problem>_n<N>.json。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from npu import algorithms, evaluate, experiment, paths, plots, variants  # noqa: E402

CORES = (2, 3, 4, 5)
PROBLEMS = (1, 2, 3)
PLAN_DIR = paths.RESULTS_DIR / 'plans_final'

_RECORDS = None


def _label_of(stage, r):
    if stage == 'main':
        v = r.get('variant') or ''
        return v if v.startswith('c') and v[1:].isdigit() else None
    if stage == 'baseline':
        return 'b_' + r['algorithm']
    if stage == 'ablation':
        return 'a_' + r['variant']
    if stage == 'granularity':
        return 'g_' + r['variant']
    return None


def records():
    """{(case, problem, N, label): makespan}（只取 eval_problem == problem 的可行记录），
    以及 main.csv 问题 1 冠军 {(case, N): makespan}。"""
    global _RECORDS
    if _RECORDS is None:
        rec, champ = {}, {}
        for stage in ('main', 'baseline', 'ablation', 'granularity'):
            for r in plots.read_csv(f'{stage}.csv'):
                if not r['feasible'] or r['makespan'] is None:
                    continue
                p = int(r['problem'])
                if int(r.get('eval_problem') or p) != p:
                    continue
                n = int(r['num_cores'] or 0)
                if stage == 'main' and p == 1:
                    key = (r['case'], n)
                    champ[key] = min(champ.get(key, r['makespan']), r['makespan'])
                label = _label_of(stage, r)
                if label:
                    rec.setdefault((r['case'], p, n, label), r['makespan'])
        _RECORDS = (rec, champ)
    return _RECORDS


def build_label(g, label, problem, n):
    if label.startswith('x3_c'):
        params = algorithms.candidate_params(3, n, 'full')[int(label[4:])]
        return evaluate.canonical_plan(algorithms.cap_ls(g, n, 3, **params))
    return variants.build(g, label, problem, n)


def label_params(label, problem, n):
    if label.startswith('x3_c'):
        return algorithms.candidate_params(3, n, 'full')[int(label[4:])]
    return variants.label_params(label, problem, n)


def _key(item):
    res = item['res']
    return (res['makespan'], res.get('added_copy_bytes') or 0, item['label'])


def champion(pool):
    ok = [it for it in pool.values() if it['res'].get('feasible')]
    return min(ok, key=_key) if ok else None


def task_case(case):
    g = experiment.get_graph(case)
    base_mk = evaluate.singlecore_baseline(case).get('makespan')
    cache = evaluate.default_cache()
    rec, main_champ = records()
    champs, pools = {}, {}
    final_rows, pool_rows, mismatch = [], [], []
    pruned = {}

    def run(problem, label, plan, runtime=0.0, eval_problem=None):
        ep = eval_problem or problem
        res = cache.evaluate(ep, case, plan)
        if not res.get('cached'):
            cache.flush()
        return {'label': label, 'plan': plan, 'res': res, 'runtime': runtime}

    for n in CORES:
        for problem in PROBLEMS:
            pool = {}
            labels = [x for x in variants.LABELS(problem, n) if x != 'single']
            if problem == 2:
                labels += ['x3_c{}'.format(i) for i in
                           range(len(algorithms.candidate_params(3, n, 'full')))]
            npruned = 0
            for label in labels:
                t0 = time.perf_counter()
                try:
                    plan = build_label(g, label, problem, n)
                except Exception as exc:                        # noqa: BLE001
                    pool_rows.append({'case': case, 'problem': problem,
                                      'num_cores': n, 'label': label,
                                      'feasible': False,
                                      'error': 'PLAN {}: {}'.format(
                                          type(exc).__name__, str(exc)[:120])})
                    continue
                runtime = time.perf_counter() - t0
                if problem == 1:
                    hit = cache.get(1, case, plan)
                    if hit is None:
                        r = rec.get((case, 1, n, label))
                        champ_mk = main_champ.get((case, n))
                        if r is None or champ_mk is None or r >= champ_mk:
                            npruned += 1
                            continue
                        item = run(1, label, plan, runtime)
                    else:
                        res = dict(hit)
                        res['cached'] = True
                        item = {'label': label, 'plan': plan, 'res': res,
                                'runtime': runtime}
                else:
                    item = run(problem, label, plan, runtime)
                want = rec.get((case, problem, n, label))
                got = item['res'].get('makespan') if item['res'].get('feasible') else None
                if want is not None and got != want:
                    mismatch.append({'case': case, 'problem': problem,
                                     'num_cores': n, 'label': label,
                                     'recorded_makespan': want,
                                     'evaluated_makespan': got,
                                     'error': item['res'].get('error', '')})
                    continue
                pool[label] = item
            if n >= 3:
                prev = champs[(problem, n - 1)]
                plan = evaluate.canonical_plan({
                    'node_to_subgraph': prev['plan']['node_to_subgraph'],
                    'core_schedules': [list(o) for o in prev['plan']['core_schedules']]
                    + [[]]})
                label = 'embed_n{}'.format(n - 1)
                pool[label] = run(problem, label, plan)
            best = champion(pool)
            if best is None or (base_mk and base_mk / best['res']['makespan'] < 1.0):
                pool['single'] = run(problem, 'single',
                                     variants.build(g, 'single', problem, n))
            champs[(problem, n)] = champion(pool)
            pools[(problem, n)] = pool
            pruned[(problem, n)] = npruned
        # 跨问题互投
        p2, p3 = champs[(2, n)], champs[(3, n)]
        pools[(3, n)]['cross_from_p2'] = run(3, 'cross_from_p2', p2['plan'])
        pools[(2, n)]['cross_from_p3'] = run(2, 'cross_from_p3', p3['plan'])
        for problem in (2, 3):
            champs[(problem, n)] = champion(pools[(problem, n)])

        for problem in PROBLEMS:
            best = champs[(problem, n)]
            for label, it in pools[(problem, n)].items():
                res = it['res']
                pool_rows.append({
                    'case': case, 'problem': problem, 'num_cores': n,
                    'label': label, 'feasible': bool(res.get('feasible')),
                    'makespan': res.get('makespan'),
                    'added_copy_bytes': res.get('added_copy_bytes'),
                    'speedup': (round(base_mk / res['makespan'], 4)
                                if res.get('feasible') and base_mk else None),
                    'cached': bool(res.get('cached')),
                    'is_champion': it is best,
                    'error': res.get('error', '')})
            if best is None:
                continue
            res = best['res']
            PLAN_DIR.mkdir(parents=True, exist_ok=True)
            path = PLAN_DIR / f'{case}_p{problem}_n{n}.json'
            path.write_text(json.dumps(best['plan'], ensure_ascii=False),
                            encoding='utf-8')
            params = label_params(best['label'], problem, n)
            if params is None:
                pjson = best['label']
                if problem == 1:
                    pjson = json.dumps({'label': best['label'],
                                        'p1_pruned_labels': pruned[(1, n)]})
            else:
                params = dict(params)
                if problem == 1:
                    params['p1_pruned_labels'] = pruned[(1, n)]
                pjson = json.dumps(params, sort_keys=True)
            final_rows.append({
                'case': case, 'problem': problem, 'eval_problem': problem,
                'num_cores': n, 'algorithm': 'capls',
                'variant': 'pool:' + best['label'], 'seed': 0,
                'runtime_s': round(best['runtime'], 3),
                'eval_s': res.get('eval_seconds'),
                'feasible': True, 'makespan': res['makespan'],
                'added_copy_bytes': res.get('added_copy_bytes'),
                'partition_added_copy_bytes': res.get('partition_added_copy_bytes'),
                'spill_added_copy_bytes': res.get('spill_added_copy_bytes'),
                'scheduled_copy_bytes': res.get('scheduled_copy_bytes'),
                'cache_hit_rate': res.get('cache_hit_rate'),
                'cache_hit_bytes': res.get('cache_hit_bytes'),
                'n_subgraphs': len(set(best['plan']['node_to_subgraph'].values())),
                'baseline_makespan': base_mk, 'error': '',
                'speedup': base_mk / res['makespan'] if base_mk else None,
                'params': pjson, 'is_best': True,
                'plan_path': str(path.relative_to(paths.ROOT)),
            })
    cache.flush()
    return final_rows, pool_rows, mismatch


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--jobs', type=int, default=16)
    ap.add_argument('--cases', nargs='*')
    ap.add_argument('--final', default=str(paths.RESULTS_DIR / 'final.csv'))
    ap.add_argument('--pool', default=str(paths.RESULTS_DIR / 'pool.csv'))
    ap.add_argument('--mismatch', default=str(paths.RESULTS_DIR / 'pool_mismatch.csv'))
    args = ap.parse_args()
    cases = args.cases or paths.all_cases()
    feats = {f['case']: f['n_ops'] for f in json.loads(
        (paths.RESULTS_DIR / 'features.json').read_text(encoding='utf-8'))}
    cases = sorted(cases, key=lambda c: (-feats.get(c, 0), c))
    t0 = time.time()
    finals, pools, bad = [], [], []
    with ProcessPoolExecutor(max_workers=args.jobs) as ex:
        futs = {ex.submit(task_case, c): c for c in cases}
        for i, fut in enumerate(as_completed(futs), 1):
            case = futs[fut]
            try:
                f, p, m = fut.result()
            except Exception as exc:                            # noqa: BLE001
                print('CASE FAILED:', case, type(exc).__name__, str(exc)[:300],
                      flush=True)
                continue
            finals.extend(f)
            pools.extend(p)
            bad.extend(m)
            print('[pool] {}/{} {}  {:.0f}s  mismatches={}'.format(
                i, len(cases), case, time.time() - t0, len(bad)), flush=True)
    key = lambda r: (r['case'], int(r['problem']), int(r['num_cores']))  # noqa: E731
    finals.sort(key=key)
    pools.sort(key=lambda r: key(r) + (r['label'],))
    experiment.write_csv(finals, Path(args.final))
    experiment.write_csv(pools, Path(args.pool))
    if bad:
        experiment.write_csv(bad, Path(args.mismatch))
    else:                                     # 空表（只有表头），覆盖旧结果
        Path(args.mismatch).write_text(
            'case,problem,num_cores,label,recorded_makespan,evaluated_makespan,error\n',
            encoding='utf-8')
    print('final -> {} ({} rows); pool -> {} ({} rows); mismatches={}; {:.0f}s'.format(
        args.final, len(finals), args.pool, len(pools), len(bad), time.time() - t0))


if __name__ == '__main__':
    main()
