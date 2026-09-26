"""把 paper/v3/*.md 排成 Word（复用 solution/paper_v2/build_docx.py 的版式与解析器）。

    python paper/v3/tools/build_v3.py                      # 生成 竞赛论文_修订版.docx（Windows + Word 时更新目录、导出 PDF）
    python paper/v3/tools/build_v3.py --no-word --out x.docx

与 v2 的差别只有四处，全部在本包装脚本里完成，不改 build_docx.py：
  1. 数字占位符取 paper/v3/data/facts_v3.json（std_caliber.py 生成）；
  2. 附录 A 逐用例表的数据源改为 paper/v3/data/final_standard.csv（标准求解流程口径）；
  3. 参考文献用键名书写（[[ullman]]），按正文首次出现的顺序自动编号；
  4. 没有 Office 自带的 MML2OMML.XSL 时（Linux），公式改用 pandoc 转成 OMML。
"""

from __future__ import annotations

import argparse
import csv
import functools
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
V3 = ROOT / "paper" / "v3"
sys.path.insert(0, str(ROOT / "solution" / "paper_v2"))
import build_docx as bd  # noqa: E402
import omml  # noqa: E402
from lxml import etree  # noqa: E402

# ---------------------------------------------------------------- 4. 公式：无 Office 时走 pandoc
_orig_xslt = omml._xslt


def _xslt_or_none():
    try:
        return _orig_xslt()
    except FileNotFoundError:
        return None


@functools.lru_cache(maxsize=None)
def _pandoc_omath(latex: str) -> bytes:
    exe = shutil.which("pandoc")
    if exe is None:
        import pypandoc
        exe = pypandoc.get_pandoc_path()
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "m.docx"
        subprocess.run([exe, "-f", "markdown", "-o", str(out)],
                       input=("$" + latex.strip() + "$").encode("utf-8"), check=True)
        xml = zipfile.ZipFile(out).read("word/document.xml")
    om = etree.fromstring(xml).find(f".//{omml.M}oMath")
    if om is None:
        raise ValueError(f"OMML 转换失败：{latex}")
    return etree.tostring(om)


def latex_to_omath(latex: str, display: bool = False):
    if _xslt_or_none() is not None:
        return _orig_latex_to_omath(latex, display)
    om = etree.fromstring(_pandoc_omath(omml._prep(latex)))
    omml._normalize(om)
    omml._upright_functions(om)
    if display:
        omml._display_limits(om)
    return om


_orig_latex_to_omath = omml.latex_to_omath
omml.latex_to_omath = latex_to_omath

# ---------------------------------------------------------------- 1/2. 数据源
bd.FACTS = V3 / "data" / "facts_v3.json"
_orig_read_csv = bd._read_csv


