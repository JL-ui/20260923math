# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Sonnet 5（型号 claude-sonnet-5）、Claude Opus 5.5（型号 claude-opus-5-5）
# 开发机构：Anthropic 公司
# 版本发布日期：Claude Sonnet 5 为 2026-06-30，Claude Opus 5.5 为 2026-09-22
"""把 paper/v2/论文_完善版.md 排成 Word（以根目录《草稿.docx》为版式模板）。

    python solution/paper_v2/build_docx.py            # 生成 docx，并用 Word 更新目录、导出 PDF
    python solution/paper_v2/build_docx.py --no-word  # 只生成 docx

版式全部沿用草稿：封面、题目/摘要页、目录域、页边距、页码（从摘要页起），
一级标题“第N章”、二级“N.M.”、三级“N.M.K.”的多级编号均来自草稿的样式与编号定义。
本脚本只做三件事：
  1. 用 results/facts_v2.json 替换正文里的 @@KEY@@（缺键即报错，杜绝手工填数）；
  2. 解析 Markdown 方言（见 parse_blocks 的说明），给图、表、公式、算法按章编号并解析交叉引用；
  3. 生成 WordprocessingML：原生 OMML 公式、三线表、题注、算法框、代码块、定理块。
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import docx
from docx.oxml.ns import qn
from docx.shared import Cm, Emu
from lxml import etree
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import omml  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "草稿.docx"
SRC = ROOT / "paper" / "v2"          # 目录：按文件名顺序拼接其中的 *.md
FACTS = ROOT / "results" / "facts_v2.json"
OUT = ROOT / "竞赛论文_完善版.docx"

W_NS = omml.W_NS
M_NS = omml.M_NS
W = f"{{{W_NS}}}"
TEXT_WIDTH = 11906 - 1588 - 1474          # 版心宽度（twip），= 15.6 cm


# ----------------------------------------------------------------------------
# 1. 数字注入
# ----------------------------------------------------------------------------

def fill_facts(text: str, facts: dict) -> str:
    missing = []

    def rep(m):
        k = m.group(1)
        if k not in facts:
            missing.append(k)
            return m.group(0)
        return str(facts[k])
    out = re.sub(r"@@([A-Za-z0-9_]+)@@", rep, text)
    if missing:
        raise SystemExit("未定义的数字键：" + ", ".join(sorted(set(missing))))
    return out


# ----------------------------------------------------------------------------
# 2. 解析
# ----------------------------------------------------------------------------

@dataclass
class Block:
    kind: str
    text: str = ""
    level: int = 0
    numbered: bool = True
    label: str | None = None
    attrs: dict = field(default_factory=dict)
    lines: list = field(default_factory=list)
    number: str | None = None


ATTR_RE = re.compile(r"\{([^{}]*)\}\s*$")


def split_attrs(s: str):
    """'标题 {#fig:x width=14}' -> ('标题', 'fig:x', {'width': '14'})"""
    m = ATTR_RE.search(s)
    if not m or ("#" not in m.group(1) and "=" not in m.group(1)):
        return s.strip(), None, {}
    body = s[:m.start()].rstrip()
    label, attrs = None, {}
    for tok in re.findall(r'(#[\w:.-]+|[\w-]+="[^"]*"|[\w-]+=[^\s]+)', m.group(1)):
        if tok.startswith("#"):
            label = tok[1:]
        else:
            k, v = tok.split("=", 1)
            attrs[k] = v.strip('"')
    return body, label, attrs


def parse_blocks(text: str) -> tuple[dict, list[Block]]:
    """Markdown 方言：

    %% KEY: value              文档级元数据（TITLE / KEYWORDS）
    # 标题 {#sec:x}            一级标题（第N章）；#* 不编号；## / ### 同理
    $$ ... $$ {#eq:x}          显示公式（可跨行；无 label 则不编号）
    ![题注](path){#fig:x width=15}
    : 题注 {#tbl:x widths=1,2,2 font=9}   紧跟管道表
    ::: kind 参数 {#alg:x}  ... :::        algorithm / theorem / proof / note / abstract /
                                             casetable / center / noindent / quote
    ```lang ... ```            代码块
    \\newpage                   分页
    其余为段落，空行分隔。
    """
    meta: dict = {}
    blocks: list[Block] = []
    lines = text.split("\n")
    i = 0
    para: list[str] = []

    def flush():
        nonlocal para
        if para:
            blocks.append(Block("para", " ".join(s.strip() for s in para)))
            para = []

    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if s.startswith("<!--"):
            flush()
            while "-->" not in lines[i]:
                i += 1
            i += 1
            continue
        if s.startswith("%% "):
            flush()
            k, v = s[3:].split(":", 1)
            meta[k.strip()] = v.strip()
            i += 1
            continue
        if not s:
            flush()
            i += 1
            continue
        m = re.match(r"^(#{1,3})(\*?)\s+(.*)$", s)
        if m:
            flush()
            title, label, attrs = split_attrs(m.group(3))
            blocks.append(Block("heading", title, level=len(m.group(1)),
                                numbered=not m.group(2), label=label, attrs=attrs))
            i += 1
            continue
        if s.startswith("$$"):
            flush()
            buf = s[2:]
            if buf.rstrip().endswith("$$") or re.search(r"\$\$\s*\{[^}]*\}\s*$", buf):
                content = buf
            else:
                content = buf
                i += 1
                while i < len(lines) and "$$" not in lines[i]:
                    content += "\n" + lines[i]
                    i += 1
                content += "\n" + lines[i]
            m2 = re.match(r"^(.*)\$\$\s*(\{[^}]*\})?\s*$", content, re.S)
            latex = m2.group(1).strip()
            _, label, attrs = split_attrs("x " + (m2.group(2) or ""))
            blocks.append(Block("equation", latex, label=label, attrs=attrs))
            i += 1
            continue
        if s.startswith("!["):
            flush()
            m2 = re.match(r"^!\[(.*)\]\(([^)]+)\)\s*(\{[^}]*\})?\s*$", s)
            if not m2:
                raise SystemExit(f"图片语法错误：{s}")
            _, label, attrs = split_attrs("x " + (m2.group(3) or ""))
            blocks.append(Block("figure", m2.group(1), label=label, attrs={**attrs, "path": m2.group(2)}))
            i += 1
            continue
        if s.startswith(": ") and i + 1 < len(lines) and lines[i + 1].strip().startswith("|"):
            flush()
            cap, label, attrs = split_attrs(s[2:])
            rows = []
            i += 1
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(lines[i].strip())
                i += 1
            blocks.append(Block("table", cap, label=label, attrs=attrs, lines=rows))
            continue
        if s.startswith("```"):
            flush()
            lang = s[3:].strip()
            buf = []
            i += 1
            while not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            blocks.append(Block("code", lang, lines=buf))
            i += 1
            continue
        if s.startswith(":::"):
            flush()
            head = s[3:].strip()
            kind, _, rest = head.partition(" ")
            rest, label, attrs = split_attrs(rest)
            buf = []
            i += 1
            depth = 1
            while i < len(lines):
                t = lines[i].strip()
                if t.startswith(":::") and t != ":::":
                    depth += 1
                elif t == ":::":
                    depth -= 1
                    if depth == 0:
                        break
                buf.append(lines[i])
                i += 1
            blocks.append(Block(kind, rest, label=label, attrs=attrs, lines=buf))
            i += 1
            continue
        if s == r"\newpage":
            flush()
            blocks.append(Block("pagebreak"))
            i += 1
            continue
        para.append(line)
        i += 1
    flush()
    return meta, blocks


# ----------------------------------------------------------------------------
# 3. 编号与交叉引用
# ----------------------------------------------------------------------------

PREFIX = {"fig": "图", "tbl": "表", "eq": "式", "alg": "算法"}


def number_blocks(blocks: list[Block]) -> dict:
    labels: dict[str, str] = {}
    ch = sec = sub = 0
    counters = {"fig": 0, "tbl": 0, "eq": 0, "alg": 0}
    appendix = False
    for b in blocks:
        if b.kind == "heading":
            if b.level == 1:
                if b.numbered:
                    ch += 1
                    sec = sub = 0
                    counters = dict.fromkeys(counters, 0)
                    b.number = f"第{ch}章"
                elif b.text.replace(" ", "") == "附录":
                    appendix = True
            elif b.level == 2 and b.numbered:
                sec += 1
                sub = 0
                b.number = f"{ch}.{sec}"
            elif b.level == 3 and b.numbered:
                sub += 1
                b.number = f"{ch}.{sec}.{sub}"
            if b.level == 2 and not b.numbered and appendix:
                # 附录A/附录B：表号前缀用字母
                m = re.match(r"附录\s*([A-Z])", b.text)
                if m:
                    ch = m.group(1)
                    counters = dict.fromkeys(counters, 0)
            if b.label:
                labels[b.label] = b.number or b.text
            continue
        kind = {"figure": "fig", "table": "tbl", "equation": "eq",
                "algorithm": "alg", "casetable": "tbl"}.get(b.kind)
        if kind is None or (kind == "eq" and not b.label):
            continue
        counters[kind] += 1
        b.number = f"{ch}-{counters[kind]}"
        if b.label:
            if b.label in labels:
                raise SystemExit(f"重复的标签：{b.label}")
            labels[b.label] = b.number
    return labels


def resolve_refs(s: str, labels: dict) -> str:
    def rep(m):
        lab = m.group(1)
        if lab not in labels:
            raise SystemExit(f"未定义的引用：{lab}")
        num = labels[lab]
        kind = lab.split(":")[0]
        if kind == "eq":
            return f"式（{num}）"
        if kind == "sec":
            return f"第{num}节" if "." in num else num
        return f"{PREFIX.get(kind, '')}{num}"
    s = re.sub(r"\[@([\w:.-]+)\]", rep, s)
    # 只要编号，不要前缀：[#fig:x] -> 4-1
    s = re.sub(r"\[#([\w:.-]+)\]", lambda m: labels[m.group(1)], s)
    return s


# ----------------------------------------------------------------------------
# 4. XML 构件
# ----------------------------------------------------------------------------

def el(tag, attrs=None, children=()):
    e = etree.Element(qn(tag))
    for k, v in (attrs or {}).items():
        e.set(qn(k), str(v))
    for c in children:
        if c is not None:
            e.append(c)
    return e


def sub(parent, tag, attrs=None):
    e = etree.SubElement(parent, qn(tag))
    for k, v in (attrs or {}).items():
        e.set(qn(k), str(v))
    return e


@dataclass
class RunStyle:
    bold: bool = False
    italic: bool = False
    size: float | None = None          # 磅
    east: str | None = None            # 中文字体
    ascii: str | None = None
    superscript: bool = False
    color: str | None = None


def make_run(text: str, st: RunStyle, is_code=False) -> etree._Element:
    r = el("w:r")
    rpr = sub(r, "w:rPr")
    if is_code:
        sub(rpr, "w:rFonts", {"w:ascii": "Consolas", "w:hAnsi": "Consolas", "w:eastAsia": st.east or "宋体"})
    elif st.east or st.ascii:
        attrs = {}
        if st.ascii:
            attrs.update({"w:ascii": st.ascii, "w:hAnsi": st.ascii})
        if st.east:
            attrs.update({"w:eastAsia": st.east, "w:hint": "eastAsia"})
        sub(rpr, "w:rFonts", attrs)
    if st.bold:
        sub(rpr, "w:b")
        sub(rpr, "w:bCs")
    if st.italic:
        sub(rpr, "w:i")
    if st.color:
        sub(rpr, "w:color", {"w:val": st.color})
    size = st.size
    if is_code and size is None:
        size = 10.5
    if size:
        sub(rpr, "w:sz", {"w:val": int(round(size * 2))})
        sub(rpr, "w:szCs", {"w:val": int(round(size * 2))})
    if st.superscript:
        sub(rpr, "w:vertAlign", {"w:val": "superscript"})
    if len(rpr) == 0:
        r.remove(rpr)
    parts = text.split("\t")
    for k, part in enumerate(parts):
        if k:
            sub(r, "w:tab")
        if part:
            t = sub(r, "w:t")
            t.text = part
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    return r


INLINE_RE = re.compile(
    r"(?P<math>(?<!\\)\$(?!\$)(?P<mbody>.+?)(?<!\\)\$)"
    r"|(?P<bold>\*\*(?P<bbody>.+?)\*\*)"
    r"|(?P<code>`(?P<cbody>[^`]+)`)"
    r"|(?P<cite>\[\[(?P<cref>[0-9,\-–\s]+)\]\])"
    r"|(?P<br><br\s*/?>)"
    r"|(?P<sup>\^\{(?P<sbody>[^}]*)\})"
)


def inline_elements(text: str, st: RunStyle) -> list:
    """把一段带行内标记的文字转成 w:r / m:oMath 元素列表。"""
    out = []
    pos = 0
    for m in INLINE_RE.finditer(text):
        if m.start() > pos:
            out.append(make_run(text[pos:m.start()], st))
        if m.group("math"):
            out.append(omml.latex_to_omath(m.group("mbody")))
        elif m.group("bold"):
            bst = RunStyle(**{**st.__dict__, "bold": True})
            out.extend(inline_elements(m.group("bbody"), bst))
        elif m.group("code"):
            out.append(make_run(m.group("cbody"), RunStyle(**{**st.__dict__, "size": (st.size or 12) - 1.5}),
                                is_code=True))
        elif m.group("cite"):
            ref = m.group("cref").replace(" ", "").replace("-", "–")
            out.append(make_run(f"[{ref}]", RunStyle(**{**st.__dict__, "superscript": True})))
        elif m.group("br"):
            r = el("w:r")
            sub(r, "w:br")
            out.append(r)
        elif m.group("sup"):
            out.append(make_run(m.group("sbody"), RunStyle(**{**st.__dict__, "superscript": True})))
        pos = m.end()
    if pos < len(text):
        out.append(make_run(text[pos:], st))
    return out


def ppr(p, *, jc=None, first_line=None, first_chars=None, left=None, hanging=None,
        before=None, after=None, line=None, line_rule="auto", keep_next=False,
        keep_lines=False, snap=True, style=None, numid0=False, page_break_before=False,
        widow=True, outline=None, tabs=None):
    pp = p.find(qn("w:pPr"))
    if pp is None:
        pp = el("w:pPr")
        p.insert(0, pp)
    if style:
        sub(pp, "w:pStyle", {"w:val": style})
    if keep_next:
        sub(pp, "w:keepNext")
    if keep_lines:
        sub(pp, "w:keepLines")
    if page_break_before:
        sub(pp, "w:pageBreakBefore")
    if numid0:
        num = sub(pp, "w:numPr")
        sub(num, "w:ilvl", {"w:val": 0})
        sub(num, "w:numId", {"w:val": 0})
    if not snap:
        sub(pp, "w:snapToGrid", {"w:val": 0})
    if tabs:
        tb = sub(pp, "w:tabs")
        for kind, pos in tabs:
            sub(tb, "w:tab", {"w:val": kind, "w:pos": pos})
    sp = {}
    if before is not None:
        sp["w:before"] = before
        sp["w:beforeLines"] = 0
    if after is not None:
        sp["w:after"] = after
        sp["w:afterLines"] = 0
    if line is not None:
        sp["w:line"] = line
        sp["w:lineRule"] = line_rule
    if sp:
        sub(pp, "w:spacing", sp)
    # 正文样式带 firstLineChars=200：取消首行缩进必须显式写 firstLineChars=0；
    # 悬挂缩进写 left + hanging + firstLineChars=0（实测 leftChars=0 会让 left 失效）
    ind = {}
    if first_line is not None:
        ind["w:firstLine"] = first_line
        ind["w:firstLineChars"] = first_chars if first_chars is not None else 0
    if left is not None:
        ind["w:left"] = left
    if hanging is not None:
        ind.pop("w:firstLine", None)
        ind["w:hanging"] = hanging
        ind["w:firstLineChars"] = 0
    if ind:
        sub(pp, "w:ind", ind)
    if jc:
        sub(pp, "w:jc", {"w:val": jc})
    if outline is not None:
        sub(pp, "w:outlineLvl", {"w:val": outline})
    return pp


# OOXML 对若干容器的子元素顺序有严格要求，顺序错了 Word 会弹“修复”对话框
_ORDER = {
    "pPr": ["pStyle", "keepNext", "keepLines", "pageBreakBefore", "framePr", "widowControl", "numPr",
            "suppressLineNumbers", "pBdr", "shd", "tabs", "suppressAutoHyphens", "kinsoku", "wordWrap",
            "overflowPunct", "topLinePunct", "autoSpaceDE", "autoSpaceDN", "bidi", "adjustRightInd",
            "snapToGrid", "spacing", "ind", "contextualSpacing", "mirrorIndents", "suppressOverlap", "jc",
            "textDirection", "textAlignment", "textboxTightWrap", "outlineLvl", "divId", "cnfStyle", "rPr",
            "sectPr", "pPrChange"],
    "rPr": ["rStyle", "rFonts", "b", "bCs", "i", "iCs", "caps", "smallCaps", "strike", "dstrike", "outline",
            "shadow", "emboss", "imprint", "noProof", "snapToGrid", "vanish", "webHidden", "color", "spacing",
            "w", "kern", "position", "sz", "szCs", "highlight", "u", "effect", "bdr", "shd", "fitText",
            "vertAlign", "rtl", "cs", "em", "lang", "eastAsianLayout", "specVanish", "oMath"],
    "tcBorders": ["top", "start", "left", "bottom", "end", "right", "insideH", "insideV", "tl2br", "tr2bl"],
    "tblBorders": ["top", "start", "left", "bottom", "end", "right", "insideH", "insideV"],
    "tcPr": ["cnfStyle", "tcW", "gridSpan", "hMerge", "vMerge", "tcBorders", "shd", "noWrap", "tcMar",
             "textDirection", "tcFitText", "vAlign", "hideMark"],
    "tblPr": ["tblStyle", "tblpPr", "tblOverlap", "bidiVisual", "tblStyleRowBandSize", "tblStyleColBandSize",
              "tblW", "jc", "tblCellSpacing", "tblInd", "tblBorders", "shd", "tblLayout", "tblCellMar",
              "tblLook"],
    "tblCellMar": ["top", "start", "left", "bottom", "end", "right"],
}


def normalize_order(root):
    for e in root.iter(qn("w:pPr"), qn("w:rPr"), qn("w:tcBorders"), qn("w:tblBorders"), qn("w:tcPr"),
                       qn("w:tblPr"), qn("w:tblCellMar")):
        name = e.tag.split("}")[1]
        order = _ORDER[name]
        kids = list(e)
        # 同名元素保留最后一个
        seen = {}
        for k in kids:
            if k.tag.startswith(W):
                seen[k.tag] = k
        keep = [k for k in kids if not k.tag.startswith(W) or seen[k.tag] is k]

        def key(k):
            local = k.tag.split("}")[1]
            return order.index(local) if (k.tag.startswith(W) and local in order) else len(order)
        keep.sort(key=key)
        for k in kids:
            e.remove(k)
        for k in keep:
            e.append(k)


# ----------------------------------------------------------------------------
# 5. 渲染
# ----------------------------------------------------------------------------

class Renderer:
    def __init__(self, doc, labels, facts):
        self.doc = doc
        self.body = doc.element.body
        self.sect = self.body.find(qn("w:sectPr"))
        self.labels = labels
        self.facts = facts
        self.fig_count = 0

    def add(self, e):
        normalize_order(e)
        self.sect.addprevious(e)
        return e

    def txt(self, s):
        return resolve_refs(s, self.labels)

    # ---- 段落 ----
    def paragraph(self, text, st=RunStyle(), **fmt):
        p = el("w:p")
        if fmt:
            ppr(p, **fmt)
        for x in inline_elements(self.txt(text), st):
            p.append(x)
        return self.add(p)

    def heading(self, b: Block):
        """标题段落的直接格式与草稿逐项一致：一级黑体不加粗，二、三级宋体加粗、编号悬挂。"""
        p = el("w:p")
        style = {1: "1", 2: "2", 3: "3"}[b.level]
        pp = ppr(p, style=style, numid0=not b.numbered)
        sub(pp, "w:spacing", {"w:before": 163, "w:after": 163})
        if not b.numbered:
            sub(pp, "w:ind", {"w:left": 0, "w:firstLine": 0, "w:firstLineChars": 0})
        elif b.level in (2, 3):
            sub(pp, "w:ind", {"w:left": 482, "w:hangingChars": 200, "w:hanging": 482})
        for x in inline_elements(self.txt(b.text), RunStyle()):
            if x.tag == qn("w:r"):
                rpr = x.find(qn("w:rPr"))
                if rpr is None:
                    rpr = el("w:rPr")
                    x.insert(0, rpr)
                if b.level == 1:
                    sub(rpr, "w:rFonts", {"w:ascii": "黑体", "w:eastAsia": "黑体", "w:hAnsi": "黑体"})
                    sub(rpr, "w:b", {"w:val": 0})
                    sub(rpr, "w:bCs")
                    sub(rpr, "w:szCs", {"w:val": 28})
                else:
                    sub(rpr, "w:rFonts", {"w:ascii": "Times New Roman", "w:hAnsi": "Times New Roman"})
            p.append(x)
        self.add(p)

    def equation(self, b: Block):
        p = el("w:p")
        ppr(p, first_line=0, jc="center", before=60, after=60, snap=False, keep_lines=True)
        p.append(omml.display_equation(b.text, b.number))
        self.add(p)

    # ---- 图 ----
    def figure(self, b: Block):
        path = ROOT / b.attrs["path"]
        if not path.exists():
            raise SystemExit(f"找不到图片：{path}")
        width_cm = float(b.attrs.get("width", 15))
        with Image.open(path) as im:
            w_px, h_px = im.size
        height_cm = width_cm * h_px / w_px
        max_h = float(b.attrs.get("maxh", 20))
        if height_cm > max_h:
            width_cm *= max_h / height_cm
            height_cm = max_h
        p = el("w:p")
        ppr(p, first_line=0, jc="center", before=120, after=0, keep_next=True, snap=False)
        self.fig_count += 1
        inline = self.doc.part.new_pic_inline(str(path), Cm(width_cm), Cm(height_cm))
        r = sub(p, "w:r")
        drawing = sub(r, "w:drawing")
        drawing.append(inline)
        self.add(p)
        self.caption(f"图{b.number}", b.text, after=160)

    def caption(self, label, text, before=0, after=120, keep_next=False):
        p = el("w:p")
        ppr(p, first_line=0, jc="center", before=before, after=after, keep_next=keep_next,
            snap=False, line=260)
        st = RunStyle(size=10.5)
        p.append(make_run(label + " ", RunStyle(size=10.5, east="黑体")))
        for x in inline_elements(self.txt(text), st):
            p.append(x)
        return self.add(p)

    # ---- 表 ----
    @staticmethod
    def _split_row(row: str):
        row = row.strip()
        if row.startswith("|"):
            row = row[1:]
        if row.endswith("|") and not row.endswith("\\|"):
            row = row[:-1]
        cells, buf, in_math = [], "", False
        k = 0
        while k < len(row):
            ch = row[k]
            if ch == "\\" and k + 1 < len(row) and row[k + 1] == "|":
                buf += "|"
                k += 2
                continue
            if ch == "$":
                in_math = not in_math
            if ch == "|" and not in_math:
                cells.append(buf.strip())
                buf = ""
            else:
                buf += ch
            k += 1
        cells.append(buf.strip())
        return cells

    @staticmethod
    def _text_len(s: str) -> float:
        s = re.sub(r"\$([^$]*)\$", lambda m: "x" * max(1, len(re.sub(r"\\[a-zA-Z]+|[{}_^]", "", m.group(1))) // 1), s)
        s = re.sub(r"<br\s*/?>", "\n", s)
        best = 0.0
        for part in s.split("\n"):
            n = 0.0
            for ch in part:
                n += 2.0 if ord(ch) > 0x2E80 else 1.0
            best = max(best, n)
        return best

    def table(self, b: Block):
        rows = [self._split_row(r) for r in b.lines]
        align_row = None
        if len(rows) > 1 and all(re.fullmatch(r":?-{2,}:?", c.replace(" ", "")) for c in rows[1]):
            align_row = rows[1]
            rows = [rows[0]] + rows[2:]
        ncol = len(rows[0])
        for r in rows:
            if len(r) != ncol:
                raise SystemExit(f"表“{b.text}”列数不一致：{r}")
        aligns = []
        for k in range(ncol):
            a = align_row[k].replace(" ", "") if align_row else ":-:"
            aligns.append("left" if a.startswith(":") and not a.endswith(":") else
                          "right" if a.endswith(":") and not a.startswith(":") else
                          "left" if not a.startswith(":") else "center")
        font = float(b.attrs.get("font", 10.5))
        if "widths" in b.attrs:
            ws = [float(x) for x in b.attrs["widths"].split(",")]
        else:
            ws = [max(self._text_len(r[k]) for r in rows) + 2 for k in range(ncol)]
        total_w = float(b.attrs.get("width", 100)) / 100 * TEXT_WIDTH
        natural = sum(ws) * font * 10  # 约 1/20 pt 每半个汉字宽度
        if "widths" not in b.attrs and natural < total_w:
            total_w = max(natural, 0.6 * TEXT_WIDTH)
        widths = [int(total_w * w / sum(ws)) for w in ws]
        cap = self.caption(f"表{b.number}", b.text, before=120, after=60, keep_next=True)
        tbl = self._table_xml(rows, widths, aligns, font, header=True,
                              repeat_header=b.attrs.get("repeat", "1") == "1",
                              bold_first_col=b.attrs.get("boldcol") == "1")
        self.add(tbl)
        if "note" in b.attrs:
            self.note(b.attrs["note"])
        else:
            self.spacer()
        return cap

    def _table_xml(self, rows, widths, aligns, font, header=True, repeat_header=True,
                   bold_first_col=False, borders="three"):
        tbl = el("w:tbl")
        tp = sub(tbl, "w:tblPr")
        sub(tp, "w:tblW", {"w:w": sum(widths), "w:type": "dxa"})
        sub(tp, "w:jc", {"w:val": "center"})
        bd = sub(tp, "w:tblBorders")
        for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
            sub(bd, f"w:{side}", {"w:val": "nil"})
        sub(tp, "w:tblLayout", {"w:type": "fixed"})
        mar = sub(tp, "w:tblCellMar")
        sub(mar, "w:left", {"w:w": 70, "w:type": "dxa"})
        sub(mar, "w:right", {"w:w": 70, "w:type": "dxa"})
        grid = sub(tbl, "w:tblGrid")
        for w in widths:
            sub(grid, "w:gridCol", {"w:w": w})
        n = len(rows)
        for ri, row in enumerate(rows):
            tr = sub(tbl, "w:tr")
            trp = sub(tr, "w:trPr")
            sub(trp, "w:cantSplit")
            if ri == 0 and header and repeat_header:
                sub(trp, "w:tblHeader")
            for ci, cell in enumerate(row):
                tc = sub(tr, "w:tc")
                tcp = sub(tc, "w:tcPr")
                sub(tcp, "w:tcW", {"w:w": widths[ci], "w:type": "dxa"})
                b = sub(tcp, "w:tcBorders")
                top = "single" if ri == 0 else "nil"
                if ri == 0:
                    sub(b, "w:top", {"w:val": "single", "w:sz": 12, "w:space": 0, "w:color": "000000"})
                if ri == 0 and header:
                    sub(b, "w:bottom", {"w:val": "single", "w:sz": 6, "w:space": 0, "w:color": "000000"})
                if ri == n - 1:
                    sub(b, "w:bottom", {"w:val": "single", "w:sz": 12, "w:space": 0, "w:color": "000000"})
                sub(tcp, "w:vAlign", {"w:val": "center"})
                # 单元格内容：\\ 或 <br> 换行成多段
                keep = n <= 25 and ri < n - 1       # 中小型表整体不跨页
                for k, piece in enumerate(re.split(r"\s*\\\\\s*", cell) if cell else [""]):
                    p = sub(tc, "w:p")
                    ppr(p, first_line=0, jc=aligns[ci], before=20 if k == 0 else 0, after=20,
                        snap=False, line=250, keep_next=keep)
                    st = RunStyle(size=font, bold=(ri == 0 and header) or (bold_first_col and ci == 0),
                                  east="黑体" if (ri == 0 and header) else None)
                    for x in inline_elements(self.txt(piece), st):
                        p.append(x)
        return tbl

    def spacer(self, after=60):
        p = el("w:p")
        ppr(p, first_line=0, before=0, after=after, snap=False, line=120, line_rule="exact")
        self.add(p)

    def note(self, text):
        p = el("w:p")
        ppr(p, first_line=0, jc="left", before=40, after=120, snap=False, line=260)
        for x in inline_elements(self.txt(text), RunStyle(size=9)):
            p.append(x)
        self.add(p)

    # ---- 算法框 ----
    def algorithm(self, b: Block):
        tbl = el("w:tbl")
        tp = sub(tbl, "w:tblPr")
        sub(tp, "w:tblW", {"w:w": TEXT_WIDTH, "w:type": "dxa"})
        sub(tp, "w:jc", {"w:val": "center"})
        sub(tp, "w:tblLayout", {"w:type": "fixed"})
        mar = sub(tp, "w:tblCellMar")
        sub(mar, "w:left", {"w:w": 110, "w:type": "dxa"})
        sub(mar, "w:right", {"w:w": 110, "w:type": "dxa"})
        grid = sub(tbl, "w:tblGrid")
        sub(grid, "w:gridCol", {"w:w": TEXT_WIDTH})
        # 标题行
        tr = sub(tbl, "w:tr")
        sub(sub(tr, "w:trPr"), "w:cantSplit")
        tc = sub(tr, "w:tc")
        tcp = sub(tc, "w:tcPr")
        sub(tcp, "w:tcW", {"w:w": TEXT_WIDTH, "w:type": "dxa"})
        bd = sub(tcp, "w:tcBorders")
        sub(bd, "w:top", {"w:val": "single", "w:sz": 12, "w:space": 0, "w:color": "000000"})
        sub(bd, "w:bottom", {"w:val": "single", "w:sz": 6, "w:space": 0, "w:color": "000000"})
        sub(bd, "w:left", {"w:val": "nil"})
        sub(bd, "w:right", {"w:val": "nil"})
        p = sub(tc, "w:p")
        ppr(p, first_line=0, jc="left", before=30, after=30, snap=False, keep_next=True)
        p.append(make_run(f"算法{b.number} ", RunStyle(size=10.5, bold=True, east="黑体")))
        for x in inline_elements(self.txt(b.text), RunStyle(size=10.5, bold=True, east="黑体")):
            p.append(x)
        # 步骤行
        tr = sub(tbl, "w:tr")
        tc = sub(tr, "w:tc")
        tcp = sub(tc, "w:tcPr")
        sub(tcp, "w:tcW", {"w:w": TEXT_WIDTH, "w:type": "dxa"})
        bd = sub(tcp, "w:tcBorders")
        sub(bd, "w:top", {"w:val": "nil"})
        sub(bd, "w:bottom", {"w:val": "single", "w:sz": 12, "w:space": 0, "w:color": "000000"})
        sub(bd, "w:left", {"w:val": "nil"})
        sub(bd, "w:right", {"w:val": "nil"})
        body_lines = [ln for ln in b.lines if ln.strip()]
        for k, ln in enumerate(body_lines):
            raw = ln.strip(" \t")
            indent = 0
            m = re.match(r"^(\d+[.:])[ \t]*(.*)$", raw)
            text = raw
            lead = ""
            if m:
                lead, text = m.group(1), m.group(2)
            while text.startswith("　"):
                indent += 1
                text = text[1:]
            p = sub(tc, "w:p")
            left = 400 + indent * 420
            if lead:
                ppr(p, left=left, hanging=400, jc="left", before=10,
                    after=10 if k < len(body_lines) - 1 else 40, snap=False, line=260,
                    tabs=[("left", left)])
            else:
                ppr(p, first_line=0, left=0, jc="left", before=10,
                    after=10 if k < len(body_lines) - 1 else 40, snap=False, line=260)
            st = RunStyle(size=10.5)
            if lead:
                p.append(make_run(lead + "\t", RunStyle(size=10.5)))
            for x in inline_elements(self.txt(text), st):
                p.append(x)
        self.add(tbl)
        self.spacer(80)

    # ---- 定理 / 证明 ----
    def theorem(self, b: Block, proof=False):
        paras = "\n".join(b.lines).strip().split("\n\n")
        for k, ptxt in enumerate(paras):
            ptxt = " ".join(x.strip() for x in ptxt.split("\n"))
            p = el("w:p")
            last = proof and k == len(paras) - 1
            ppr(p, before=40 if k == 0 else 0, after=40, keep_lines=True,
                tabs=[("right", TEXT_WIDTH)] if last else None)
            body_st = RunStyle(east="楷体") if not proof else RunStyle()
            if k == 0:
                label = b.text or ("证明" if proof else "")
                p.append(make_run(label + " ", RunStyle(bold=True, east="黑体")))
            for x in inline_elements(self.txt(ptxt), body_st):
                p.append(x)
            if last:
                p.append(make_run("\t□", RunStyle()))
            self.add(p)

    # ---- 代码 ----
    def code(self, b: Block):
        tbl = el("w:tbl")
        tp = sub(tbl, "w:tblPr")
        sub(tp, "w:tblW", {"w:w": TEXT_WIDTH, "w:type": "dxa"})
        sub(tp, "w:jc", {"w:val": "center"})
        sub(tp, "w:tblLayout", {"w:type": "fixed"})
        mar = sub(tp, "w:tblCellMar")
        sub(mar, "w:left", {"w:w": 140, "w:type": "dxa"})
        sub(mar, "w:right", {"w:w": 100, "w:type": "dxa"})
        grid = sub(tbl, "w:tblGrid")
        sub(grid, "w:gridCol", {"w:w": TEXT_WIDTH})
        tr = sub(tbl, "w:tr")
        tc = sub(tr, "w:tc")
        tcp = sub(tc, "w:tcPr")
        sub(tcp, "w:tcW", {"w:w": TEXT_WIDTH, "w:type": "dxa"})
        bd = sub(tcp, "w:tcBorders")
        for side in ("top", "bottom", "right"):
            sub(bd, f"w:{side}", {"w:val": "single", "w:sz": 4, "w:space": 0, "w:color": "BFC7D5"})
        sub(bd, "w:left", {"w:val": "single", "w:sz": 18, "w:space": 0, "w:color": "3B6FB6"})
        sub(tcp, "w:shd", {"w:val": "clear", "w:color": "auto", "w:fill": "F4F6FA"})
        size = float(b.attrs.get("font", 8.5)) if b.attrs else 8.5
        for k, ln in enumerate(b.lines):
            p = sub(tc, "w:p")
            ppr(p, first_line=0, jc="left", before=30 if k == 0 else 0,
                after=30 if k == len(b.lines) - 1 else 0, snap=False, line=230)
            is_comment = ln.strip().startswith("#")
            st = RunStyle(size=size, color="5A6B7D" if is_comment else None, east="宋体")
            p.append(make_run(ln.replace("\t", "    ") or " ", st, is_code=True))
        self.add(tbl)
        self.spacer(80)

    # ---- 逐用例表 ----
    def casetable(self, b: Block):
        spec = b.attrs
        rows = casetable_rows(spec)
        widths = [int(TEXT_WIDTH * w) for w in [0.2, 0.16, 0.16, 0.16, 0.16, 0.16]]
        self.caption(f"表{b.number}", b.text, before=120, after=60, keep_next=True)
        tbl = self._table_xml(rows, widths, ["center"] * 6, float(spec.get("font", 9)), header=True,
                              repeat_header=True)
        self.add(tbl)
        self.spacer()

    def render(self, blocks: list[Block]):
        for b in blocks:
            k = b.kind
            if k == "heading":
                self.heading(b)
            elif k == "para":
                self.paragraph(b.text)
            elif k == "equation":
                self.equation(b)
            elif k == "figure":
                self.figure(b)
            elif k == "table":
                self.table(b)
            elif k == "algorithm":
                self.algorithm(b)
            elif k in ("theorem", "thm"):
                self.theorem(b)
            elif k == "proof":
                self.theorem(b, proof=True)
            elif k == "code":
                self.code(b)
            elif k == "casetable":
                self.casetable(b)
            elif k == "note":
                self.note(" ".join(x.strip() for x in b.lines))
            elif k == "noindent":
                for ptxt in "\n".join(b.lines).strip().split("\n\n"):
                    self.paragraph(" ".join(x.strip() for x in ptxt.split("\n")), first_line=0)
            elif k == "refs":
                # 参考文献：编号悬挂，续行与正文对齐
                for ptxt in "\n".join(b.lines).strip().split("\n\n"):
                    self.paragraph(" ".join(x.strip() for x in ptxt.split("\n")), left=560, hanging=560,
                                   before=0, after=30, jc="both")
            elif k == "center":
                for ptxt in "\n".join(b.lines).strip().split("\n\n"):
                    self.paragraph(" ".join(x.strip() for x in ptxt.split("\n")), first_line=0, jc="center")
            elif k == "pagebreak":
                p = el("w:p")
                r = sub(p, "w:r")
                sub(r, "w:br", {"w:type": "page"})
                self.add(p)
            elif k == "abstract":
                continue
            else:
                raise SystemExit(f"未知块类型：{k}")


# ----------------------------------------------------------------------------
# 6. 逐用例表（附录）
# ----------------------------------------------------------------------------

def _read_csv(name):
    with open(ROOT / "results" / name, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def casetable_rows(spec: dict):
    """spec: problem=1|2|3, metric=makespan|added|hit|gain"""
    prob = int(spec["problem"])
    metric = spec["metric"]
    final = _read_csv("final.csv")
    n1 = _read_csv("n1.csv")
    val = {}
    for r in final:
        val[(r["case"], int(r["problem"]), int(r["num_cores"]))] = r
    for r in n1:
        val[(r["case"], int(r["problem"]), 1)] = r
    cases = sorted({r["case"] for r in final})
    rows = [["用例", "N=1", "N=2", "N=3", "N=4", "N=5"]]
    for c in cases:
        row = [c.replace("case_", "case_")]
        for n in range(1, 6):
            if metric == "gain":
                a = val[(c, 2, n)]
                bb = val[(c, 3, n)]
                row.append(f"{int(a['makespan']) / int(bb['makespan']):.3f}")
                continue
            r = val[(c, prob, n)]
            if metric == "makespan":
                row.append(f"{int(r['makespan'])}")
            elif metric == "added":
                row.append(f"{int(float(r['added_copy_bytes']))}")
            elif metric == "hit":
                h = r.get("cache_hit_rate") or "0"
                row.append(f"{100 * float(h):.1f}")
        rows.append(row)
    return rows


# ----------------------------------------------------------------------------
# 7. 模板处理：封面/摘要/目录保留，正文替换
# ----------------------------------------------------------------------------

def prepare_template(doc, meta, abstract_blocks, labels):
    body = doc.element.body
    kids = list(body)
    sdt_idx = next(i for i, k in enumerate(kids) if k.tag == qn("w:sdt"))
    for k in kids[sdt_idx + 1:]:
        if k.tag != qn("w:sectPr"):
            body.remove(k)
    # 找到题目、摘要、关键词段落
    paras = [k for k in kids[:sdt_idx] if k.tag == qn("w:p")]

    def text_of(p):
        return "".join(t.text or "" for t in p.iter(qn("w:t")))
    title_p = next(p for p in paras if text_of(p).startswith("题"))
    abs_head = next(p for p in paras if text_of(p).replace(" ", "").startswith("摘要"))
    abs_p = next(p for p in paras if text_of(p).startswith("摘要应"))
    kw_p = next(p for p in paras if text_of(p).startswith("关键词"))
    # 题目：保留“题 目：”，替换下划线内容
    runs = title_p.findall(qn("w:r"))
    for r in runs[1:]:
        title_p.remove(r)
    t = el("w:r")
    rpr = sub(t, "w:rPr")
    sub(rpr, "w:rFonts", {"w:ascii": "黑体", "w:eastAsia": "黑体", "w:hAnsi": "黑体", "w:hint": "eastAsia"})
    sub(rpr, "w:sz", {"w:val": 32})
    sub(rpr, "w:szCs", {"w:val": 32})
    sub(rpr, "w:u", {"w:val": "single", "w:color": "000000"})
    tt = sub(t, "w:t")
    tt.text = "  " + meta["TITLE"] + "  "
    tt.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    title_p.append(t)
    # 摘要：删除占位段与其后的空段，插入摘要段落
    nxt = abs_p.getnext()
    while nxt is not None and nxt is not kw_p:
        after = nxt.getnext()
        if text_of(nxt).strip() == "":
            body.remove(nxt)
        nxt = after
    anchor = abs_p
    for ptxt in abstract_blocks:
        p = el("w:p")
        ppr(p, first_line=480, first_chars=200)
        for x in inline_elements(resolve_refs(ptxt, labels), RunStyle()):
            p.append(x)
        anchor.addnext(p)
        anchor = p
    body.remove(abs_p)
    # 关键词段前留一点空
    kpp = kw_p.find(qn("w:pPr"))
    ind = kpp.find(qn("w:ind"))
    if ind is not None:
        kpp.remove(ind)
    sub(kpp, "w:spacing", {"w:before": 240, "w:beforeLines": 0})
    sub(kpp, "w:ind", {"w:firstLine": 0, "w:firstLineChars": 0})
    kruns = kw_p.findall(qn("w:r"))
    for r in kruns[1:]:
        kw_p.remove(r)
    kr = make_run(meta["KEYWORDS"], RunStyle(east="宋体"))
    kw_p.append(kr)
    for p in (title_p, kw_p, abs_head):
        normalize_order(p)
    return kids[sdt_idx]


def _automation_word_pids():
    import subprocess
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process -Filter \"Name='WINWORD.EXE'\" | "
         "Where-Object { $_.CommandLine -like '*Automation*' } | ForEach-Object { $_.ProcessId }"],
        capture_output=True, text=True)
    return {int(x) for x in out.stdout.split() if x.strip().isdigit()}


def word_postprocess(docx_path: Path, pdf_path: Path | None, timeout=900):
    """在子进程里调 Word：更新目录与域、导出 PDF。超时只结束本次自动化启动的 Word。"""
    import subprocess
    # 残留的自动化 Word（/Automation -Embedding）会锁住文件，先清理；用户自己打开的 Word 不受影响
    for pid in _automation_word_pids():
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
    before = _automation_word_pids()
    cmd = [sys.executable, "-u", str(Path(__file__).resolve()), "--word-only", str(docx_path)]
    if pdf_path:
        cmd.append(str(pdf_path))
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                             env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
        print(res.stdout.strip())
        if res.returncode != 0:
            print(res.stderr[-2000:])
            raise SystemExit(f"Word 后处理失败（返回码 {res.returncode}）")
    except subprocess.TimeoutExpired:
        for pid in _automation_word_pids() - before:
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
        raise SystemExit("Word 后处理超时（可能弹出了修复对话框，说明生成的 XML 有问题）")


def _word_only(docx_path, pdf_path=None):
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        import os
        word.ScreenUpdating = False
        try:
            word.Options.UpdateLinksAtOpen = False
            word.Options.CheckGrammarAsYouType = False
            word.Options.CheckSpellingAsYouType = False
        except Exception:
            pass
        print("word started", flush=True)
        doc = word.Documents.Open(os.path.abspath(docx_path), False, False, False)
        print("opened", flush=True)
        doc.Repaginate()
        for k in range(1, doc.TablesOfContents.Count + 1):
            doc.TablesOfContents(k).Update()
        print("toc updated", flush=True)
        doc.Repaginate()
        for k in range(1, doc.TablesOfContents.Count + 1):
            doc.TablesOfContents(k).UpdatePageNumbers()
        pages = doc.ComputeStatistics(2)
        doc.SaveAs2(os.path.abspath(docx_path), 16)
        print("saved", flush=True)
        if pdf_path:
            doc.ExportAsFixedFormat(os.path.abspath(pdf_path), 17)
        doc.Close(False)
        print(f"PAGES={pages}", flush=True)
    finally:
        word.Quit()


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--word-only":
        _word_only(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
        return
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(SRC))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--no-word", action="store_true")
    args = ap.parse_args()
    facts = json.loads(FACTS.read_text(encoding="utf-8")) if FACTS.exists() else {}
    src = Path(args.src)
    if src.is_dir():
        text = "\n\n".join(p.read_text(encoding="utf-8") for p in sorted(src.glob("*.md")))
    else:
        text = src.read_text(encoding="utf-8")
    text = fill_facts(text, {k: v for k, v in facts.items()})
    meta, blocks = parse_blocks(text)
    labels = number_blocks(blocks)
    abstract = next((b for b in blocks if b.kind == "abstract"), None)
    abs_paras = []
    if abstract:
        for ptxt in "\n".join(abstract.lines).strip().split("\n\n"):
            abs_paras.append(" ".join(x.strip() for x in ptxt.split("\n")))
    doc = docx.Document(str(TEMPLATE))
    prepare_template(doc, meta, abs_paras, labels)
    Renderer(doc, labels, facts).render([b for b in blocks if b.kind != "abstract"])
    out = Path(args.out)
    doc.save(str(out))
    print("已生成", out)
    if not args.no_word:
        pdf = out.with_suffix(".pdf")
        word_postprocess(out.resolve(), pdf.resolve())
        print(f"Word 已更新目录并导出 PDF：{pdf}")


if __name__ == "__main__":
    main()
