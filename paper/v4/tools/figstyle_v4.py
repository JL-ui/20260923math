"""v4 插图风格：在 solution/paper_v2/figstyle.py 之上换配色、字体与输出格式。

数据图：低饱和学术配色（#3C5488 / #E64B35 / #00A087），浅色水平网格，去掉上、右边框，刻度朝外。
示意图：白底细黑线直角框，分组用浅灰底虚线框。
字体：英文与数字 Times New Roman，中文宋体（SVG 内保留字体名，Word 中按本机字体显示）。
输出：每张图同时写 SVG（插入 Word 的主图）与 300 dpi PNG（旧版 Word/WPS 的兜底）。
先 import 本模块，再 import figstyle，后者导出的常量即为 v4 取值。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "solution" / "paper_v2"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager as fm  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

import figstyle as fs  # noqa: E402

OUT = ROOT / "figures" / "v4"
OUT.mkdir(parents=True, exist_ok=True)
fs.OUT = OUT

# ---------------------------------------------------------------- 配色
C1, C2, C3 = "#3C5488", "#E64B35", "#00A087"
fs.C1, fs.C2, fs.C3 = C1, C2, C3
fs.PCOL = {1: C1, 2: C2, 3: C3}
fs.PNAME = {1: "问题一（场景A）", 2: "问题二（场景B）", 3: "问题三（场景B+L2）"}
fs.RED, fs.GREY, fs.DARK, fs.LIGHT = "#DC0000", "#8C8C8C", "#222222", "#F2F2F2"
fs.PIPE_COL = {"PIPE_MTE2": "#B09C85", "PIPE_MTE3": "#F39B7F", "PIPE_M": "#3C5488", "PIPE_V": "#00A087"}
BARS = ["#D9D9D9", "#BDBDBD", "#969696", "#8491B4", "#3C5488"]

# ---------------------------------------------------------------- 字体
_have = {f.name for f in fm.fontManager.ttflist}
LATIN = "Times New Roman" if "Times New Roman" in _have else "Liberation Serif"
CJK = "SimSun" if "SimSun" in _have else "Noto Serif CJK SC"
FAMILY = ["Times New Roman", "SimSun", "Liberation Serif", "Noto Serif CJK SC"]


def _rc():
    plt.rcParams.update({
        "font.family": FAMILY,
        "font.size": 9,
        "axes.titlesize": 9,
        "axes.labelsize": 9,
        "xtick.labelsize": 8.5,
        "ytick.labelsize": 8.5,
        "legend.fontsize": 8.5,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.linewidth": 0.7,
        "axes.edgecolor": "#333333",
        "axes.grid": True,
        "axes.grid.axis": "y",
        "grid.color": "#E3E3E3",
        "grid.linewidth": 0.6,
        "axes.axisbelow": True,
        "xtick.direction": "out",
        "ytick.direction": "out",
        "xtick.major.size": 3,
        "ytick.major.size": 3,
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
        "legend.frameon": False,
        "lines.linewidth": 1.4,
        "lines.markersize": 4.5,
        "figure.dpi": 150,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.03,
        "axes.unicode_minus": False,
        "svg.fonttype": "none",
        # $...$ 中的正体（含中文）走宋体，变量斜体走 Times New Roman
        "mathtext.fontset": "custom",
        "mathtext.rm": CJK,
        "mathtext.it": f"{LATIN}:italic",
        "mathtext.bf": f"{LATIN}:bold",
        "mathtext.cal": f"{LATIN}:italic",
        "mathtext.sf": LATIN,
        "mathtext.tt": "DejaVu Sans Mono",
        "mathtext.fallback": "stix",
    })


def use_serif():
    _rc()


def use_sans():
    # 示意图同样用宋体 + Times New Roman，不用黑体/雅黑
    _rc()
    plt.rcParams.update({"axes.grid": False})


def save(fig, name):
    svg = OUT / f"{name}.svg"
    fig.savefig(svg, facecolor="white")
    fig.savefig(OUT / f"{name}.png", facecolor="white")
    plt.close(fig)
    print("  ", svg.relative_to(ROOT))
    return svg


def box(ax, x, y, w, h, text, fc="#FFFFFF", ec="#222222", lw=0.8, fs_=8.5, color="#222222",
        title=None, title_fc=None, rad=0.0, weight="normal", ha="center", align_text="center",
        zorder=2, ls="-", wrap=True, **kw):
    """示意图样式 1：白底细线直角框；有标题时标题加粗、下方一条细分隔线。"""
    fsz = kw.pop("fs", fs_)
    if fc not in ("#FFFFFF", "white", "none", "#F2F2F2", "#f2f2f2"):
        fc = "#FFFFFF"
    ec = "#222222" if ec not in ("none",) else ec
    if text and wrap:
        text = fs.wrap_text(text, w - 0.25, fsz)
    p = FancyBboxPatch((x, y), w, h, boxstyle="square,pad=0", fc=fc, ec=ec, lw=lw, zorder=zorder, ls=ls)
    ax.add_patch(p)
    if title:
        th = min(0.32, h * 0.38)
        ax.plot([x, x + w], [y + h - th, y + h - th], color=ec, lw=0.5, zorder=zorder + 0.1)
        ax.text(x + w / 2, y + h - th / 2, title, ha="center", va="center", fontsize=fsz + 0.3,
                color="#111111", fontweight="bold", zorder=zorder + 0.2)
        if text:
            tx = x + w / 2 if align_text == "center" else x + 0.08
            ax.text(tx, y + (h - th) / 2, text, ha=align_text, va="center", fontsize=fsz, color=color,
                    zorder=zorder + 0.2, linespacing=1.35)
    elif text:
        tx = x + w / 2 if ha == "center" else x + 0.08
        ax.text(tx, y + h / 2, text, ha=ha, va="center", fontsize=fsz, color=color, zorder=zorder + 0.2,
                fontweight=weight, linespacing=1.35)
    return p


def group(ax, x, y, w, h, label=None, fs_=8.5):
    """虚线分组框（浅灰底）。"""
    p = FancyBboxPatch((x, y), w, h, boxstyle="square,pad=0", fc="#F2F2F2", ec="#8C8C8C", lw=0.6,
                       ls="--", zorder=0.5)
    ax.add_patch(p)
    if label:
        ax.text(x + 0.08, y + h - 0.08, label, ha="left", va="top", fontsize=fs_, color="#444444", zorder=0.6)
    return p


_orig_arrow = fs.arrow


def arrow(ax, p1, p2, color="#222222", lw=0.8, **kw):
    kw.setdefault("ms", 8)
    return _orig_arrow(ax, p1, p2, color="#222222" if color not in ("#DC0000",) else color, lw=lw, **kw)


fs.use_serif, fs.use_sans, fs.save, fs.box, fs.arrow = use_serif, use_sans, save, box, arrow
fs.group = group
fs.BARS = BARS
import logging
logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
_rc()


# ---------------------------------------------------------------- 含中文的 $...$ 改成 Unicode 写法
# matplotlib 的 mathtext 不能与中文混排（中文会变成方框），含中文的字符串里的公式一律换成
# Unicode 近似写法（希腊字母、上下标数字）；纯公式字符串仍走 mathtext。
import re as _re  # noqa: E402

from matplotlib.text import Text as _Text  # noqa: E402

_G = {"theta": "θ", "sigma": "σ", "beta": "β", "lambda": "λ", "omega": "ω", "delta": "δ", "Delta": "Δ",
      "pi": "π", "rho": "ρ", "mu": "μ", "nu": "ν", "eta": "η", "alpha": "α", "tau": "τ", "Phi": "Φ",
      "le": "≤", "leq": "≤", "ge": "≥", "geq": "≥", "to": "→", "rightarrow": "→", "in": "∈", "cdot": "·",
      "times": "×", "infty": "∞", "ne": "≠", "neq": "≠", "approx": "≈", "sum": "Σ", "max": "max",
      "min": "min", "lvert": "|", "rvert": "|", "ldots": "…", "dots": "…", "mathrm": "", "text": "",
      "operatorname": "", "mathbb": "", "mathcal": ""}
_SUB = dict(zip("0123456789+-()", "₀₁₂₃₄₅₆₇₈₉₊₋₍₎"))
_SUP = dict(zip("0123456789+-()n", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁽⁾ⁿ"))


def _script(s, table):
    return "".join(table.get(ch, ch) for ch in s)


def plain(t):
    def one(m):
        x = m.group(1)
        x = _re.sub(r"\\([a-zA-Z]+)", lambda g: _G.get(g.group(1), g.group(1)), x)
        x = _re.sub(r"\\[,;! ]", " ", x)
        x = _re.sub(r"_\{([^}]*)\}|_(\w)", lambda g: _script(g.group(1) or g.group(2), _SUB), x)
        x = _re.sub(r"\^\{([^}]*)\}|\^(\w)", lambda g: _script(g.group(1) or g.group(2), _SUP), x)
        return x.replace("{", "").replace("}", "")
    return _re.sub(r"(?<!\\)\$([^$]*)\$", one, t)


_orig_set_text = _Text.set_text


def _set_text(self, s):
    if isinstance(s, str) and "$" in s and _re.search(r"[⺀-鿿＀-￯]", s):
        s = plain(s)
    return _orig_set_text(self, s)


_Text.set_text = _set_text
