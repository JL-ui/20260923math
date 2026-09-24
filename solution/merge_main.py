"""合并主阶段结果：问题 1 的行取自一份 CSV，问题 2/3 的行取自另一份，写回 main.csv。

    python solution/merge_main.py
    python solution/merge_main.py --p1 results/baseline_snapshot/main_before_T06.csv \
                                  --p23 results/main_p23.csv --out results/main.csv

默认值对应 T06：问题 1 保留重跑前的记录（results/baseline_snapshot/main_before_T06.csv），
问题 2/3 取重跑结果（results/main_p23.csv）。
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from npu import paths                                            # noqa: E402


def read(path: Path) -> list:
    with path.open(encoding='utf-8', newline='') as fh:
        return list(csv.DictReader(fh))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--p1', default=str(paths.RESULTS_DIR / 'baseline_snapshot'
                                        / 'main_before_T06.csv'))
    ap.add_argument('--p23', default=str(paths.RESULTS_DIR / 'main_p23.csv'))
    ap.add_argument('--out', default=str(paths.RESULTS_DIR / 'main.csv'))
    args = ap.parse_args()
    p1 = [r for r in read(Path(args.p1)) if str(r['problem']) == '1']
    p23 = [r for r in read(Path(args.p23)) if str(r['problem']) in ('2', '3')]
    rows = p1 + p23
    keys = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with Path(args.out).open('w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=keys, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)
    print('merged: {} P1 rows + {} P2/P3 rows -> {}'.format(len(p1), len(p23), args.out))


if __name__ == '__main__':
    main()
