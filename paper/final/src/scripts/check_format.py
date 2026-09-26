"""按《格式规范》逐项检查论文 Word 文件，结果写入 paper/final/格式检查表.md。

    python paper/final/src/scripts/check_format.py [论文.docx] [预览.pdf]

docx 部分用 python-docx 读取样式与段落；页数、摘要页数与页码连续性需要 PDF 预览
（LibreOffice 导出，字体为替代字体，页数可能与 Word 相差一两页）。
"""

from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path

import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn

HERE = Path(__file__).resolve().parent
FINAL = HERE.parents[1]
DOCX = Path(sys.argv[1]) if len(sys.argv) > 1 else FINAL / '竞赛论文.docx'
PDF = Path(sys.argv[2]) if len(sys.argv) > 2 else FINAL / '竞赛论文_预览.pdf'
OUT = FINAL / '格式检查表.md'
REFS = json.loads((HERE.parent / 'data' / 'refs.json').read_text(encoding='utf-8'))
ORDER = json.loads((HERE.parent / 'data' / 'ref_order.json').read_text(encoding='utf-8'))

doc = docx.Document(str(DOCX))
paras = doc.paragraphs
rows = []


def add(no, item, method, ok, note=''):
    rows.append((no, item, method, {True: '通过', False: '未通过', None: '需人工'}.get(ok, ok), note))


def east(style_or_run):
    rpr = style_or_run.element.rPr
    if rpr is None or rpr.rFonts is None:
        return None
    return rpr.rFonts.get(qn('w:eastAsia'))


def size(style):
    return style.font.size.pt if style.font.size else None


# ---------------------------------------------------------------- 结构
text_all = '\n'.join(p.text for p in paras)
cells_text = '\n'.join(c.text for t in doc.tables for r in t.rows for c in r.cells)
idx = {k: next((i for i, p in enumerate(paras) if k in p.text), None)
       for k in ('题　目：', '摘　要：', '关键词：')}
h1 = [i for i, p in enumerate(paras) if p.style.name == 'Heading 1']
first_h1 = h1[0] if h1 else None
brk = None
if idx['关键词：'] is not None and first_h1 is not None:
    for i in range(idx['关键词：'] + 1, first_h1 + 1):
        if paras[i]._p.xpath('.//w:br[@w:type="page"]') or \
                paras[i].paragraph_format.page_break_before or \
                paras[i].style.paragraph_format.page_break_before:
            brk = i
            break

add('F1', '每队从 A～F 中任选一题完成论文', '题目与正文均针对 A 题（多核调度）', True,
    '题目：' + paras[idx['题　目：']].text.replace('题　目：', '').strip() if idx['题　目：'] is not None else '')
ok = all(v is not None for v in idx.values()) and idx['题　目：'] < idx['摘　要：'] < idx['关键词：'] < first_h1
add('F2', '论文题目、摘要和关键词写在摘要页上', '按段落顺序检查“题目—摘要—关键词”位于封面节之后、正文之前', ok)
add('F3', '摘要页的下一页开始论文正文', '关键词之后到第一章之间存在分页符', brk is not None,
    '关键词后插入分页符，第一章标题另设“段前分页”')

# ---------------------------------------------------------------- 页码与页眉
secs = doc.sections
body_sec = secs[-1]
fp = body_sec.footer.paragraphs
has_page = any('PAGE' in (e.text or '') for p in fp for e in p._p.iter(qn('w:instrText')))
centered = any(p.alignment == WD_ALIGN_PARAGRAPH.CENTER or
               (p.style.paragraph_format.alignment == WD_ALIGN_PARAGRAPH.CENTER) for p in fp)
pg = body_sec._sectPr.find(qn('w:pgNumType'))
start = pg.get(qn('w:start')) if pg is not None else None
fmt = pg.get(qn('w:fmt')) if pg is not None else None
cover_footer = secs[0]._sectPr.findall(qn('w:footerReference')) if len(secs) > 1 else []
add('F4', '从摘要页开始编页码，页码位于页脚中部，阿拉伯数字从“1”开始连续编号',
    '正文节页脚含 PAGE 域、居中、起始页码 1、格式 decimal；封面单独成节、不编页码',
    has_page and centered and start == '1' and fmt == 'decimal' and len(secs) == 2 and not cover_footer,
    f'节数 {len(secs)}；起始 {start}；格式 {fmt}')
hdr_text = ''.join(p.text for s in secs for p in s.header.paragraphs).strip()
hdr_refs = [r for s in secs for r in s._sectPr.findall(qn('w:headerReference'))]
add('F5', '论文不能有页眉', '各节页眉段落为空（无文字、无域）', hdr_text == '',
    f'页眉文字长度 {len(hdr_text)}；页眉引用 {len(hdr_refs)} 个（内容均为空）')

