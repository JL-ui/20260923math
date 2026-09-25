"""LaTeX -> MathML -> OMML（Word 原生公式）。

转换链：latex2mathml 把 LaTeX 转成 MathML，再用 Office 自带的 MML2OMML.XSL
转成 OMML。显示公式用 ``m:oMathPara`` 包一层 ``m:eqArr``，在末尾写入
``#(4-1)``，Word 排版时会把 ``#`` 之后的编号右对齐（与在 Word 里手输
``公式#(4-1)`` 的效果相同）。
"""

from __future__ import annotations

import functools
import re
from pathlib import Path

import latex2mathml.converter
from lxml import etree

M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MML_NS = "http://www.w3.org/1998/Math/MathML"
M = f"{{{M_NS}}}"
W = f"{{{W_NS}}}"

_XSL_CANDIDATES = [
    r"C:\Program Files\Microsoft Office\root\Office16\MML2OMML.XSL",
    r"C:\Program Files (x86)\Microsoft Office\root\Office16\MML2OMML.XSL",
    r"C:\Program Files\Microsoft Office\Office16\MML2OMML.XSL",
]


@functools.lru_cache(maxsize=1)
def _xslt():
    for p in _XSL_CANDIDATES:
        if Path(p).exists():
            return etree.XSLT(etree.parse(p))
    raise FileNotFoundError("找不到 MML2OMML.XSL（需要安装 Microsoft Office）")


# 预处理：latex2mathml 不认识或处理不好的写法
_MACROS = [
    (r"\\dfrac", r"\\frac"),
    (r"\\tfrac", r"\\frac"),
    (r"\\bigl|\\bigr|\\Bigl|\\Bigr|\\biggl|\\biggr", r""),
]


def _prep(latex: str) -> str:
    s = latex.strip()
    for a, b in _MACROS:
        s = re.sub(a, b, s)
    # \text{A\_B}：latex2mathml 会原样保留 "\_"，统一成 "_"
    s = re.sub(r"\\(text|mathrm)\{([^{}]*)\}",
               lambda m: "\\" + m.group(1) + "{" + m.group(2).replace(r"\_", "_") + "}", s)
    return s


def _fix_mathml(root):
    """把 \\mathrm{MK} 拆出的相邻正体 mi 合并成一个，避免 Word 把它们当乘积排版。"""
    for parent in root.iter():
        kids = list(parent)
        i = 0
        while i < len(kids) - 1:
            a, b = kids[i], kids[i + 1]
            if (a.tag == b.tag == f"{{{MML_NS}}}mi"
                    and a.get("mathvariant") == "normal" and b.get("mathvariant") == "normal"
                    and a.text and b.text and not len(a) and not len(b)):
                a.text += b.text
                parent.remove(b)
                kids.pop(i + 1)
                continue
            i += 1
    return root


_CJK = re.compile(r"[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef]")


def _set_run_text_font(r):
    """含中文的 m:r：改成正体普通文本（m:nor），字体宋体 + Times New Roman。"""
    for c in list(r):
        if c.tag in (f"{M}rPr", f"{W}rPr"):
            r.remove(c)
    mrpr = etree.Element(f"{M}rPr")
    etree.SubElement(mrpr, f"{M}nor")
    wrpr = etree.Element(f"{W}rPr")
    f = etree.SubElement(wrpr, f"{W}rFonts")
    f.set(f"{W}ascii", "Times New Roman")
    f.set(f"{W}hAnsi", "Times New Roman")
    f.set(f"{W}eastAsia", "宋体")
    f.set(f"{W}hint", "eastAsia")
    r.insert(0, wrpr)
    r.insert(0, mrpr)


def _normalize(om):
    for r in om.iter(f"{M}r"):
        t = r.find(f"{M}t")
        if t is not None and t.text and _CJK.search(t.text):
            _set_run_text_font(r)


_FUNC_RE = re.compile(r"(?<![A-Za-z])(argmax|argmin|max|min|log|ln|exp|lim|sup|inf|det|dim|mod|gcd|rank)(?![A-Za-z])")
_LIMIT_FUNCS = {"max", "min", "argmax", "argmin", "lim", "sup", "inf"}


def _is_plain(r):
    rpr = r.find(f"{M}rPr")
    return rpr is not None and (rpr.find(f"{M}nor") is not None
                                or (rpr.find(f"{M}sty") is not None and rpr.find(f"{M}sty").get(f"{M}val") == "p"))


