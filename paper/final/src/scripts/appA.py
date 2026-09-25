"""生成附录 A 的逐用例结果表（Markdown），数据只取自 results/final.csv 与 results/n1.csv。

    python paper/final/src/scripts/appA.py
输出 paper/final/src/md/90_appA.md。
"""

from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
RES = ROOT / 'results'
OUT = Path(__file__).resolve().parents[1] / 'md' / '90_appA.md'


def read(name):
    with (RES / name).open(encoding='utf-8', newline='') as fh:
        return list(csv.DictReader(fh))


final = read('final.csv')
n1 = read('n1.csv')
rows = {}
for r in final:
    rows[(r['case'], int(r['problem']), int(r['num_cores']))] = r
for r in n1:
    rows[(r['case'], int(r['problem']), 1)] = r
cases = sorted({r['case'] for r in final})
assert len(cases) == 100


def table(title, problem, field, fmt, note=None):
    out = [f'Table: {title}', '',
           '| 用例 | $N=1$ | $N=2$ | $N=3$ | $N=4$ | $N=5$ |',
           '|:--|--:|--:|--:|--:|--:|']
    for c in cases:
        cells = [fmt(rows[(c, problem, n)], c, n) for n in range(1, 6)]
        out.append(f'| {c} | ' + ' | '.join(cells) + ' |')
    out.append('')
    if note:
        out += [note, '']
    return '\n'.join(out)


def mk(r, c, n):
    return str(int(r['makespan']))


def add(r, c, n):
    return str(int(r['added_copy_bytes']))


def hit(r, c, n):
    v = r.get('cache_hit_rate')
    return f'{100 * float(v):.1f}' if v not in (None, '') else '—'


def gain(r, c, n):
    return f'{int(rows[(c, 2, n)]["makespan"]) / int(r["makespan"]):.3f}'


parts = ['# 附录 A　逐用例结果', '',
         '本附录的全部数值由官方评估脚本在固定配置 `data/config.txt` 下给出。$N=2\\sim5$ 取自 `results/final.csv`（每个 (用例, 问题, 核数) 的最终方案），'
         '$N=1$ 取自 `results/n1.csv`（整图一个子图、放在 0 号核，由对应问题的评估器评估）。Makespan 单位为 cycle，额外搬运量单位为字节。'
         '对应的方案文件为 `results/final_plans/p<问题>/n<核数>/<用例>_multicore_res.json`（$N\\ge2$），可按附录 B 的命令逐个复核。', '',
         '## A.1　问题一（场景 A）', '',
         table('表 A-1　问题一各用例的 Makespan（cycle）', 1, 'makespan', mk),
         table('表 A-2　问题一各用例的总额外数据搬运量（字节）', 1, 'added', add),
         '## A.2　问题二（场景 B）', '',
         table('表 A-3　问题二各用例的 Makespan（cycle）', 2, 'makespan', mk),
         table('表 A-4　问题二各用例的总额外数据搬运量（字节）', 2, 'added', add),
         '## A.3　问题三（无 L2 与只读 Cache）', '',
         '无 L2 配置即场景 B 不带 Cache，其逐用例 Makespan 与总额外搬运量就是表 A-3、表 A-4（该配置没有 Cache 命中率）。'
         '只读 Cache 配置的结果见表 A-5～表 A-7，表 A-8 给出只读 Cache 相对无 L2 的加速比 $\\mathrm{MK}_{\\text{无 L2}}/\\mathrm{MK}_{\\text{只读 Cache}}$。', '',
         table('表 A-5　问题三（只读 Cache）各用例的 Makespan（cycle）', 3, 'makespan', mk),
         table('表 A-6　问题三（只读 Cache）各用例的总额外数据搬运量（字节）', 3, 'added', add),
         table('表 A-7　问题三（只读 Cache）各用例的 Cache 命中率（按字节，%）', 3, 'hit', hit),
         table('表 A-8　只读 Cache 相对无 L2 的加速比', 3, 'gain', gain,
               note='注：大于 1 表示只读 Cache 更快。case_030 与 case_048 在 $N=3$ 时的值略小于 1（相对差分别为 0.0012% 与 0.0067%），保留三位小数后显示为 1.000，即第 8.4 节所述的 FIFO 时序例外。'),
         ]
OUT.write_text('\n'.join(parts) + '\n', encoding='utf-8')
print('written', OUT)