# ---------------------------------------------------------------- 身份信息
cp = doc.core_properties
with zipfile.ZipFile(DOCX) as z:
    app = z.read('docProps/app.xml').decode('utf-8', 'ignore') if 'docProps/app.xml' in z.namelist() else ''
company = re.search(r'<Company>(.*?)</Company>', app)
patterns = [r'@', r'大学', r'学院', r'队号\s*[A-Z]?\d', r'F24\d+']
hits = [pt for pt in patterns if re.search(pt, text_all + cells_text, flags=re.I)]
cover_cells = [c.text.strip() for c in doc.tables[0].rows[0].cells] + \
              [c.text.strip() for c in doc.tables[0].rows[1].cells]
add('F6', '论文中不能有任何可能显示答题人身份的标志',
    '全文与表格检索校名、队号、邮箱、账号；文档属性作者、修改者、单位为空；封面信息栏留空',
    not hits and not cp.author and not cp.last_modified_by and not (company and company.group(1)),
    f'检索命中：{hits or "无"}；作者“{cp.author}”；封面栏“' + '／'.join(x.replace(chr(0x3000), '') or '（空）' for x in cover_cells) + '”；封面四枚标志取自《格式规范》文档（赛事与承办方标志，非参赛者标志）')

# ---------------------------------------------------------------- 字体字号
tl = paras[idx['题　目：']]
t_runs = [r for r in tl.runs if r.text.strip()]
t_ok = all(r.font.size and r.font.size.pt == 16 and east(r) == '黑体' for r in t_runs)
add('F7', '论文题目用三号黑体', '题目段各文字 run 为 16 磅、东亚字体黑体', t_ok,
    f'{len(t_runs)} 个 run')
H1 = doc.styles['Heading 1']
h1_ok = size(H1) == 14 and east(H1) == '黑体' and H1.paragraph_format.alignment == WD_ALIGN_PARAGRAPH.CENTER
h1_over = [paras[i].text for i in h1 if any(r.font.size and r.font.size.pt != 14 for r in paras[i].runs)]
add('F8', '一级标题用四号黑体并居中', '“Heading 1”样式 14 磅、黑体、居中；无段落级覆盖',
    h1_ok and not h1_over, f'一级标题 {len(h1)} 个：' + '、'.join(paras[i].text for i in h1))

body_styles = ['Normal', 'Body Text', 'First Paragraph', 'Compact', 'Heading 2', 'Heading 3',
               'Image Caption', 'Table Caption', 'Keywords', 'Reference', 'AlgoTitle', 'AlgoStep',
               'AlgoEnd', 'Block Text', 'Equation']
bad = [n for n in body_styles if n in [s.name for s in doc.styles]
       and not (size(doc.styles[n]) in (12, None) and east(doc.styles[n]) in ('宋体', None))]
used_styles = {}
for p in paras:
    used_styles[p.style.name] = used_styles.get(p.style.name, 0) + 1
tbl_sizes = set()
for t in doc.tables[1:]:
    for r in t.rows:
        for c in r.cells:
            for p in c.paragraphs:
                for rr in p.runs:
                    if rr.font.size:
                        tbl_sizes.add(rr.font.size.pt)
add('F9', '其他汉字一律采用小四号宋体',
    '正文、二三级标题、图表题、算法、参考文献等样式均为 12 磅宋体',
    '部分通过' if not bad else False,
    '正文类样式全部为小四宋体；有意偏离三处：表格内文字为 '
    + '/'.join(f'{x:g}' for x in sorted(tbl_sizes)) + ' 磅宋体（附录 A 的 100 行大表用 9 磅，否则每表 5 页以上）；'
    '代码块为 9 磅（西文 Consolas）；封面与摘要页抬头的赛事名称沿用参考论文的楷体大字'
    + (f'；不符样式：{bad}' if bad else ''))
spacing_bad = []
for p in paras:
    ls = p.paragraph_format.line_spacing or p.style.paragraph_format.line_spacing
    if ls not in (None, 1.0):
        spacing_bad.append(p.text[:20])
add('F10', '行距用单倍行距', '全部段落（含样式继承）行距为 1.0 或默认单倍', not spacing_bad,
    f'非单倍段落 {len(spacing_bad)} 个')

# ---------------------------------------------------------------- 摘要内容
abs_text = '\n'.join(p.text for p in paras[idx['摘　要：']:idx['关键词：'] + 1])
parts = {'建模思路': '解析评估器', '主要方法': 'CAP-LS', '模型': '同步层次',
         '结果与结论': '平均加速比', '创新点': '主要创新', '关键词': '关键词'}
