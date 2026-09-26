# 图表样式参考：同一组真实数据按 5 种数据图风格、3 种示意图风格绘制，供作者挑选
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle
import numpy as np, sys, os

OUT = sys.argv[1]
plt.rcParams.update({
    "font.family": ["Times New Roman", "Liberation Serif", "SimSun", "Noto Serif CJK SC"],
    "mathtext.fontset": "stix", "svg.fonttype": "none", "axes.unicode_minus": False,
    "font.size": 10.5,
})
N = np.arange(1, 6)
SP = {"问题一": [1, 1.76, 2.45, 3.15, 3.67], "问题二": [1, 2.05, 2.87, 3.60, 4.20], "问题三": [1, 2.06, 2.87, 3.65, 4.25]}
METH = ["B1 随机", "B2 拓扑等分", "B3 负载均衡", "B4 通信聚类", "CAP-LS"]
BAR = np.array([[0.92, 1.10, 1.11], [1.22, 1.87, 1.90], [1.23, 1.67, 1.69], [2.35, 2.78, 2.83], [3.15, 3.60, 3.65]])

STYLES = {
 "A": dict(name="A 期刊灰阶（IEEE 风格）", cols=["#000000", "#555555", "#999999"], bars=["#f0f0f0", "#c8c8c8", "#8c8c8c", "#505050", "#000000"],
           mk=["o", "s", "^"], ls=["-", "--", "-."], grid=False, box=True, hatch=None),
 "B": dict(name="B 低饱和学术配色（Nature 风格）", cols=["#3C5488", "#E64B35", "#00A087"], bars=["#d9d9d9", "#bdbdbd", "#969696", "#8491B4", "#3C5488"],
           mk=["o", "s", "D"], ls=["-", "-", "-"], grid=True, box=False, hatch=None),
 "C": dict(name="C 色盲友好 Okabe-Ito 配色", cols=["#0072B2", "#D55E00", "#009E73"], bars=["#E69F00", "#56B4E9", "#F0E442", "#CC79A7", "#0072B2"],
           mk=["o", "s", "^"], ls=["-", "--", ":"], grid=True, box=True, hatch=None),
 "D": dict(name="D 蓝色单色系（数模获奖论文常见）", cols=["#08306b", "#2171b5", "#6baed6"], bars=["#deebf7", "#c6dbef", "#9ecae1", "#4292c6", "#08519c"],
           mk=["o", "s", "^"], ls=["-", "-", "-"], grid=True, box=True, hatch=None),
 "E": dict(name="E 黑白印刷（线型 + 填充纹理）", cols=["#000000", "#000000", "#000000"], bars=["white"] * 5,
           mk=["o", "s", "^"], ls=["-", "--", ":"], grid=False, box=True, hatch=["", "///", "\\\\\\", "xxx", "..."]),
}

def _style_ax(ax, st, key):
    ax.tick_params(direction="in" if st["box"] else "out", length=3, width=0.6)
    for sp in ["top", "right"]:
        ax.spines[sp].set_visible(st["box"])
    for sp in ax.spines.values(): sp.set_linewidth(0.7)
    if st["grid"]:
        ax.yaxis.grid(True, color="#e3e3e3", lw=0.6); ax.set_axisbelow(True)

