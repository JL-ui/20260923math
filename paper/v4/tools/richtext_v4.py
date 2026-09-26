"""中西文与公式混排的文字排版（示意图与机理图共用）。

matplotlib 的 mathtext 不能与中文混排。本模块把一段文字拆成“原子”：每个汉字或中文标点、
每个西文词、每个 $...$ 公式各为一个原子，按实测宽度分行，再把相邻的文字原子合并绘制。
这样变量可以用斜体（$F$、$\\beta W/N$），下标用正体（$W_{\\mathrm{same}}$），与正文公式写法一致。

    rtext(ax, x, y, text, width, ...)       坐标单位为厘米的画布（示意图）
    rtext_fig(fig, xf, yf, text, ...)       图形分数坐标（任意坐标系的图，先换算到图形坐标）
"""

from __future__ import annotations

import math
import re

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

INK = "#222222"
FS = 9
PT = 2.54 / 72  # 1 磅 = 0.03528 cm

_MF = Figure(figsize=(4, 4), dpi=300)
FigureCanvasAgg(_MF)
_MR = _MF.canvas.get_renderer()
_WC = {}
# 形如 c0～c13、（C1）～（C5）、1～5 的范围整体不拆行
# 数字与其后的量词（“16 个”“4 组”）也不拆开；\u200b 为人工指定的断行位置（不占宽度、不绘制）
_TOK = re.compile(r"[（(]?[A-Za-z]*\d+[）)]?～[（(]?[A-Za-z]*\d+[）)]?|\d+ ?[个组核种项次条位]|\$[^$]+\$|"
                  r"[A-Za-z0-9_.,:;+\-−=/<>%'()\[\]]+| +|.")
ZW = "\u200b"
NOHEAD = set("，。；：、）》”’！？,.;:)]%·…")
NOTAIL = set("（《“‘([")
CJK_ONLY = set("↑↓←→“”‘’")          # 这些符号取宋体字形（全角），不取 Times New Roman
CJK_FAM = ["SimSun", "Noto Serif CJK SC"]


def textw(s, fs, weight="normal", cjk=False):
    """字符串在字号 fs（磅）下的宽度（cm）。"""
    key = (s, fs, weight, cjk)
    if key not in _WC:
        kw = {"fontfamily": CJK_FAM} if cjk else {}
        t = _MF.text(0, 0, s, fontsize=fs, fontweight=weight, **kw)
        _WC[key] = t.get_window_extent(renderer=_MR).width / _MF.dpi * 2.54
        t.remove()
    return _WC[key]


def _layout(text, width, fs, weight="normal"):
    lines = []
    sp = 0.25 * fs * PT
    for para in text.split("\n"):
        cur, cw = [], 0.0
        for m in _TOK.finditer(para):
            t = m.group(0)
            if t == ZW:
                continue
            a = (" ", sp) if t.isspace() else (t, textw(t, fs, weight, t in CJK_ONLY))
            if a[0] == " " and not cur:
                continue
            if cur and a[0] != " " and cw + a[1] > width + 1e-6 and a[0][0] not in NOHEAD:
                while cur and cur[-1][0] == " ":
                    cur.pop()
                carry = []
                while cur and cur[-1][0] in NOTAIL:
                    carry.insert(0, cur.pop())
                if cur:
                    lines.append(cur)
                cur = carry
                cw = sum(x[1] for x in cur)
            cur.append(a)
            cw += a[1]
        while cur and cur[-1][0] == " ":
            cur.pop()
        lines.append(cur)
    return lines


_PUNCT_END = set("，。；：、！？）》”’")


def _is_cjk(ch):
    return "\u4e00" <= ch <= "\u9fff"


