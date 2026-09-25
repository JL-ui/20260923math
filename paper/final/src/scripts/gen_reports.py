"""生成《数字溯源表》与《参考文献核验表》。须先运行 build.py（它写出 used_facts.json、ref_order.json）。

    python paper/final/src/scripts/gen_reports.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parent
FINAL = SRC.parent
DATA, MD = SRC / 'data', SRC / 'md'

facts = json.loads((DATA / 'facts.json').read_text(encoding='utf-8'))
used = json.loads((DATA / 'used_facts.json').read_text(encoding='utf-8'))
refs = json.loads((DATA / 'refs.json').read_text(encoding='utf-8'))
order = json.loads((DATA / 'ref_order.json').read_text(encoding='utf-8'))


def cell(s):
    return str(s).replace('|', '／').replace('\n', ' ')


def shown(v):
    return re.sub(r'(?<=\d),(?=\d{3}(?!\d))', '', str(v))


# 每个键首次出现的章节
where = {}
for f in sorted(MD.glob('*.md')):
    sec = '摘要' if f.name.startswith('00') else ''
    for line in f.read_text(encoding='utf-8').splitlines():
        m = re.match(r'#{1,2}\s+(.*)', line)
        if m:
            sec = m.group(1).strip()
        for k in re.findall(r'\{\{([A-Za-z0-9_.]+)\}\}', line):
            where.setdefault(k, sec)

lines = ['# 数字溯源表', '',
         '论文正文与附录中的全部实验数字都由 `src/scripts/facts.py` 从 `results/` 下的 csv 与 json 提取，写入 '
         '`src/data/facts.json`，再由 `build.py` 替换进各章的 `{{KEY}}` 占位符；构建时任何缺失的键都会报错。'
         '下表按首次出现顺序列出论文实际用到的每一个键。“论文中的值”即排版后的写法；“来源”为 facts.py 记录的文件与字段'
         '（以“…”开头的表示与上一行同一文件）。附录 A 的逐用例表由 `appA.py` 直接读取 `results/final.csv` 与 '
         '`results/n1.csv` 生成，不经过占位符，见表末说明。', '',
         f'共 {len(used)} 个键。', '',
         '| 序号 | 键 | 论文中的值 | 首次出现 | 来源 |', '|--:|:--|:--|:--|:--|']
for i, k in enumerate(used, 1):
    lines.append(f'| {i} | `{k}` | {cell(shown(facts[k]["v"]))} | {cell(where.get(k, ""))} | {cell(facts[k]["src"])} |')
lines += ['', '## 附录 A 与图表', '',
          '* 表 A-1～A-8：`appA.py` 读取 `results/final.csv`（$N=2\\sim5$，列 makespan、added_copy_bytes、cache_hit_rate）'
          '与 `results/n1.csv`（$N=1$）；表 A-8 为同一用例同一核数下问题二与问题三 makespan 之比。',
          '* 全部图：`figs.py` 只读取 `results/` 下的文件生成，图中标注的数值与上表同源。', '',
          '## 不来自实验的数字', '',
          '以下数字是题设参数、算法参数或解析推导，不是实验结果：', '',
          '| 数字 | 出处 | 位置 |', '|:--|:--|:--|',
          '| L1 524288 B、UB 131072 B、DDR 60 B/cycle、L2 1 MB 与 250 B/cycle | `data/config.txt`（官方固定配置） | 1.1 节、表 4-1、第 8 章 |',
          '| 同核等待 100 cycle、跨核等待 1000 cycle、同步延迟 500 cycle | `data/config.txt` 与赛题正文 | 1.2 节、第 5～7 章 |',
          '| 5～10 分钟 | 赛题对问题一“高效”的说明 | 1.2 节、6.4 节、6.6 节 |',
          '| θ ∈ {∞,16,8,4,2,1}、β 取值、260 个块、移动上限 min(max(300,8m′),2200)、至多 6 轮 | `solution/npu/partition.py`、`assign.py`、`algorithms.py` | 6.3 节、表 6-1 |',
          '| 候选网格 c0～c17 的参数 | `solution/npu/algorithms.py` 候选网格 | 表 6-1、7.2 节 |',
          '| 问题一裁剪阈值 6000/12000 个算子、兜底阈值 600 s（按 `results/main.csv` 中问题一候选 eval_s 的中位数） | `solution/npu/experiment.py`（`_large_p1_cases` 与候选裁剪） | 6.4 节 |',
          '| 退火 1500 步、初温 2%、终温 10⁻³、种子 20260924、保留 3 个方案 | `solution/npu/p1_anneal.py` | 6.4 节、附录 B |',
          '| 表调度：秩前 64 个、α/μ/ν 取值、η=0.05、16 个种子 | `solution/npu/listsched.py`、`solution/npu/variants.py` | 7.2 节 |',
          '| 0.0127、76%、52% | 由 1/60−1/250、(1/60−1/250)/(1/60)、(1/60−1/125)/(1/60) 解析得到 | 式（8-2）、8.3 节 |',
          '| 10～11 cycle | 由 `COND4_LIST` 中两个例外的 Makespan 相减得到 | 10.2 节 |',
          '| 约 7.1×10⁵ cycle 的整核空转（case_062，N=4） | 项目早期对评估器执行轨迹的诊断（见仓库 CLAUDE.md“不变量 3”），不属于 results/ 的正式实验 | 2.2 节事实 3 |',
          '| 敏感性扫描的参数取值（64 KB～16 MB、60～1000 B/cycle 等） | `solution/run_experiments.py --stage sensitivity` 的参数网格 | 8.3 节、9.5 节 |',
          '']
(FINAL / '数字溯源表.md').write_text('\n'.join(lines), encoding='utf-8')

rl = ['# 参考文献核验表', '',
      '全部文献按正文首次引用顺序编号。每条都用题名在网上检索过（WebSearch），记录命中的页面与核对到的信息；'
      '“页码”一栏写明是否在检索页面上核对到起止页码，未核对到的按该文献的常见著录填写。'
      '网络资源条目的访问时间为检索当天。文献条目的著录格式按《格式规范》：期刊为“作者，论文名，杂志名，卷期号：起止页码，出版年”，'
      '书籍为“作者，书名，出版地：出版社，起止页码，出版年”，网上资源为“作者，资源标题，网址，访问时间”；'
      '会议论文按期刊格式、以会议录名代替杂志名。', '',
      '| 编号 | 键 | 类型 | 条目 | 核验方式与结果 | 页码 | 链接 | 正文引用位置 |', '|--:|:--|:--|:--|:--|:--|:--|:--|']
cites = {}
for f in sorted(MD.glob('*.md')):
    sec = '摘要' if f.name.startswith('00') else ''
    for line in f.read_text(encoding='utf-8').splitlines():
        m = re.match(r'#{1,2}\s+(.*)', line)
        if m:
            sec = m.group(1).strip().split('　')[0].split(' ')[0]
        for grp in re.findall(r'\[(@[\w\-]+(?:\s*;\s*@[\w\-]+)*)\]', line):
            for k in re.findall(r'@([\w\-]+)', grp):
                cites.setdefault(k, [])
                if sec not in cites[k]:
                    cites[k].append(sec)
for i, k in enumerate(order, 1):
    r = refs[k]
    rl.append(f'| [{i}] | `{k}` | {cell(r["type"])} | {cell(r["text"])} | {cell(r["checked"])} | '
              f'{cell(r["pages"])} | {cell(r["url"])} | {cell("、".join(cites.get(k, [])))} |')
confirmed = sum('已核对' in refs[k]['pages'] for k in order)
rl += ['', f'共 {len(order)} 条，其中页码在检索页面上核对到的 {confirmed} 条；其余条目的题名、作者、刊名与年份均已核对，'
       '页码未能在检索结果中看到，按常见著录填写，定稿前如有条件可再用数据库核对一次。', '']
(FINAL / '参考文献核验表.md').write_text('\n'.join(rl), encoding='utf-8')
print('facts used', len(used), 'refs', len(order), 'confirmed pages', confirmed)