def _upright_functions(om):
    """MML2OMML 会把 max(a,b) 合成一个斜体 m:r；这里把函数名拆出来改成正体。"""
    import copy
    for r in list(om.iter(f"{M}r")):
        t = r.find(f"{M}t")
        if t is None or not t.text or _is_plain(r) or not _FUNC_RE.search(t.text):
            continue
        pieces = [p for p in _FUNC_RE.split(t.text) if p]
        parent = r.getparent()
        idx = parent.index(r)
        wrpr = r.find(f"{W}rPr")
        news = []
        for p in pieces:
            nr = etree.Element(f"{M}r")
            if _FUNC_RE.fullmatch(p):
                mrpr = etree.SubElement(nr, f"{M}rPr")
                sty = etree.SubElement(mrpr, f"{M}sty")
                sty.set(f"{M}val", "p")
            if wrpr is not None:
                nr.append(copy.deepcopy(wrpr))
            nt = etree.SubElement(nr, f"{M}t")
            nt.text = p
            if p != p.strip():
                nt.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            news.append(nr)
        parent.remove(r)
        for k, nr in enumerate(news):
            parent.insert(idx + k, nr)


def _display_limits(om):
    """显示公式：max/min 的下标放到正下方，求和号的上下限放到上下。"""
    for lim in om.iter(f"{M}limLoc"):
        lim.set(f"{M}val", "undOvr")
    for ss in list(om.iter(f"{M}sSub")):
        e = ss.find(f"{M}e")
        kids = list(e) if e is not None else []
        if (len(kids) == 1 and kids[0].tag == f"{M}r" and kids[0].find(f"{M}t") is not None
                and (kids[0].find(f"{M}t").text or "").strip() in _LIMIT_FUNCS):
            sub_ = ss.find(f"{M}sub")
            ll = etree.Element(f"{M}limLow")
            le = etree.SubElement(ll, f"{M}e")
            le.append(kids[0])
            lm = etree.SubElement(ll, f"{M}lim")
            for c in list(sub_):
                lm.append(c)
            ss.getparent().replace(ss, ll)


def latex_to_omath(latex: str, display: bool = False) -> etree._Element:
    """返回一个 ``m:oMath`` 元素。"""
    mml = latex2mathml.converter.convert(_prep(latex))
    root = etree.fromstring(mml.encode("utf-8"))
    root = _fix_mathml(root)
    res = _xslt()(root).getroot()
    om = res if res.tag == f"{M}oMath" else res.find(f"{M}oMath")
    if om is None:
        raise ValueError(f"OMML 转换失败：{latex}")
    _normalize(om)
    _upright_functions(om)
    if display:
        _display_limits(om)
    return om


def _mrun(text, normal=True):
    r = etree.Element(f"{M}r")
    if normal:
        mrpr = etree.SubElement(r, f"{M}rPr")
        etree.SubElement(mrpr, f"{M}nor")
    wrpr = etree.SubElement(r, f"{W}rPr")
    f = etree.SubElement(wrpr, f"{W}rFonts")
    font = "Times New Roman" if normal else "Cambria Math"
    f.set(f"{W}ascii", font)
    f.set(f"{W}hAnsi", font)
    t = etree.SubElement(r, f"{M}t")
    t.text = text
    return r


def display_equation(latex: str, number: str | None) -> etree._Element:
    """返回 ``m:oMathPara``；有编号时用 eqArr + ``#(编号)``。"""
    om = latex_to_omath(latex, display=True)
    para = etree.Element(f"{M}oMathPara")
    ppr = etree.SubElement(para, f"{M}oMathParaPr")
    jc = etree.SubElement(ppr, f"{M}jc")
    jc.set(f"{M}val", "center")
    if number is None:
        para.append(om)
        return para
    outer = etree.SubElement(para, f"{M}oMath")
    arr = etree.SubElement(outer, f"{M}eqArr")
    apr = etree.SubElement(arr, f"{M}eqArrPr")
    md = etree.SubElement(apr, f"{M}maxDist")
    md.set(f"{M}val", "1")
    e = etree.SubElement(arr, f"{M}e")
    for child in list(om):
        e.append(child)
    e.append(_mrun("#", normal=False))
    e.append(_mrun(f"({number})", normal=True))
    return para


if __name__ == "__main__":
    import sys
    for s in sys.argv[1:]:
        print(etree.tostring(latex_to_omath(s), encoding="unicode")[:600])
