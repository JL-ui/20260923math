"""最终方案的官方 CLI 复核（T08）。

    python solution/verify_final.py --problems 2 3 --jobs 16
    python solution/verify_final.py --problems 1 --jobs 16

对 results/final_plans/p<P>/n<N>/<case>_multicore_res.json（N=1..5）逐个以子进程调用
官方 CLI（code/multicore_cut_evaluate_problem_<P>.py），读取 makespan、
data_movement_bytes.added_copy_bytes 与（问题 3）cache_stats.hit_rate，
与 results/final_plans/manifest.csv（N≥2）或 results/n1.csv（N=1）逐项比较，
要求完全相等（命中率比较到 1e-9）。结果写 results/verify_final.csv。

官方 CLI 默认把 trace / log 写到图文件旁（data/ 目录，只读），因此这里显式
指定 --trace-output / --log-output 到临时目录；临时文件按并发槽位复用。
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import queue
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from npu import experiment, paths, plots                          # noqa: E402

CORES = (1, 2, 3, 4, 5)


def expected_values():
    exp = {}
    with (paths.RESULTS_DIR / 'final_plans' / 'manifest.csv').open(
            encoding='utf-8', newline='') as fh:
        for r in csv.DictReader(fh):
            hit = r.get('cache_hit_rate')
            exp[(r['case'], int(r['problem']), int(r['num_cores']))] = {
                'makespan': int(r['makespan']),
                'added_copy_bytes': int(r['added_copy_bytes']),
                'cache_hit_rate': float(hit) if hit not in (None, '', 'None') else None}
    for r in plots.read_csv('n1.csv'):
        if r['feasible']:
            exp[(r['case'], int(r['problem']), 1)] = {
                'makespan': r['makespan'],
                'added_copy_bytes': r['added_copy_bytes'],
                'cache_hit_rate': r.get('cache_hit_rate')}
    return exp


def run_cli(problem, case, n, slot, tmpdir):
    plan = (paths.RESULTS_DIR / 'final_plans' / f'p{problem}' / f'n{n}'
            / f'{case}_multicore_res.json')
    out = Path(tmpdir) / f'slot{slot}_res.json'
    cmd = [sys.executable, str(paths.CODE_DIR / f'multicore_cut_evaluate_problem_{problem}.py'),
           str(paths.case_path(case)), str(plan), '--config', str(paths.CONFIG_PATH),
           '-o', str(out),
           '--trace-output', str(Path(tmpdir) / f'slot{slot}_trace.json'),
           '--log-output', str(Path(tmpdir) / f'slot{slot}_log.txt')]
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                          errors='replace', env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    secs = time.perf_counter() - t0
    if proc.returncode != 0 or not out.is_file():
        return {'error': (proc.stderr or proc.stdout)[-300:], 'cli_seconds': round(secs, 1)}
    res = json.loads(out.read_text(encoding='utf-8'))
    got = {'makespan': int(res['makespan']),
           'added_copy_bytes': int(res['data_movement_bytes']['added_copy_bytes']),
           'cache_hit_rate': (float(res['cache_stats']['hit_rate'])
                              if problem == 3 else None),
           'cli_seconds': round(secs, 1), 'error': ''}
    return got


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--problems', nargs='*', type=int, default=[1, 2, 3])
    ap.add_argument('--jobs', type=int, default=8)
    ap.add_argument('--cases', nargs='*')
    ap.add_argument('--out', default=str(paths.RESULTS_DIR / 'verify_final.csv'))
    args = ap.parse_args()
    cases = args.cases or paths.all_cases()
    feats = {f['case']: f['n_ops'] for f in json.loads(
        (paths.RESULTS_DIR / 'features.json').read_text(encoding='utf-8'))}
    exp = expected_values()
    jobs = sorted(((p, c, n) for p in args.problems for c in cases for n in CORES),
                  key=lambda t: (-feats.get(t[1], 0), t))
    tmpdir = Path(tempfile.gettempdir()) / 'npu_verify_final'
    tmpdir.mkdir(parents=True, exist_ok=True)
    slots = queue.Queue()
    for i in range(args.jobs):
        slots.put(i)

    def work(job):
        slot = slots.get()
        try:
            return job, run_cli(*job, slot, tmpdir)
        finally:
            slots.put(slot)

    rows, mismatches = [], 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.jobs) as ex:
        futs = [ex.submit(work, j) for j in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            (p, c, n), got = fut.result()
            want = exp.get((c, p, n))
            ok = bool(want) and not got.get('error')
            if ok:
                ok = (got['makespan'] == want['makespan']
                      and got['added_copy_bytes'] == want['added_copy_bytes'])
                if p == 3:
                    a, b = got['cache_hit_rate'], want['cache_hit_rate']
                    ok = ok and a is not None and b is not None and abs(a - b) <= 1e-9
            mismatches += 0 if ok else 1
            rows.append({'case': c, 'problem': p, 'num_cores': n, 'match': ok,
                         'cli_makespan': got.get('makespan'),
                         'expected_makespan': (want or {}).get('makespan'),
                         'cli_added_copy_bytes': got.get('added_copy_bytes'),
                         'expected_added_copy_bytes': (want or {}).get('added_copy_bytes'),
                         'cli_hit_rate': got.get('cache_hit_rate'),
                         'expected_hit_rate': (want or {}).get('cache_hit_rate'),
                         'cli_seconds': got.get('cli_seconds'),
                         'error': got.get('error', '') or ('' if want else 'no expected value')})
            if i % 50 == 0 or i == len(futs):
                print('[verify] {}/{} {:.0f}s mismatches={}'.format(
                    i, len(futs), time.time() - t0, mismatches), flush=True)
    rows.sort(key=lambda r: (r['problem'], r['num_cores'], r['case']))
    out = Path(args.out)
    old = []
    if out.is_file():                   # 分问题多次运行时保留其他问题的行
        with out.open(encoding='utf-8', newline='') as fh:
            old = [r for r in csv.DictReader(fh)
                   if int(r['problem']) not in args.problems]
    experiment.write_csv(old + rows, out)
    print('checked={} mismatches={}'.format(len(rows), mismatches))
    return 0 if mismatches == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
