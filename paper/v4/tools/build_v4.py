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
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "paper" / "v3" / "tools"))
import build_v3 as b3  # noqa: E402  （导入即完成数据源、文献编号与公式转换的替换）

bd = b3.bd
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

# ---------------------------------------------------------------- 4. 逐用例表用五号字
_orig_casetable = bd.Renderer.casetable


def casetable(self, b):
    b.attrs.setdefault("font", "10.5")
    return _orig_casetable(self, b)


bd.Renderer.casetable = casetable


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
    force_times(doc)
    out = Path(args.out)
    doc.save(str(out))
    print("已生成", out)


if __name__ == "__main__":
    main()