def _read_csv(name):
    if name != "final.csv":
        return _orig_read_csv(name)
    with open(V3 / "data" / "final_standard.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k in ("problem", "num_cores", "makespan"):
            r[k] = str(int(float(r[k])))
    return rows


bd._read_csv = _read_csv


# ---------------------------------------------------------------- 3. 参考文献按首次出现编号
def number_refs(text: str) -> str:
    m = re.search(r"::: refs\n(.*?)\n:::", text, re.S)
    if not m:
        return text
    entries = {}
    for line in m.group(1).split("\n"):
        mm = re.match(r"\[([A-Za-z][\w-]*)\]\s*(.+)", line.strip())
        if mm:
            entries[mm.group(1)] = mm.group(2)
    order: list[str] = []
    body = text[:m.start()]

    def rep(mm):
        keys = [k.strip() for k in mm.group(1).split(",")]
        for k in keys:
            if k not in entries:
                raise SystemExit(f"未定义的文献键：{k}")
            if k not in order:
                order.append(k)
        return "[[" + ",".join(str(order.index(k) + 1) for k in keys) + "]]"
    body = re.sub(r"\[\[([A-Za-z][\w-]*(?:\s*,\s*[A-Za-z][\w-]*)*)\]\]", rep, body)
    unused = [k for k in entries if k not in order]
    if unused:
        raise SystemExit("参考文献未被引用：" + ", ".join(unused))
    refs = "\n\n".join(f"[{i + 1}] {entries[k]}" for i, k in enumerate(order))
    # 附录（参考文献之后）只允许引用正文已引用过的文献，编号沿用正文
    n_body = len(order)
    tail = re.sub(r"\[\[([A-Za-z][\w-]*(?:\s*,\s*[A-Za-z][\w-]*)*)\]\]", rep, text[m.end():])
    if len(order) != n_body:
        raise SystemExit("附录引用了正文未引用的文献：" + ", ".join(order[n_body:]))
    return body + "::: refs\n" + refs + "\n:::" + tail



# ---------------------------------------------------------------- 5. 目录：写入静态条目（Linux 下无 Word 更新域时使用）
def _toc_entries(blocks):
    out = []
    for b in blocks:
        if b.kind != "heading" or b.level > 3:
            continue
        num = getattr(b, "number", None) or ""
        if b.level == 1 and num:
            label = f"{num} {b.text}"
        elif num:
            label = f"{num}. {b.text}"
        else:
            label = b.text
        label = re.sub(r"\$([^$]*)\$", lambda m: re.sub(r"[\\{}]|mathrm", "", m.group(1)), label)
        out.append((b.level, label, b.text))
    return out


def write_static_toc(doc, entries, pages=None):
    """把模板目录域里的旧条目换成本文的标题（页码取 LibreOffice 排版的估计值），并让 Word 打开时更新域。"""
    from copy import deepcopy
    from docx.oxml.ns import qn
    body = doc.element.body
    sdt = next(k for k in body if k.tag == qn("w:sdt"))
    content = sdt.find(qn("w:sdtContent"))
    paras = [k for k in content if k.tag == qn("w:p")]
    title, last = paras[0], paras[-1]
    ppr_by = {}
    for q in paras[1:-1]:
        st = q.find(qn("w:pPr") + "/" + qn("w:pStyle"))
        if st is not None and st.get(qn("w:val")) not in ppr_by:
            ppr_by[st.get(qn("w:val"))] = deepcopy(q.find(qn("w:pPr")))
    for q in paras[1:-1]:
        content.remove(q)

    def run(parent, text=None, tab=False, fld=None, instr=None, bold_font=False):
        r = etree.SubElement(parent, qn("w:r"))
        rpr = etree.SubElement(r, qn("w:rPr"))
        if bold_font:
            f = etree.SubElement(rpr, qn("w:rFonts"))
            f.set(qn("w:eastAsia"), "黑体")
        etree.SubElement(rpr, qn("w:noProof"))
        if tab:
            etree.SubElement(r, qn("w:tab"))
        if fld:
            e = etree.SubElement(r, qn("w:fldChar"))
            e.set(qn("w:fldCharType"), fld)
        if instr:
            e = etree.SubElement(r, qn("w:instrText"))
            e.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            e.text = instr
        if text is not None:
            t = etree.SubElement(r, qn("w:t"))
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            t.text = text
        return r

    anchor = last
    for i, (level, label, _) in enumerate(entries):
        q = etree.Element(qn("w:p"))
        ppr = ppr_by.get(f"TOC{level}")
        if ppr is None:
            ppr = ppr_by.get("TOC2")
        q.append(deepcopy(ppr))
        if i == 0:
            run(q, fld="begin")
            run(q, instr='TOC \\o "1-3" \\h \\u ')
            run(q, fld="separate")
        run(q, text=label, bold_font=(level == 1))
        run(q, tab=True)
        run(q, text=str(pages[i]) if pages and pages[i] else "")
        anchor.addprevious(q)
    settings = doc.settings.element
    uf = settings.find(qn("w:updateFields"))
    if uf is None:
        uf = etree.SubElement(settings, qn("w:updateFields"))
    uf.set(qn("w:val"), "true")


def lo_pages(docx_path: Path, entries):
    """用 LibreOffice 排版估计各标题所在页（页脚页码从摘要页起为 1）。"""
    exe = shutil.which("soffice")
    if exe is None:
        return None
    import pymupdf
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "x.docx"
        shutil.copy(docx_path, src)
        subprocess.run([exe, "--headless", "--convert-to", "pdf", "--outdir", d, str(src)],
                       check=True, capture_output=True, timeout=1200)
        pdf = pymupdf.open(str(Path(d) / "x.pdf"))
        texts = [re.sub(r"\s", "", pg.get_text()) for pg in pdf]
    start = next(i for i, t in enumerate(texts) if "关键词" in t) + 1
    while start < len(texts) and ("目录" in texts[start][:10] or "......" in texts[start]):
        start += 1
    out, cur = [], start
    for level, label, raw in entries:
        key = re.sub(r"\s|\$[^$]*\$", "", raw)[:14]
        j = cur
        while j < len(texts) and key not in texts[j]:
            j += 1
        if j >= len(texts):
            out.append(None)
            continue
        cur = j
        out.append(j)       # 物理页从 0 计；封面为第 0 页、摘要页页码为 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(V3))
    ap.add_argument("--out", default=str(ROOT / "竞赛论文_修订版.docx"))
    ap.add_argument("--no-word", action="store_true")
    args = ap.parse_args()
    facts = json.loads(bd.FACTS.read_text(encoding="utf-8"))
    # 正文数字不用千分位分隔符（格式检查表要求）
    facts = {k: re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", v) if isinstance(v, str) else v
             for k, v in facts.items()}
    src = Path(args.src)
    text = "\n\n".join(p.read_text(encoding="utf-8") for p in sorted(src.glob("*.md")))
    text = number_refs(text)
    text = bd.fill_facts(text, facts)
    meta, blocks = bd.parse_blocks(text)
    labels = bd.number_blocks(blocks)
    abstract = next((b for b in blocks if b.kind == "abstract"), None)
    abs_paras = []
    if abstract:
        for ptxt in "\n".join(abstract.lines).strip().split("\n\n"):
            abs_paras.append(" ".join(x.strip() for x in ptxt.split("\n")))
    import docx
    doc = docx.Document(str(bd.TEMPLATE))
    bd.prepare_template(doc, meta, abs_paras, labels)
    bd.Renderer(doc, labels, facts).render([b for b in blocks if b.kind != "abstract"])
    out = Path(args.out)
    entries = _toc_entries(blocks)
    write_static_toc(doc, entries)
    doc.save(str(out))
    if args.no_word:
        pages = lo_pages(out, entries)
        if pages:
            doc = docx.Document(str(out))
            write_static_toc(doc, entries, pages)
            doc.save(str(out))
    print("已生成", out)
    if not args.no_word:
        pdf = out.with_suffix(".pdf")
        bd.word_postprocess(out.resolve(), pdf.resolve())
        print(f"Word 已更新目录并导出 PDF：{pdf}")


if __name__ == "__main__":
    main()