def layout(text, width, fs, weight="normal"):
    """分行：先保证行数最少，再在断点合适（尽量断在标点或中西文交界处）的前提下使各行长度均衡。"""
    out = []
    sp = 0.25 * fs * PT
    for para in text.split("\n"):
        atoms = []
        for m in _TOK.finditer(para):
            t = m.group(0)
            if t == ZW:
                atoms.append((ZW, 0.0))
            else:
                atoms.append((" ", sp) if t.isspace() else (t, textw(t, fs, weight, t in CJK_ONLY)))
        m_ = len(atoms)
        if m_ == 0:
            out.append([])
            continue

        def span(i, j):
            while i < j and atoms[i][0] in (" ", ZW):
                i += 1
            while j > i and atoms[j - 1][0] in (" ", ZW):
                j -= 1
            return i, j, sum(w for _, w in atoms[i:j])

        total = span(0, m_)[2]
        n_min = max(1, math.ceil(total / width - 1e-9))

        def brk(j):
            """在第 j 个原子之前断行的代价；None 表示不允许。"""
            k = j - 1
            had_space = False
            while k >= 0 and atoms[k][0] in (" ", ZW):
                k -= 1
                had_space = True
            q = j
            while q < m_ and atoms[q][0] in (" ", ZW):
                q += 1
                had_space = True
            if k < 0 or q >= m_:
                return None
            prev, nxt = atoms[k][0], atoms[q][0]
            if nxt[0] in NOHEAD or prev in NOTAIL:
                return None
            if had_space or prev[-1] in _PUNCT_END or nxt[0] in NOTAIL:
                return 0.0
            if _is_cjk(prev[-1]) and _is_cjk(nxt[0]):
                return 1.0
            return 0.5

        INF = float("inf")
        best = [(INF, 0, None)] * (m_ + 1)      # (代价, 行数, 前一断点)
        best[0] = (0.0, 0, None)
        # 目标行长：按最少行数均分
        for n_try in range(n_min, n_min + 6):
            L = total / n_try
            best = [(INF, 0, None)] * (m_ + 1)
            best[0] = (0.0, 0, None)
            for j in range(1, m_ + 1):
                pen_j = 0.0 if j == m_ else brk(j)
                if pen_j is None:
                    continue
                for i in range(0, j):
                    if best[i][0] == INF:
                        continue
                    a, b_, w = span(i, j)
                    if a == b_:
                        continue
                    if w > width + 1e-6 and b_ - a > 1:
                        continue
                    c = best[i][0] + 1e6 + (w - L) ** 2 + pen_j * (0.55 * L) ** 2
                    if c < best[j][0]:
                        best[j] = (c, best[i][1] + 1, i)
            if best[m_][0] < INF and best[m_][1] <= n_try:
                break
        cuts = []
        j = m_
        while j > 0:
            i = best[j][2]
            cuts.append((i, j))
            j = i
        for i, j in reversed(cuts):
            a, b_, _ = span(i, j)
            out.append(atoms[a:b_])
    return out


def rtext(ax, x, y, text, width=99.0, fs=FS, align="center", va="center", color=INK, weight="normal",
          ls=1.42, z=4):
    """在 (x, y) 处排一段混排文字；返回占用高度（cm）。"""
    lines = layout(text, width, fs, weight)
    lh = fs * ls * PT
    n = len(lines)
    top = {"center": y + n * lh / 2, "top": y, "bottom": y + n * lh}[va]
    for i, line in enumerate(lines):
        segs = []                            # 相邻的普通文字原子合并；公式与全角符号单独绘制
        for s, w in line:
            if s == ZW:
                continue
            kind = "math" if s.startswith("$") else ("cjk" if s in CJK_ONLY else "txt")
            if kind == "txt" and segs and segs[-1][2] == "txt":
                segs[-1][0] += s
                segs[-1][1] += w
            else:
                segs.append([s, w, kind])
        lw_ = sum(sg[1] for sg in segs)
        x0 = {"center": x - lw_ / 2, "left": x, "right": x - lw_}[align]
        base = top - (i + 1) * lh + (lh - fs * PT) / 2 + 0.12 * fs * PT
        for s, w, kind in segs:
            kw = {"fontfamily": CJK_FAM} if kind == "cjk" else {}
            ax.text(x0, base, s, fontsize=fs, fontweight=weight, color=color, ha="left", va="baseline",
                    zorder=z, **kw)
            x0 += w
    return n * lh


def nlines(text, width, fs):
    return len(layout(text, width, fs))


def rtext_fig(fig, xf, yf, text, width_cm=99.0, fs=FS, align="left", va="center", color=INK, weight="normal",
              ls=1.42, z=4):
    """在图形分数坐标 (xf, yf) 处排一段混排文字（宽度、行距按厘米计），返回占用高度（cm）。"""
    W, H = fig.get_size_inches() * 2.54
    lines = layout(text, width_cm, fs, weight)
    lh = fs * ls * PT
    n = len(lines)
    top = {"center": yf * H + n * lh / 2, "top": yf * H, "bottom": yf * H + n * lh}[va]
    for i, line in enumerate(lines):
        segs = []
        for s, w in line:
            if s == ZW:
                continue
            kind = "math" if s.startswith("$") else ("cjk" if s in CJK_ONLY else "txt")
            if kind == "txt" and segs and segs[-1][2] == "txt":
                segs[-1][0] += s
                segs[-1][1] += w
            else:
                segs.append([s, w, kind])
        lw_ = sum(sg[1] for sg in segs)
        x0 = {"center": xf * W - lw_ / 2, "left": xf * W, "right": xf * W - lw_}[align]
        base = top - (i + 1) * lh + (lh - fs * PT) / 2 + 0.12 * fs * PT
        for s, w, kind in segs:
            kw = {"fontfamily": CJK_FAM} if kind == "cjk" else {}
            fig.text(x0 / W, base / H, s, fontsize=fs, fontweight=weight, color=color, ha="left", va="baseline",
                     zorder=z, **kw)
            x0 += w
    return n * lh


def rtext_at(ax, x, y, text, transform=None, **kw):
    """把 ax 中 (x, y)（默认数据坐标）换算成图形分数坐标后调用 rtext_fig。须在坐标范围与版面固定后调用。"""
    fig = ax.figure
    tr = transform if transform is not None else ax.transData
    xf, yf = fig.transFigure.inverted().transform(tr.transform((x, y)))
    return rtext_fig(fig, xf, yf, text, **kw)