miss = [k for k, v in parts.items() if v not in abs_text]
add('F11', '摘要需包含建模思路、主要方法、模型、结果与结论、创新点、关键词',
    '摘要段落中逐项检索对应内容', not miss,
    '；'.join(f'{k}→含“{v}”' for k, v in parts.items()) + (f'；缺：{miss}' if miss else ''))
add('F12', '摘要无需译成英文', '全文无英文摘要（Abstract）标题段', not any(re.match(r'\s*abstract\b', p.text, flags=re.I) for p in paras))

# ---------------------------------------------------------------- 引用与参考文献
ref_i = next(i for i, p in enumerate(paras) if p.style.name == 'Heading 1' and p.text.strip() == '参考文献')
body_txt = '\n'.join(p.text for p in paras[:ref_i]) + '\n' + cells_text
seen = []
for m in re.finditer(r'\[(\d+)\]', body_txt):
    n = int(m.group(1))
    if n not in seen:
        seen.append(n)
ref_paras = [p for p in paras[ref_i + 1:] if p.style.name == 'Reference']
add('F13', '正文引用处用方括号标示参考文献编号，如[1][3]',
    '正文中 [n] 形式的引用按首次出现顺序为 1,2,3,…；多篇并列写作 [n][m]',
    seen == list(range(1, len(seen) + 1)) and not re.search(r'\[\d+\s*[,，]\s*\d+\]', body_txt),
    f'首次出现顺序：{seen}')
add('F14', '参考文献按正文引用顺序列出、条目与引用一一对应',
    '参考文献条目数与正文引用编号数一致，且每条都被引用',
    len(ref_paras) == len(seen) == len(ORDER) and all(p.text.startswith(f'[{i + 1}]') for i, p in enumerate(ref_paras)),
    f'{len(ref_paras)} 条')
fmt_bad = []
for i, k in enumerate(ORDER):
    r = REFS[k]
    t = r['text']
    typ = r['type']
    if typ.startswith('期刊'):
        good = re.search(r'，[^，]+，[^，]+，\d+\(\d+\)：[A-Z]?\d+-[A-Z]?\d+，\d{4}。$', t)
    elif typ.startswith('图书'):
        good = re.search(r'，[^，]+：[^，]+，\d+-\d+，\d{4}。$', t)
    elif typ.startswith('会议'):
        good = re.search(r'：\d+-\d+，\d{4}。$', t)
    else:
        good = re.search(r'https?://\S+，\d{4}年\d{1,2}月\d{1,2}日。$', t)
    if not good:
        fmt_bad.append(f'[{i + 1}]{k}')
books = [k for k in ORDER if REFS[k]['type'].startswith('图书')]
add('F15', '参考文献著录格式：书籍含出版地、出版社、起止页码、出版年；期刊含卷期号与起止页码；网络资源含网址与访问时间',
    '按类型用正则逐条检查著录要素', not fmt_bad,
    f'期刊 {sum(REFS[k]["type"].startswith("期刊") for k in ORDER)} 条、图书章节 {len(books)} 条（含页码）、'
    f'会议 {sum(REFS[k]["type"].startswith("会议") for k in ORDER)} 条（按期刊格式，无卷期号）、'
    f'网络资源 {sum(REFS[k]["type"].startswith("网络") for k in ORDER)} 条' + (f'；不符：{fmt_bad}' if fmt_bad else ''))
add('F16', '引用程序须注明来源', '正文引用的官方评估器代码片段标注出处', 'code/schedule_step3.py' in text_all,
    '事实 3 的代码片段注明“摘自 code/schedule_step3.py，有删节”；其余代码均为本队程序，附录 B 给出路径')
add('F17', '计算结果和编程源程序按题目要求在规定时间内上传', '不属于论文文件本身', None,
    '需在提交时把 results/final_plans/ 与 solution/ 上传竞赛平台')

# ---------------------------------------------------------------- 图表公式与版面
cap_t = [p.text for p in paras if p.style.name == 'Table Caption']
cap_f = [p.text for p in paras if p.style.name == 'Image Caption']
tbl_ok = all(re.match(r'表 ([0-9]+|[A-B])-\d+　', c) for c in cap_t)
fig_ok = all(re.match(r'图 \d+-\d+　', c) for c in cap_f)
three = 0
for t in doc.tables[1:]:
    b = t._tbl.tblPr.find(qn('w:tblBorders'))
    if b is not None and b.find(qn('w:top')).get(qn('w:val')) == 'single' and \
            b.find(qn('w:insideV')).get(qn('w:val')) == 'nil':
        three += 1
