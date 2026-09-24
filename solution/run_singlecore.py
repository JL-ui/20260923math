"""预计算全部用例的官方单核基准（加速比分母），结果写入 results/cache。

    python solution/run_singlecore.py [--jobs 12] [--cases case_001 ...]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from npu import paths                                    # noqa: E402
from npu.evaluate import singlecore_baseline             # noqa: E402


def work(case: str):
    t0 = time.perf_counter()
    out = singlecore_baseline(case)
    return case, out, time.perf_counter() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--jobs', type=int, default=12)
    ap.add_argument('--cases', nargs='*')
    args = ap.parse_args()
    cases = args.cases or paths.all_cases()
    done = {}
    with ProcessPoolExecutor(max_workers=args.jobs) as ex:
        futures = {ex.submit(work, c): c for c in cases}
        for fut in as_completed(futures):
            case, out, secs = fut.result()
            done[case] = out
            print('{:14s} makespan={:>12} added={:>10} feasible={} {:.1f}s'.format(
                case, out.get('makespan'), out.get('added_copy_bytes'),
                out.get('feasible'), secs), flush=True)
    summary = paths.RESULTS_DIR / 'singlecore_baseline.json'
    summary.write_text(json.dumps(done, ensure_ascii=False, indent=1),
                       encoding='utf-8')
    bad = [c for c, v in done.items() if not v.get('feasible')]
    print('\nwrote', summary, 'infeasible:', bad)


if __name__ == '__main__':
    main()
