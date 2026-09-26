"""把 paper/v4/src/*.md 排成 Word（复用 v3 包装脚本与 solution/paper_v2/build_docx.py 的解析器）。

    python paper/v4/tools/build_v4.py --template 草稿.docx --out 论文_v4.docx

在 v3 的基础上只改排版，数字与逐用例表的数据源不变（facts_v3.json、final_standard.csv）：
  1. 不要目录页：摘要页之后直接开始正文；
  2. 插图以 SVG 嵌入，同名 PNG 作为不支持 SVG 的阅读器的回退图；
  3. 全文西文（含公式中的变量）统一为 Times New Roman；
  4. 逐用例表与正文表格同为五号字的三线表。
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "paper" / "v3" / "tools"))
import build_v3 as b3  # noqa: E402  （导入即完成数据源、文献编号与公式转换的替换）

bd = b3.bd
b3.omml._LIMIT_FUNCS.add("lexmin")  # 目标函数的字典序最小化：下标放到正下方
from docx.opc.constants import RELATIONSHIP_TYPE as RT  # noqa: E402
from docx.opc.packuri import PackURI  # noqa: E402
from docx.opc.part import Part  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402
from lxml import etree  # noqa: E402

V4 = ROOT / "paper" / "v4"
TNR = "Times New Roman"
SVG_EXT = "{96DAC541-7B7A-43D3-8B79-37D633B846F1}"
ASVG = "http://schemas.microsoft.com/office/drawing/2016/SVG/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"


# ---------------------------------------------------------------- 2. SVG 插图 + PNG 回退
_orig_figure = bd.Renderer.figure
_svg_count = [0]


def figure(self, b):
    svg = ROOT / b.attrs["path"]
    png = svg.with_suffix(".png")
    if svg.suffix.lower() != ".svg":
        return _orig_figure(self, b)
    if not (svg.exists() and png.exists()):
        raise SystemExit(f"找不到图片：{svg} 或其 PNG 回退图")
    b.attrs["path"] = str(png.relative_to(ROOT))
    before = len(self.body)
    _orig_figure(self, b)
    # 找到刚插入的图片段落，给 a:blip 加上 SVG 扩展
    blip = None
    for k in list(self.body)[before - 1:]:
        found = k.find(".//{%s}blip" % A_NS)
        if found is not None:
            blip = found
            break
    if blip is None:
        raise SystemExit(f"未找到图片元素：{svg}")
    part = self.doc.part
    _svg_count[0] += 1
    svg_part = Part(PackURI(f"/word/media/fig_svg_{_svg_count[0]}.svg"), "image/svg+xml",
                    svg.read_bytes(), part.package)
    rid = part.relate_to(svg_part, RT.IMAGE)
    ext_lst = etree.SubElement(blip, "{%s}extLst" % A_NS)
    ext = etree.SubElement(ext_lst, "{%s}ext" % A_NS, {"uri": SVG_EXT})
    sb = etree.SubElement(ext, "{%s}svgBlip" % ASVG, nsmap={"asvg": ASVG})
    sb.set("{%s}embed" % R_NS, rid)


bd.Renderer.figure = figure

# ---------------------------------------------------------------- 5. 页边距：格式规范未作规定，取与组委会发布的赛题文件相同的四边 2.5 cm
MARGIN = 1417
PAGE_W, PAGE_H = 11906, 16838
bd.TEXT_WIDTH = PAGE_W - 2 * MARGIN          # 版心宽度 16.0 cm（表格、算法框与公式编号的右制表位都用它）


def set_margins(doc):
    for sp in doc.element.body.iter(qn("w:sectPr")):
        pm = sp.find(qn("w:pgMar"))
        for k, v in (("top", MARGIN), ("bottom", MARGIN), ("left", MARGIN), ("right", MARGIN),
                     ("header", 850), ("footer", 850), ("gutter", 0)):
            pm.set(qn("w:" + k), str(v))


# ---------------------------------------------------------------- 4. 逐用例表：按页切块，每块都是完整的三线表
# Word 表格跨页时不会在断开处补画底线，续页也没有顶线；长表因此按页切成若干张完整的三线表，
# 第二块起题注写“续表”，并从新页开始。行高固定（exact），每页能放的行数可以直接算出。
ROW_H, HEAD_H = 255, 300          # 数据行、表头行高（twip）
CAP_H = 120 + 300 + 60            # 题注：段前 + 固定行高 + 段后
SPACER_H = 60 + 120               # 表后空行
BODY_H = PAGE_H - 2 * MARGIN
SAFETY = 420                      # 每页留出的余量
FIRST_USED = 3800                 # 附录首页在第一张表之前已占用的高度（一级、二级标题与说明段落的估计值，偏保守）
_ct_state = {"used": None, "end": None}


def _fix_line(p, line, rule="exact", before=None, after=None):
    pp = p.find(qn("w:pPr"))
    sp = pp.find(qn("w:spacing"))
    if sp is None:
        sp = etree.SubElement(pp, qn("w:spacing"))
    sp.set(qn("w:line"), str(line))
    sp.set(qn("w:lineRule"), rule)
    if before is not None:
        sp.set(qn("w:before"), str(before))
        sp.set(qn("w:beforeLines"), "0")
    if after is not None:
        sp.set(qn("w:after"), str(after))
        sp.set(qn("w:afterLines"), "0")


def casetable(self, b):
    spec = b.attrs
    rows = bd.casetable_rows(spec)
    head, data = rows[0], rows[1:]
    widths = [int(bd.TEXT_WIDTH * w) for w in [0.2, 0.16, 0.16, 0.16, 0.16, 0.16]]
    font = float(spec.get("font", 10.5))
    # 紧接上一张逐用例表时沿用其页面占用，否则按附录首页估计
    last = self.sect.getprevious()
    used = _ct_state["used"] if (last is not None and last is _ct_state["end"]) else FIRST_USED
    i, first = 0, True
    while i < len(data):
        new_page = (not first) or used + CAP_H + HEAD_H + 5 * ROW_H > BODY_H - SAFETY
        if new_page:
            used = 0
        k = min(len(data) - i, (BODY_H - SAFETY - used - CAP_H - HEAD_H) // ROW_H)
        label = f"表{b.number}" if first else f"续表{b.number}"
        cap = self.caption(label, b.text, before=120, after=60, keep_next=True)
        _fix_line(cap, 300)
        if new_page:
            etree.SubElement(cap.find(qn("w:pPr")), qn("w:pageBreakBefore"))
            bd.normalize_order(cap)
        tbl = self._table_xml([head] + data[i:i + k], widths, ["center"] * 6, font, header=True,
                              repeat_header=False)
        for ri, tr in enumerate(tbl.findall(qn("w:tr"))):
            trp = tr.find(qn("w:trPr"))
            etree.SubElement(trp, qn("w:trHeight"), {qn("w:val"): str(HEAD_H if ri == 0 else ROW_H),
                                                    qn("w:hRule"): "exact"})
            for p in tr.iter(qn("w:p")):
                _fix_line(p, 240, "auto", before=0, after=0)
        self.add(tbl)
        used += CAP_H + HEAD_H + k * ROW_H
        i += k
        first = False
    self.spacer()
    _ct_state["used"] = used + SPACER_H
    _ct_state["end"] = self.sect.getprevious()


bd.Renderer.casetable = casetable


# ---------------------------------------------------------------- 7. 表格整体不跨页
def keep_tables(doc, max_rows=60):
    """表格（含算法框与逐用例表的每一块）除末行外逐行“与下段同页”：放不下时整张表移到下一页，
    不会被页面切成没有底线、顶线的两半。逐用例表的每块按页高切分，本身不超过一页。"""
    for tbl in doc.element.body.iterchildren(qn("w:tbl")):
        rows = tbl.findall(qn("w:tr"))
        if len(rows) > max_rows:
            continue
        for tr in rows[:-1]:
            for p in tr.iter(qn("w:p")):
                pp = p.find(qn("w:pPr"))
                if pp is None:
                    pp = etree.Element(qn("w:pPr"))
                    p.insert(0, pp)
                if pp.find(qn("w:keepNext")) is None:
                    etree.SubElement(pp, qn("w:keepNext"))
                bd.normalize_order(p)


# ---------------------------------------------------------------- 6. 中文引号、破折号、省略号用中文字体
CJK_PUNCT = "“”‘’—…·"


def _east_font(run, styles):
    rf = run.find(qn("w:rPr") + "/" + qn("w:rFonts"))
    if rf is not None and rf.get(qn("w:eastAsia")):
        return rf.get(qn("w:eastAsia"))
    return "宋体"


def fix_cjk_punct(doc):
    """含中文标点的文字段单独成段，西文字体也设为该段的中文字体（Word 与 LibreOffice 都按宋体显示）。"""
    for r in list(doc.element.body.iter(qn("w:r"))):
        t = r.find(qn("w:t"))
        if t is None or not t.text or not any(ch in CJK_PUNCT for ch in t.text):
            continue
        east = _east_font(r, None)
        content = [c for c in r if c.tag != qn("w:rPr")]
        if len(content) != 1:
            # 段内还有制表符、换行等：只加提示，由 Word 按中文字体显示
            rpr = r.find(qn("w:rPr"))
            if rpr is None:
                rpr = etree.Element(qn("w:rPr"))
                r.insert(0, rpr)
            rf = rpr.find(qn("w:rFonts"))
            if rf is None:
                rf = etree.SubElement(rpr, qn("w:rFonts"))
            rf.set(qn("w:hint"), "eastAsia")
            bd.normalize_order(r)
            continue
        pieces = re.findall(r"[%s]+|[^%s]+" % (CJK_PUNCT, CJK_PUNCT), t.text)
        parent = r.getparent()
        idx = parent.index(r)
        for j, piece in enumerate(pieces):
            nr = copy.deepcopy(r)
            for extra in nr.findall(qn("w:t")):
                nr.remove(extra)
            nt = etree.SubElement(nr, qn("w:t"))
            nt.text = piece
            nt.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            if piece[0] in CJK_PUNCT:
                rpr = nr.find(qn("w:rPr"))
                if rpr is None:
                    rpr = etree.Element(qn("w:rPr"))
                    nr.insert(0, rpr)
                rf = rpr.find(qn("w:rFonts"))
                if rf is None:
                    rf = etree.Element(qn("w:rFonts"))
                    rpr.insert(0, rf)
                for a in ("w:ascii", "w:hAnsi", "w:eastAsia"):
                    rf.set(qn(a), east)
                rf.set(qn("w:hint"), "eastAsia")
                bd.normalize_order(nr)
            parent.insert(idx + j, nr)
        parent.remove(r)


# ---------------------------------------------------------------- 公式字形
# pandoc（texmath）把 \varnothing 译成直径符号 ⌀（U+2300），把 \setminus 译成反斜杠；
# 改为标准的空集符号 ∅（U+2205）与集合差符号 ∖（U+2216）。
_MATH_GLYPH = {"\u2300": "\u2205"}


def fix_math_glyphs(doc):
    mt = "{http://schemas.openxmlformats.org/officeDocument/2006/math}t"
    for t in doc.element.body.iter(mt):
        if not t.text:
            continue
        if t.text == "\\":
            t.text = "\u2216"
        else:
            t.text = "".join(_MATH_GLYPH.get(ch, ch) for ch in t.text)


# ---------------------------------------------------------------- 3. 西文字体
def _set_latin(rfonts):
    rfonts.set(qn("w:ascii"), TNR)
    rfonts.set(qn("w:hAnsi"), TNR)
    rfonts.set(qn("w:cs"), TNR)


def force_times(doc):
    """正文、样式与公式中的西文统一为 Times New Roman；代码块（Consolas）不动。"""
    roots = [doc.element, doc.styles.element]
    for sec in doc.sections:
        for hf in (sec.header, sec.footer, sec.first_page_header, sec.first_page_footer):
            try:
                roots.append(hf._element)
            except Exception:
                pass
    for root in roots:
        for rf in root.iter(qn("w:rFonts")):
            if rf.get(qn("w:ascii")) == "Consolas":
                continue
            for a in ("w:asciiTheme", "w:hAnsiTheme", "w:cstheme"):
                if rf.get(qn(a)) is not None:
                    del rf.attrib[qn(a)]
            _set_latin(rf)
    # 没有 rFonts 的普通段落依赖文档默认字体
    defaults = doc.styles.element.find(qn("w:docDefaults"))
    rpr = defaults.find(qn("w:rPrDefault") + "/" + qn("w:rPr"))
    rf = rpr.find(qn("w:rFonts"))
    if rf is None:
        rf = etree.SubElement(rpr, qn("w:rFonts"))
        rpr.insert(0, rf)
    for a in ("w:asciiTheme", "w:hAnsiTheme", "w:cstheme"):
        if rf.get(qn(a)) is not None:
            del rf.attrib[qn(a)]
    _set_latin(rf)
    # 公式：每个 m:r 加 w:rPr/w:rFonts = Times New Roman
    for mr in doc.element.iter("{%s}r" % M_NS):
        wrpr = mr.find(qn("w:rPr"))
        if wrpr is None:
            wrpr = etree.Element(qn("w:rPr"))
            mpr = mr.find("{%s}rPr" % M_NS)
            if mpr is not None:
                mpr.addnext(wrpr)
            else:
                mr.insert(0, wrpr)
        rf = wrpr.find(qn("w:rFonts"))
        if rf is None:
            rf = etree.SubElement(wrpr, qn("w:rFonts"))
            wrpr.insert(0, rf)
        _set_latin(rf)
        rf.set(qn("w:eastAsia"), "宋体")


# ---------------------------------------------------------------- 1. 去掉目录页
def drop_toc(doc):
    """删去目录域及其前面的分页段落；一级标题样式自带段前分页，正文仍从摘要页的下一页开始。"""
    body = doc.element.body
    sdt = next((k for k in body if k.tag == qn("w:sdt")), None)
    if sdt is None:
        return
    prev = sdt.getprevious()
    body.remove(sdt)
    while prev is not None and prev.tag == qn("w:p") and not "".join(
            t.text or "" for t in prev.iter(qn("w:t"))).strip():
        before = prev.getprevious()
        if any(br.get(qn("w:type")) == "page" for br in prev.iter(qn("w:br"))):
            body.remove(prev)
            break
        prev = before


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(V4 / "src"))
    ap.add_argument("--template", default=str(bd.TEMPLATE))
    ap.add_argument("--out", default=str(ROOT / "竞赛论文_v4.docx"))
    args = ap.parse_args()
    facts = json.loads(bd.FACTS.read_text(encoding="utf-8"))
    facts = {k: re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", v) if isinstance(v, str) else v
             for k, v in facts.items()}
    # 带正负号的相对变化另给一个不带符号的版本，供“高 X”“下降 X”这类句式使用
    for k, v in list(facts.items()):
        if isinstance(v, str) and re.match(r"^[+\-−]\d", v):
            facts[k + "_ABS"] = v[1:]
    text = "\n\n".join(p.read_text(encoding="utf-8") for p in sorted(Path(args.src).glob("*.md")))
    text = b3.number_refs(text)
    text = bd.fill_facts(text, facts)
    left = sorted(set(re.findall(r"@@\w+@@", text)))
    if left:
        raise SystemExit("未替换的占位符：" + ", ".join(left))
    meta, blocks = bd.parse_blocks(text)
    labels = bd.number_blocks(blocks)
    bad = sorted(set(re.findall(r"\[@((?:sec|eq|fig|tbl|alg):[\w-]+)\]", text)) - set(labels))
    if bad:
        raise SystemExit("未定义的交叉引用：" + ", ".join(bad))
    abstract = next((b for b in blocks if b.kind == "abstract"), None)
    abs_paras = []
    if abstract:
        for ptxt in "\n".join(abstract.lines).strip().split("\n\n"):
            abs_paras.append(" ".join(x.strip() for x in ptxt.split("\n")))
    import docx
    doc = docx.Document(args.template)
    bd.prepare_template(doc, meta, abs_paras, labels)
    bd.Renderer(doc, labels, facts).render([b for b in blocks if b.kind != "abstract"])
    drop_toc(doc)
    fix_math_glyphs(doc)
    force_times(doc)
    fix_cjk_punct(doc)
    keep_tables(doc)
    set_margins(doc)
    out = Path(args.out)
    doc.save(str(out))
    print("已生成", out)


if __name__ == "__main__":
    main()