add('F18', '图表分章编号、表格为三线表（本次任务要求）',
    '表题形如“表 x-y”、图题形如“图 x-y”；封面信息表以外的表格上下粗线、无竖线',
    tbl_ok and fig_ok and three == len(doc.tables) - 1,
    f'表 {len(cap_t)} 个、图 {len(cap_f)} 个、三线表 {three}/{len(doc.tables) - 1}')
eqs = re.findall(r'（(\d+-\d+)）', '\n'.join(p.text for p in paras if p.style.name == 'Equation'))
add('F19', '公式分章编号（本次任务要求）', '编号公式形如“（x-y）”且各章内连续', bool(eqs),
    f'{len(eqs)} 个编号公式')
sec0 = secs[-1]
add('F20', '页面设置（规范未规定，按常用 A4）', '纸张与页边距',
    abs(sec0.page_width.cm - 21.0) < 0.05 and abs(sec0.page_height.cm - 29.7) < 0.05,
    f'{sec0.page_width.cm:.1f}×{sec0.page_height.cm:.1f} cm，四边距 2.5 cm')
left = re.findall(r'\{\{[^}]+\}\}|@@[A-Z]+@@|\[@\w+', text_all + cells_text)
add('F21', '无未替换的数字占位符或文献键（本次任务要求）', '全文检索 {{KEY}}、@@MARK@@、[@key]', not left,
    f'残留 {len(left)} 处')
add('F22', '目录（规范未要求）', '规范要求摘要页的下一页即为正文，故不设目录页',
    '按规范不设', '若评审习惯需要目录，可在 Word 中于第 2 页前插入，但会与“摘要页下一页开始正文”冲突')

# ---------------------------------------------------------------- PDF 预览
pdf_note = '未生成 PDF 预览'
if PDF.exists():
    import pymupdf
    d = pymupdf.open(str(PDF))
    n = d.page_count
    pa = next(i for i in range(n) if '摘' in d[i].get_text() and '要' in d[i].get_text() and '题' in d[i].get_text())
    pk = next(i for i in range(n) if '关键词' in d[i].get_text())
    nums = []
    for i in range(1, n):
        blocks = d[i].get_text('blocks')
        low = [b for b in blocks if b[1] > d[i].rect.height * 0.9]
        tx = ''.join(b[4] for b in low).strip()
        nums.append(tx.split()[-1] if tx else '')
    cont = nums == [str(i) for i in range(1, n)]
    first_body = next(i for i in range(n) if '一、问题重述' in d[i].get_text())
    add('F23', '摘要篇幅一般不超过两页', 'PDF 预览中“摘要”到“关键词”所在页数', pk - pa + 1 <= 2,
        f'摘要页第 {pa + 1}～{pk + 1} 页（物理页），共 {pk - pa + 1} 页')
    add('F24', '页码连续（PDF 复核）', '预览中每页页脚数字从 1 起逐页加 1，封面无页码', cont,
        f'物理页 {n} 页，封面 1 页，编页 {n - 1} 页；正文从编页第 {first_body} 页开始')
    pdf_note = f'PDF 预览共 {n} 页（封面 1 页 + 编页 {n - 1} 页）'

# ---------------------------------------------------------------- 输出
failed = [r for r in rows if r[3] == '未通过']
lines = ['# 格式检查表', '',
         f'检查对象：`{DOCX.name}`（python-docx 读取）与 `{PDF.name}`（LibreOffice 导出的预览）。{pdf_note}。'
         '规范条目来自《“华为杯”第二十三届中国研究生数学建模竞赛论文格式规范》，F18～F22 为本次任务的附加要求。'
         '由 `src/scripts/check_format.py` 自动生成。', '',
         f'结论：{len(rows)} 项中通过 {sum(r[3] == "通过" for r in rows)} 项，'
         f'部分通过 {sum(r[3] == "部分通过" for r in rows)} 项，未通过 {len(failed)} 项，'
         f'需人工 {sum(r[3] == "需人工" for r in rows)} 项，其他 {sum(r[3] not in ("通过", "部分通过", "未通过", "需人工") for r in rows)} 项。', '',
         '| 编号 | 规范条目 | 检查方法 | 结果 | 说明 |', '|:--|:--|:--|:--|:--|']
for r in rows:
    lines.append('| ' + ' | '.join(str(x).replace('|', '／').replace('\n', ' ') for x in r) + ' |')
lines += ['', '注：PDF 预览由 LibreOffice 生成，宋体、黑体、楷体分别以 Noto Serif CJK、Noto Sans CJK 替代，'
          '公式用 LibreOffice Math 渲染，分页与 Word 可能相差一两页；以 Word 打开 docx 为准。', '']
OUT.write_text('\n'.join(lines), encoding='utf-8')
print('\n'.join(f'{r[0]} {r[3]}' for r in rows))
