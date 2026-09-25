"""论文插图的统一风格与绘图小工具。"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt                      # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "figures" / "v2"
OUT.mkdir(parents=True, exist_ok=True)

# 三个问题贯穿全文的配色（Tol 色盲友好色系）
C1, C2, C3 = "#0077BB", "#EE7733", "#009988"
PCOL = {1: C1, 2: C2, 3: C3}
PNAME = {1: "问题一（场景 A）", 2: "问题二（场景 B）", 3: "问题三（场景 B + L2）"}
RED, GREY, DARK, LIGHT = "#CC3311", "#8C8C8C", "#2B2B2B", "#E8ECF2"
PIPE_COL = {"PIPE_MTE2": "#C9A227", "PIPE_MTE3": "#D1603D", "PIPE_M": "#3B6FB6", "PIPE_V": "#4F9D69"}

SERIF = ["Times New Roman", "SimSun"]
SANS = ["Microsoft YaHei", "Arial"]


def _mathfonts(rm):
    # 含 $...$ 的字符串整串走 mathtext：正体（含中文）用 rm 字体，数学斜体用 Times New Roman
    plt.rcParams.update({
        "mathtext.fontset": "custom",
        "mathtext.rm": rm,
        "mathtext.it": "Times New Roman:italic",
        "mathtext.bf": "Times New Roman:bold",
        "mathtext.sf": "Arial",
        "mathtext.tt": "Consolas",
        "mathtext.cal": "Times New Roman:italic",
        "mathtext.fallback": "stix",
    })


def use_serif():
    plt.rcParams.update({
        "font.family": SERIF,
        "font.size": 9,
        "axes.titlesize": 9.5,
        "axes.labelsize": 9.5,
        "xtick.labelsize": 8.5,
        "ytick.labelsize": 8.5,
        "legend.fontsize": 8.2,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.linewidth": 0.8,
        "axes.grid": True,
        "grid.color": "#E3E3E3",
        "grid.linewidth": 0.6,
        "grid.linestyle": "-",
        "axes.axisbelow": True,
        "legend.frameon": False,
        "figure.dpi": 150,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.03,
        "axes.unicode_minus": False,
    })
    _mathfonts("SimSun")


def use_sans():
    use_serif()
    plt.rcParams.update({"font.family": SANS, "axes.grid": False})
    _mathfonts("Microsoft YaHei")


def save(fig, name):
    path = OUT / f"{name}.png"
    fig.savefig(path, facecolor="white")
    plt.close(fig)
    print("  ", path.relative_to(ROOT))
    return path


def panel_label(ax, s, x=-0.02, y=1.02):
    ax.text(x, y, s, transform=ax.transAxes, fontsize=10, fontweight="bold", va="bottom", ha="left")


# ---------------------------------------------------------------- 流程图工具
import re as _re

_TOKEN = _re.compile(r"\$[^$]*\$|[A-Za-z0-9_./+\-()=,:%~^*<>|\[\]{}]+|\s+|.")


def _tok_width(t):
    """以 em（字号）为单位估计宽度。"""
    if t.startswith("$"):
        core = _re.sub(r"\\[a-zA-Z]+|[{}_^$]", "", t)
        return 0.55 * max(1, len(core))
    w = 0.0
    for ch in t:
        w += 1.0 if ord(ch) > 0x2E80 else (0.3 if ch == " " else 0.56)
    return w


def wrap_text(text, width_cm, fs):
    """按框宽自动折行：中文逐字可断，英文单词与 $公式$ 整体不断。"""
    max_em = width_cm / (fs * 0.03528) * 0.97
    out = []
    for line in text.split("\n"):
        cur, cur_w = "", 0.0
        for tok in _TOKEN.findall(line):
            tw = _tok_width(tok)
            if cur and cur_w + tw > max_em and not tok.isspace():
                out.append(cur.rstrip())
                cur, cur_w = "", 0.0
            if not cur and tok.isspace():
                continue
            cur += tok
            cur_w += tw
        out.append(cur.rstrip())
    return "\n".join(out)


def box(ax, x, y, w, h, text, fc="#FFFFFF", ec="#4A5A6A", lw=1.0, fs=8.5, color=DARK,
        title=None, title_fc=None, rad=0.06, weight="normal", ha="center", align_text="center",
        zorder=2, ls="-", wrap=True):
    """左下角 (x, y)，宽 w、高 h 的圆角框；title 非空时顶部画一条标题带。"""
    if text and wrap:
        text = wrap_text(text, w - 0.25, fs)
    p = FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={rad}",
                       fc=fc, ec=ec, lw=lw, zorder=zorder, ls=ls)
    ax.add_patch(p)
    if title:
        th = min(0.32, h * 0.38)
        tb = FancyBboxPatch((x, y + h - th), w, th, boxstyle=f"round,pad=0,rounding_size={rad}",
                            fc=title_fc or ec, ec=ec, lw=lw, zorder=zorder + 0.1)
        ax.add_patch(tb)
        ax.text(x + w / 2, y + h - th / 2, title, ha="center", va="center", fontsize=fs + 0.5,
                color="white", fontweight="bold", zorder=zorder + 0.2)
        if text:
            tx = x + w / 2 if align_text == "center" else x + 0.08
            ax.text(tx, y + (h - th) / 2, text, ha=align_text, va="center", fontsize=fs, color=color,
                    zorder=zorder + 0.2, linespacing=1.35)
    elif text:
        tx = x + w / 2 if ha == "center" else x + 0.08
        ax.text(tx, y + h / 2, text, ha=ha, va="center", fontsize=fs, color=color, zorder=zorder + 0.2,
                fontweight=weight, linespacing=1.35)
    return p


def arrow(ax, p1, p2, color="#4A5A6A", lw=1.1, style="-|>", ms=9, ls="-", conn="arc3,rad=0", zorder=1.5,
          shrinkA=1, shrinkB=1):
    a = FancyArrowPatch(p1, p2, arrowstyle=style, mutation_scale=ms, color=color, lw=lw, ls=ls,
                        connectionstyle=conn, zorder=zorder, shrinkA=shrinkA, shrinkB=shrinkB)
    ax.add_patch(a)
    return a


def canvas(w_cm, h_cm, xlim, ylim):
    use_sans()
    fig = plt.figure(figsize=(w_cm / 2.54, h_cm / 2.54))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.axis("off")
    return fig, ax