def data_fig(key, st):
    # 两个面板分别成图，避免图例、坐标轴标签与分图标题互相挤压
    fig = plt.figure(figsize=(3.2, 3.0)); ax = fig.add_axes([0.2, 0.3, 0.75, 0.6])
    ax.plot(N, N, color="#7f7f7f", lw=0.8, ls=(0, (4, 3)), label="线性加速")
    for i, (k, v) in enumerate(SP.items()):
        ax.plot(N, v, color=st["cols"][i], marker=st["mk"][i], ls=st["ls"][i], lw=1.2, ms=4.5,
                mfc="white" if key in "AE" else st["cols"][i], label=k)
    ax.set_xlabel("核心数 N"); ax.set_ylabel("平均加速比"); ax.set_xticks(N); ax.set_ylim(0.5, 5.5); ax.set_yticks([1, 2, 3, 4, 5])
    ax.legend(frameon=False, fontsize=9, loc="upper left", handlelength=2.2)
    _style_ax(ax, st, key)
    fig.text(0.575, 0.03, "(a) 平均加速比折线图", ha="center", fontsize=10.5)
    fig.savefig(f"/tmp/_a_{key}.png", dpi=200); fig.savefig(f"{OUT}/数据图样式_{key}_a.svg"); plt.close(fig)
    fig = plt.figure(figsize=(3.2, 3.0)); ax = fig.add_axes([0.2, 0.3, 0.75, 0.48])
    x = np.arange(3); w = 0.16
    for j, m in enumerate(METH):
        ax.bar(x + (j - 2) * w, BAR[j], w, color=st["bars"][j], edgecolor="black" if key in "AE" else "none",
               lw=0.6, hatch=(st["hatch"][j] if st["hatch"] else None), label=m)
    ax.set_xticks(x); ax.set_xticklabels(["问题一", "问题二", "问题三"]); ax.set_ylabel("平均加速比")
    ax.set_ylim(0, 4.0)
    ax.legend(frameon=False, fontsize=8.5, ncol=2, loc="lower left", bbox_to_anchor=(-0.02, 1.01), columnspacing=0.8, handlelength=1.4)
    _style_ax(ax, st, key)
    fig.text(0.575, 0.03, "(b) 分组柱状图（N=4）", ha="center", fontsize=10.5)
    fig.savefig(f"/tmp/_b_{key}.png", dpi=200); fig.savefig(f"{OUT}/数据图样式_{key}_b.svg"); plt.close(fig)
    from PIL import Image, ImageDraw, ImageFont
    a, b = Image.open(f"/tmp/_a_{key}.png"), Image.open(f"/tmp/_b_{key}.png")
    c = Image.new("RGB", (a.width + b.width, a.height + 70), "white"); c.paste(a, (0, 70)); c.paste(b, (a.width, 70))
    f = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc", 30)
    ImageDraw.Draw(c).text((c.width // 2, 35), "样式 " + st["name"], fill="black", font=f, anchor="mm")
    c.save(f"{OUT}/数据图样式_{key}.png")

STEPS = ["读入计算图\n收缩 COPY", "S1 亲和原子化\n与无环切块", "S2 负载-通信\n联合分核", "S3 同步层次\n分层成子图", "S4 多起点候选\n官方评估择优"]

def box(ax, x, y, w, h, text, fc, ec, rounded, lw=0.8, fs=9, tc="black"):
    if rounded:
        p = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.08", fc=fc, ec=ec, lw=lw)
    else:
        p = Rectangle((x, y), w, h, fc=fc, ec=ec, lw=lw)
    ax.add_patch(p); ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, color=tc, linespacing=1.3)

def arrow(ax, x0, y0, x1, y1, c="black"):
    ax.annotate("", xy=(x1, y1), xytext=(x0, y0), arrowprops=dict(arrowstyle="-|>", color=c, lw=0.8, mutation_scale=9, shrinkA=0, shrinkB=0))

def diag(key):
    fig, ax = plt.subplots(figsize=(6.3, 2.3)); ax.set_xlim(0, 10.6); ax.set_ylim(0, 3.6); ax.axis("off")
    w, h, y = 1.8, 0.95, 1.5
    xs = [0.05 + i * 2.1 for i in range(5)]
    if key == "1":  # 细线框 + 灰底分组
        ax.add_patch(Rectangle((2.0, 1.2), 6.3, 1.55, fc="#f2f2f2", ec="#8c8c8c", lw=0.6, ls="--"))
        ax.text(5.15, 2.9, "构造一个候选（每组参数执行一次）", ha="center", fontsize=9)
        for i, s in enumerate(STEPS): box(ax, xs[i], y, w, h, s, "white", "black", False)
        name = "1 线框 + 虚线分组（学术论文常见）"
    elif key == "2":  # 泳道
        lanes = [("输入", 0), ("切图", 1), ("分核", 2), ("成子图", 3), ("评估", 4)]
        for i, (t, _) in enumerate(lanes):
            ax.add_patch(Rectangle((xs[i] - 0.15, 0.2), 2.0, 3.2, fc="#fafafa" if i % 2 else "#eeeeee", ec="none"))
            ax.text(xs[i] + 0.85, 3.15, t, ha="center", fontsize=9.5, fontweight="bold")
        for i, s in enumerate(STEPS): box(ax, xs[i], y, w, h, s, "white", "#333333", True)
        name = "2 分阶段泳道图"
    else:  # 圆角浅色填充 + 主题色
        fcs = ["#dbe8f5", "#c6dbef", "#9ecae1", "#6baed6", "#2171b5"]
        for i, s in enumerate(STEPS): box(ax, xs[i], y, w, h, s, fcs[i], "#2b5d8a", True, tc="white" if i == 4 else "black")
        box(ax, 5.2, 0.2, 5.3, 0.7, "官方评估器：Makespan 与额外搬运量", "white", "#2b5d8a", True, fs=9)
        arrow(ax, xs[4] + w / 2, y, xs[4] + w / 2, 0.9, "#2b5d8a")
        name = "3 圆角浅色填充（单一主题色）"
    for i in range(4): arrow(ax, xs[i] + w, y + h / 2, xs[i + 1], y + h / 2)
    fig.suptitle("示意图样式 " + name, fontsize=11, fontweight="bold", y=0.98)
    for ext in ("svg", "png"):
        fig.savefig(f"{OUT}/示意图样式_{key}.{ext}", dpi=200, bbox_inches="tight")
    plt.close(fig)

for k, s in STYLES.items(): data_fig(k, s)
for k in "123": diag(k)
