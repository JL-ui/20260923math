"""v3 机理示意图（停摆机理、同步层次、Task 时序）的原样副本，供 figs_diagrams_v4.py 调用。"""


from __future__ import annotations

import math

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle, Circle

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import figstyle_v4  # noqa: E402,F401
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "solution" / "paper_v2"))
import figstyle  # noqa: E402
from figstyle import (C1, C2, C3, DARK, GREY, RED, LIGHT, PIPE_COL, arrow, box, canvas, save, use_sans)  # noqa: E402

figstyle.OUT = figstyle.ROOT / "figures" / "v4"
figstyle.OUT.mkdir(parents=True, exist_ok=True)

# 浅色底
B1, B2, B3 = "#E3F0FA", "#FDEBDD", "#DDF1EE"
BG = "#F4F6FA"
EDGE = "#5B6B7B"


# ------------------------------------------------------------------ 技术路线图
def roadmap():
    fig, ax = canvas(16, 14.2, (0, 16), (0, 14.2))
    stages = [
        ("机理分析", 11.75, 13.95, "#3B6FB6"),
        ("统一建模", 9.05, 11.25, "#6A5ACD"),
        ("算法设计", 6.35, 8.55, "#2E8B57"),
        ("问题求解", 3.05, 5.85, "#C0632B"),
        ("检验评价", 0.25, 2.55, "#7A5230"),
    ]
    for name, y0, y1, col in stages:
        ax.add_patch(FancyBboxPatch((0.15, y0), 1.05, y1 - y0, boxstyle="round,pad=0,rounding_size=0.12",
                                    fc=col, ec=col, lw=0))
        ax.text(0.675, (y0 + y1) / 2, "\n".join(name), ha="center", va="center", color="white",
                fontsize=10, fontweight="bold", linespacing=1.25)
        ax.add_patch(FancyBboxPatch((1.4, y0), 14.45, y1 - y0, boxstyle="round,pad=0,rounding_size=0.12",
                                    fc="#FAFBFD", ec=col, lw=0.9, ls=(0, (4, 2))))
    # 1 机理分析
    y, h = 12.0, 1.7
    box(ax, 1.65, y, 4.7, h, "边界重建 · 核内执行序\n全局申请序 · Belady · FIFO",
        fc="white", ec="#3B6FB6", title="评估器实现解析", title_fc="#3B6FB6", fs=7.8)
    box(ax, 6.65, y, 4.1, h, "规模 · 深度 · 连通分量\n关键路径 · 容量压力",
        fc="white", ec="#3B6FB6", title="100 个用例结构特征", title_fc="#3B6FB6", fs=7.8)
    box(ax, 11.05, y, 4.55, h, "队首跨核 COPY_IN 未就绪\n→ 整核四条流水同时停摆",
        fc="#FFF3F0", ec=RED, title="关键机制", title_fc=RED, fs=7.8, lw=1.3)
    arrow(ax, (6.35, y + h / 2), (6.65, y + h / 2))
    arrow(ax, (10.75, y + h / 2), (11.05, y + h / 2))
    # 2 统一建模
    y, h = 9.3, 1.7
    xs = [1.65, 5.2, 8.75, 12.3]
    items = [("算子级 DAG", "收缩 COPY 节点\n得到 $E_{op}$"),
             ("决策与约束", "决策 $x,\\ y,\\ \\pi$\n约束 (C1)–(C9)"),
             ("目标与界", "目标：评估器 Makespan\n下界 $LB_N$"),
             ("可行性构造", "同步层次 $r(v)$\n(核心, 层次) 成子图")]
    for i, (t, s) in enumerate(items):
        box(ax, xs[i], y, 3.3, h, s, fc="white", ec="#6A5ACD", title=t, title_fc="#6A5ACD", fs=7.8,
            lw=1.3 if i == 3 else 1.0)
        if i:
            arrow(ax, (xs[i - 1] + 3.3, y + h / 2), (xs[i], y + h / 2))
    # 3 算法设计
    y, h = 6.6, 1.7
    items = [("S1 无环切块", "扇出阈值原子化\nSCC 合并 · 连续分块"),
             ("S2 联合分配", "负载 · 字节 · 同步深度\nLPT + 局部搜索"),
             ("S3 分层成形", "ASAP / ALAP 层指派\n(核心, 层次) 成子图"),
             ("S4 组合择优", "候选网格 c0–c17\n退火 / 采样\n评估器择优")]
    for i, (t, s) in enumerate(items):
        box(ax, xs[i], y, 3.3, h, s, fc="white", ec="#2E8B57", title=t, title_fc="#2E8B57", fs=7.8)
        if i:
            arrow(ax, (xs[i - 1] + 3.3, y + h / 2), (xs[i], y + h / 2))
    # 4 问题求解
    y, h = 3.3, 2.3
    cols = [(C1, B1, "问题一（场景 A）", "子图即 Task · 经 DDR 中转\nTask 级时序模型 · 偏粗粒度\n代理驱动模拟退火\n→ 1～5 核加速比曲线"),
            (C2, B2, "问题二（场景 B）", "核即 Task · 同核零搬运\n$(\\lambda-1)$ 超图割 · 驻留–顺序权衡\n单算子子图 + 容量感知表调度\n→ 1～5 核加速比曲线"),
            (C3, B3, "问题三（B + 只读 L2）", "FIFO 命中规则 · 复用度模型\n命中字节按 250 B/cycle 折算\n两类 Cache 指标分开报告\n→ 两种配置的对比曲线")]
    for i, (ec, fc, t, s) in enumerate(cols):
        x = 1.65 + i * 4.75
        box(ax, x, y, 4.45, h, s, fc=fc, ec=ec, title=t, title_fc=ec, fs=7.8, lw=1.2)
    # 5 检验评价
    y, h = 0.5, 1.8
    items = ["四类基线\n配对检验", "事后消融\n机制分析", "粒度与硬件\n灵敏度", "理论下界\n差距", "代理模型\n可靠性", "结构特征\n与难例"]
    for i, s in enumerate(items):
        box(ax, 1.65 + i * 2.37, y, 2.15, h, s, fc="white", ec="#7A5230", fs=7.8, lw=1.0)
    # 阶段间箭头
    for ya, yb in ((11.75, 11.25), (9.05, 8.55), (6.35, 5.85), (3.05, 2.55)):
        arrow(ax, (8.6, ya + 0.02), (8.6, yb - 0.02), color="#4A5A6A", lw=1.6, ms=12)
    save(fig, "fig_roadmap")


# ------------------------------------------------------------------ 硬件结构
def hardware():
    fig, ax = canvas(15.5, 7.4, (0, 15.5), (0, 7.4))
    for k in range(4):
        x = 0.35 + k * 3.8
        ax.add_patch(FancyBboxPatch((x, 2.55), 3.4, 4.6, boxstyle="round,pad=0,rounding_size=0.12",
                                    fc="#F7F9FC", ec="#3B6FB6", lw=1.2))
        ax.text(x + 1.7, 6.85, f"AI Core {k}", ha="center", va="center", fontsize=9, fontweight="bold",
                color="#1F3F6B")
        rows = [("Cube 矩阵单元  PIPE_M", PIPE_COL["PIPE_M"]), ("Vector 向量单元  PIPE_V", PIPE_COL["PIPE_V"]),
                ("搬入  PIPE_MTE2", PIPE_COL["PIPE_MTE2"]), ("搬出  PIPE_MTE3", PIPE_COL["PIPE_MTE3"])]
        for i, (t, c) in enumerate(rows):
            yy = 6.15 - i * 0.62
            ax.add_patch(FancyBboxPatch((x + 0.18, yy), 3.04, 0.48, boxstyle="round,pad=0,rounding_size=0.06",
                                        fc=c, ec="none", alpha=0.18))
            ax.add_patch(Rectangle((x + 0.18, yy), 0.07, 0.48, fc=c, ec="none"))
            ax.text(x + 1.72, yy + 0.24, t, ha="center", va="center", fontsize=7.4, color=DARK)
        box(ax, x + 0.18, 2.75, 1.45, 0.72, "L1\n512 KB", fc="white", ec="#7A8A9A", fs=7.4)
        box(ax, x + 1.77, 2.75, 1.45, 0.72, "UB\n128 KB", fc="white", ec="#7A8A9A", fs=7.4)
    # L2 与 DDR：DDR 通路从 L2 条背后穿过（L2 条在上层且不透明）
    ax.add_patch(FancyBboxPatch((0.35, 1.35), 14.8, 0.8, boxstyle="round,pad=0,rounding_size=0.1",
                                fc="#FFF6E5", ec="#D4A017", lw=1.2, ls=(0, (4, 2)), zorder=3))
    ax.text(7.75, 1.75, "共享只读 L2 Cache（仅问题三）：1 MB，250 B/cycle，FIFO 淘汰，带宽独立于 DDR",
            ha="center", va="center", fontsize=8, color="#7A5A00", zorder=4)
    ax.add_patch(FancyBboxPatch((0.35, 0.15), 14.8, 0.85, boxstyle="round,pad=0,rounding_size=0.1",
                                fc="#EEF0F3", ec="#5B6B7B", lw=1.2, zorder=3))
    ax.text(7.75, 0.57, "共享 DDR 主存：总带宽 60 B/cycle，所有核的 COPY_IN / COPY_OUT / 换入换出公平共享",
            ha="center", va="center", fontsize=8, color=DARK, zorder=4)
    for k in range(4):
        x = 0.35 + k * 3.8
        arrow(ax, (x + 2.6, 2.55), (x + 2.6, 2.15), style="<|-|>", ms=7, color="#8A6A00", lw=1.0, zorder=2)
        arrow(ax, (x + 0.8, 2.55), (x + 0.8, 1.0), style="<|-|>", ms=7, color="#5B6B7B", lw=1.0, zorder=2)
    save(fig, "fig_hardware")


# ------------------------------------------------------------------ 全局申请序停摆机理
def stall_mechanism():
    fig, axes = plt.subplots(2, 1, figsize=(15.5 / 2.54, 8.6 / 2.54))
    use_sans()
    plt.rcParams.update({"axes.grid": False})
    fig.subplots_adjust(left=0.13, right=0.985, top=0.93, bottom=0.12, hspace=0.62)
    lanes = ["MTE2", "M", "V", "MTE3"]
    lane_col = [PIPE_COL["PIPE_MTE2"], PIPE_COL["PIPE_M"], PIPE_COL["PIPE_V"], PIPE_COL["PIPE_MTE3"]]
    # 远端数据在 t=7.5 才到。(a) 未分层：核内申请序 a1 a2 CI* c b1 b2；(b) 分层：a1 a2 b1 b2 | CI* c
    T_ARR = 7.5
    spec_a = {"MTE2": [(0, 1, "a1入"), (1, 1, "a2入"), (T_ARR, 1.2, "CI*"), (8.7, 1, "b1入"), (9.7, 1, "b2入")],
              "M": [(1, 2, "a1"), (3, 2, "a2"), (8.7, 1.6, "c"), (10.3, 1.4, "b1")],
              "V": [(10.7, 1.3, "b2")],
              "MTE3": [(5, 0.8, "出"), (12.0, 0.8, "出")]}
    spec_b = {"MTE2": [(0, 1, "a1入"), (1, 1, "a2入"), (2, 1, "b1入"), (3, 1, "b2入"), (T_ARR, 1.2, "CI*")],
              "M": [(1, 2, "a1"), (3, 2, "a2"), (5, 1.4, "b1"), (8.7, 1.6, "c")],
              "V": [(4, 1.3, "b2")],
              "MTE3": [(5.3, 0.8, "出"), (6.4, 0.8, "出"), (10.3, 0.8, "出")]}
    titles = ["(a) 未分层：依赖远端数据的 CI* 排在核内申请序前部，队首被堵，四条流水一起空转",
              "(b) 同步层次分层：CI* 及其后继推到下一层，本地就绪的 b1、b2 先执行，数据到达时正好接上"]
    for ax, spec, title, stall in zip(axes, (spec_a, spec_b), titles, ((5.8, T_ARR), None)):
        for i, ln in enumerate(lanes):
            yy = 3 - i
            ax.axhline(yy, color="#EEF0F3", lw=9, zorder=0)
            for s, d, t in spec.get(ln, []):
                is_ci = t == "CI*"
                ax.add_patch(FancyBboxPatch((s + 0.04, yy - 0.34), d - 0.08, 0.68,
                                            boxstyle="round,pad=0,rounding_size=0.08",
                                            fc=RED if is_ci else lane_col[i], ec="white", lw=0.6,
                                            alpha=0.95 if is_ci else 0.85))
                ax.text(s + d / 2, yy, t, ha="center", va="center", fontsize=6.8, color="white",
                        fontweight="bold")
        # 远端数据到达
        ax.axvline(T_ARR, color=RED, lw=0.9, ls=(0, (3, 2)))
        ax.text(T_ARR + 0.08, 3.72, "远端数据到达（COPY_OUT 完成 + 500 cycle）", color=RED, fontsize=6.8,
                ha="left", va="center")
        if stall:
            ax.axvspan(stall[0], stall[1], ymin=0.1, ymax=0.83, color=RED, alpha=0.12, lw=0)
            ax.text((stall[0] + stall[1]) / 2, 1.5, "整核\n停摆", ha="center", va="center",
                    fontsize=8, color=RED, fontweight="bold")
        ax.set_yticks([3, 2, 1, 0])
        ax.set_yticklabels(["PIPE_MTE2", "PIPE_M", "PIPE_V", "PIPE_MTE3"], fontsize=7.4)
        ax.set_xlim(0, 13.2)
        ax.set_ylim(-0.6, 4.0)
        ax.set_xticks([])
        for sp in ("top", "right", "left"):
            ax.spines[sp].set_visible(False)
        ax.set_title(title, fontsize=8.2, loc="left", pad=3)
        ax.tick_params(axis="y", length=0)
    # 申请序说明放在坐标轴下方左侧，时间方向放在右侧
    axes[0].text(0.0, -0.95, "核内申请序：a1 → a2 → CI* → c → b1 → b2（只有队首可发射）", ha="left",
                 va="top", fontsize=7, color="#555555", clip_on=False)
    axes[1].text(0.0, -0.95, "核内申请序：a1 → a2 → b1 → b2 ｜ CI* → c（第 r 层 ｜ 第 r+1 层）", ha="left",
                 va="top", fontsize=7, color="#555555", clip_on=False)
    for ax in axes:
        ax.text(13.2, -0.95, "时间 →", ha="right", va="top", fontsize=7.4, color="#333333", clip_on=False)
    save(fig, "fig_stall_mechanism")


# ------------------------------------------------------------------ 切图 / 分核 / 分层示意
def levels_sketch():
    """(a) 算子级 DAG；(b) σ 连续区间成块；(c) 列 = 同步层次、行 = 核心的网格：
    子图就是网格中的一格，所有边都指向同列或右侧的格子，因此子图商图无环。"""
    use_sans()
    fig = plt.figure(figsize=(16 / 2.54, 6.4 / 2.54))
    gs = fig.add_gridspec(1, 3, width_ratios=[1, 1, 1.35], left=0.01, right=0.995, top=0.88, bottom=0.12,
                          wspace=0.06)
    axes = [fig.add_subplot(gs[0, i]) for i in range(3)]
    pos = {0: (0, 1), 1: (0, -1), 2: (1, 1.6), 3: (1, 0), 4: (1, -1.6), 5: (2, 0.8), 6: (2, -0.8), 7: (3, 0)}
    edges = [(0, 2), (0, 3), (1, 3), (1, 4), (2, 5), (3, 5), (3, 6), (4, 6), (5, 7), (6, 7)]
    core = {0: 0, 2: 0, 5: 0, 7: 0, 1: 1, 3: 1, 4: 1, 6: 1}
    blocks = {0: 0, 2: 1, 3: 1, 4: 1, 1: 0, 5: 2, 6: 2, 7: 3}
    lev = {}
    for v in range(8):
        preds = [u for u, w in edges if w == v]
        lev[v] = max([lev[u] + (core[u] != core[v]) for u in preds], default=0)
    blk_col = ["#6C8EBF", "#D7856A", "#79B38A", "#A58BC9"]
    core_col = [C1, C2]
    # (c) 的网格坐标：x = 层次，y = 核心带内的上下位置
    groups = {}
    for v in sorted(range(8)):
        groups.setdefault((core[v], lev[v]), []).append(v)
    pos_c = {}
    for (c, r), vs in groups.items():
        for i, v in enumerate(vs):
            off = (i - (len(vs) - 1) / 2) * 0.95
            pos_c[v] = (r * 1.45, (1.05 if c == 0 else -1.05) + off)
    titles = ["(a) 算子级 DAG", "(b) 亲和原子化 + $\\sigma$ 连续区间分块", "(c) 子图 = (核心, 层次) 等价类"]
    for k, ax in enumerate(axes):
        ax.axis("off")
        ax.set_title(titles[k], fontsize=8.6, pad=2)
        P = pos if k < 2 else pos_c
        if k < 2:
            ax.set_xlim(-0.5, 3.5)
            ax.set_ylim(-2.25, 2.25)
        else:
            ax.set_xlim(-1.35, 3.6)
            ax.set_ylim(-2.25, 2.25)
            sid = 0
            for key in sorted(groups, key=lambda t: (t[1], t[0])):
                c, r = key
                x0 = r * 1.45 - 0.5
                y0 = 0.1 if c == 0 else -2.0
                ax.add_patch(FancyBboxPatch((x0, y0), 1.0, 1.9, boxstyle="round,pad=0,rounding_size=0.14",
                                            fc=core_col[c], alpha=0.10, ec=core_col[c], lw=0.9, ls=(0, (3, 2))))
                ax.text(x0 + 0.08, y0 + 1.78, f"S{sid}", fontsize=7.2, color=core_col[c],
                        fontweight="bold", ha="left", va="center")
                sid += 1
            for r in range(3):
                ax.text(r * 1.45, -2.18, f"层 {r}", ha="center", va="center", fontsize=7.4, color="#444444")
            ax.text(-1.05, 1.05, "核 0", ha="center", va="center", fontsize=7.6, color=C1, fontweight="bold")
            ax.text(-1.05, -1.05, "核 1", ha="center", va="center", fontsize=7.6, color=C2, fontweight="bold")
            ax.axhline(0.0, xmin=0.05, xmax=0.98, color="#C8CDD3", lw=0.6)
        for u, w in edges:
            (x1, y1), (x2, y2) = P[u], P[w]
            cross = k == 2 and core[u] != core[w]
            arrow(ax, (x1, y1), (x2, y2), color=RED if cross else "#9AA5B1", lw=1.2 if cross else 0.9,
                  ms=7, shrinkA=8, shrinkB=8, ls=(0, (3, 2)) if cross else "-")
        for v, (x, y) in P.items():
            fc = "#9AA5B1" if k == 0 else (blk_col[blocks[v]] if k == 1 else core_col[core[v]])
            ax.add_patch(Circle((x, y), 0.25, fc=fc, ec="white", lw=1.0, zorder=3))
            ax.text(x, y, f"{v}", ha="center", va="center", fontsize=7.5, color="white", zorder=4,
                    fontweight="bold")
    axes[0].text(1.5, -2.2, "节点 = 算子，边 = 张量依赖", ha="center", fontsize=7.2, color="#555555")
    axes[1].text(1.5, -2.2, "同色 = 同一块（$\\sigma$ 的连续区间）", ha="center", fontsize=7.2, color="#555555")
    save(fig, "fig_levels_sketch")


# ------------------------------------------------------------------ 场景 A 的 Task 时序
def task_timeline():
    fig, ax = plt.subplots(figsize=(15.5 / 2.54, 4.6 / 2.54))
    use_sans()
    fig.subplots_adjust(left=0.08, right=0.99, top=0.9, bottom=0.2)
    tasks = [  # core, start, dur, name
        (0, 0.0, 3.0, "$s_1$"), (0, 3.4, 2.4, "$s_3$"), (0, 9.9, 2.2, "$s_5$"),
        (1, 0.0, 2.2, "$s_2$"), (1, 4.2, 3.0, "$s_4$"), (1, 7.6, 1.8, "$s_6$")]
    for c, s, d, n in tasks:
        col = C1 if c == 0 else C2
        ax.add_patch(FancyBboxPatch((s, (1 - c) - 0.3), d, 0.6, boxstyle="round,pad=0,rounding_size=0.08",
                                    fc=col, ec="white", alpha=0.85))
        ax.text(s + d / 2, 1 - c, n, ha="center", va="center", color="white", fontsize=9, fontweight="bold")
    # 同核等待 W_same
    ax.annotate("", xy=(3.4, 1.42), xytext=(3.0, 1.42), arrowprops=dict(arrowstyle="<->", color=DARK, lw=0.8))
    ax.text(3.2, 1.5, "$W_{same}$", ha="center", va="bottom", fontsize=7.6)
    # 跨核等待 W_cross：s1 -> s4
    arrow(ax, (3.0, 0.7), (4.2, 0.3), color=RED, lw=1.0, ms=8, ls=(0, (3, 2)))
    ax.text(3.95, 0.52, "$W_{cross}$", color=RED, fontsize=7.6, ha="left")
    # s4 -> s5 跨核 + 同核等待取最大
    arrow(ax, (7.2, 0.3), (9.9, 0.7), color=RED, lw=1.0, ms=8, ls=(0, (3, 2)))
    ax.text(8.1, 0.64, "$W_{cross}$", color=RED, fontsize=7.6)
    ax.axvspan(5.8, 9.9, ymin=0.62, ymax=0.9, color=GREY, alpha=0.15, lw=0)
    ax.text(7.85, 1.12, "核 0 空等跨核前驱 $s_4$", fontsize=7.4, color="#555555", ha="center")
    ax.set_yticks([1, 0])
    ax.set_yticklabels(["核 0", "核 1"], fontsize=8)
    ax.set_xlim(-0.2, 12.4)
    ax.set_ylim(-0.6, 1.85)
    ax.set_xticks([])
    ax.set_xlabel("时间 →", fontsize=8)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.tick_params(axis="y", length=0)
    save(fig, "fig_task_timeline")


# ------------------------------------------------------------------ CAP-LS 框架
def framework():
    fig, ax = canvas(16, 7.6, (0, 16), (0, 7.6))
    box(ax, 0.2, 5.0, 2.1, 1.9, "计算图 $G$\n核数 $N$\nconfig.txt", fc=BG, ec=EDGE, title="输入", title_fc=EDGE, fs=7.8)
    stages = [("S1 无环切块", "扇出阈值 $\\theta$ 原子化\nTarjan 合并 SCC\n$\\sigma$ 连续区间成块"),
              ("S2 联合分配", "LPT / 轮转 / 连续段初解\n代价 $F$：负载 · 字节 · 同步\n首次改进局部搜索"),
              ("S3 分层成形", "同步层次 $r(v)$\nALAP 填充 / 层压缩\n按层次–核心字典序编号"),
              ("S4 组合择优", "候选网格 c0–c17\n退火 / 优先级采样\n评估器择优")]
    cols = ["#3B6FB6", "#6A5ACD", "#2E8B57", "#C0632B"]
    for i, ((t, s), c) in enumerate(zip(stages, cols)):
        x = 2.75 + i * 3.25
        box(ax, x, 4.75, 2.95, 2.4, s, fc="white", ec=c, title=t, title_fc=c, fs=7.6)
        arrow(ax, (x - 0.45 if i == 0 else x - 0.3, 5.95), (x, 5.95))
    arrow(ax, (2.3, 5.95), (2.75, 5.95))
    box(ax, 2.75, 3.2, 12.7, 1.1, "标准求解流程：在本流程产生的候选中取评估器 Makespan 最小者作为输出方案\n"
        "（消融、基线、灵敏度等检验实验产生的方案不参与选择）", fc="#FFF8EC", ec="#C0632B", fs=7.8, wrap=False)
    arrow(ax, (14.7, 4.75), (14.7, 4.3))
    box(ax, 0.2, 3.2, 2.1, 1.1, "输出\n规定格式方案", fc=BG, ec=EDGE, fs=7.6, wrap=False)
    arrow(ax, (2.75, 3.75), (2.3, 3.75))
    # 三个问题的差异
    difs = [(C1, B1, "问题一（场景 A）", "Task = 子图；同步权重 $\\omega$ = 1000\n偏粗粒度；c0–c13 + 模拟退火"),
            (C2, B2, "问题二（场景 B）", "Task = 核心；$\\omega$ = 500\n+ 单算子子图表调度与采样"),
            (C3, B3, "问题三（场景 B + L2）", "同问题二；代价中命中字节按\n250 B/cycle 折算；问题三评估器择优")]
    ax.text(8.0, 2.78, "三个问题的差别集中在代价权重、候选集合与 L2 折算三处", ha="center", fontsize=8,
            color="#444444", fontweight="bold")
    for i, (ec, fc, t, s) in enumerate(difs):
        box(ax, 0.2 + i * 5.3, 0.2, 5.0, 2.2, s, fc=fc, ec=ec, title=t, title_fc=ec, fs=7.6)
    save(fig, "fig_framework")


# ------------------------------------------------------------------ 各问题求解流程图
def flow(name, steps, side, col, fc, height=15.0):
    """steps: [(标题, 说明)]；side: {步骤序号: 右侧批注}"""
    n = len(steps)
    fig, ax = canvas(15.5, height, (0, 15.5), (0, height))
    top = height - 0.35
    gap = (height - 0.7) / n
    bh = gap * 0.72
    for i, (t, s) in enumerate(steps):
        y = top - (i + 1) * gap + (gap - bh) / 2
        special = t.startswith("★")
        tt = t.lstrip("★")
        box(ax, 1.2, y, 7.6, bh, s, fc="#FFF8EC" if special else (fc if i in (0, n - 1) else "white"),
            ec=col if not special else "#C0632B", title=tt, title_fc=col if not special else "#C0632B",
            fs=7.8, lw=1.1)
        if i:
            arrow(ax, (5.0, y + bh + (gap - bh) + 0.0), (5.0, y + bh), color=col, lw=1.3, ms=10)
        if i in side:
            tx, note = side[i]
            box(ax, 9.5, y + 0.04, 5.8, bh - 0.08, note, fc="#F6F7F9", ec="#A0AAB4", fs=7.3, ls=(0, (3, 2)),
                ha="left")
            arrow(ax, (9.5, y + bh / 2), (8.8, y + bh / 2), color="#A0AAB4", lw=0.9, ms=7, style="-|>")
    save(fig, name)


def flows():
    flow("fig_flow_p1", [
        ("输入与预处理", "读入计算图与固定配置；收缩 COPY 得到算子级 DAG $E_{op}$"),
        ("S1 无环切块", "扇出阈值 $\\theta$ 亲和原子化 → SCC 合并 → 沿 $\\sigma$ 切成计算量 ≤ $\\beta W/N$ 的块"),
        ("S2 联合分配", "LPT / 轮转 / 连续段初解；以代价 $F$（$\\omega=W_{cross}$）做移动式局部搜索"),
        ("S3 分层成形", "按同步层次把 (核心, 层次) 等价类成子图；每个子图即一个 Task"),
        ("S4 候选择优", "c0–c13 共 14 组候选按图规模裁剪后交评估器；4 个大图先用代理 $F$ 预筛"),
        ("代理驱动退火", "以 Task 级时序代理为适应度，合并 / 拆分 / 迁移 Task，每步检查 Task 图无环"),
        ("输出", "网格候选与退火候选中评估器 Makespan 最小者，输出为规定格式方案"),
    ], {2: (0, "搜索代理 $F$（负载 · 字节 · 同步深度）\n边界搬运项与评估器输出逐字节一致"),
        3: (0, "引理 3-1：按层次–核心字典序编号\n→ 结构性约束 C1～C5 由构造保证"),
        4: (0, "候选覆盖不同粒度 $\\beta$ 与分配方式\n场景 A 倾向较粗粒度"),
        5: (0, "初温取代理值 2%，1500 步几何降温\n取代理前 3 名交评估器")}, C1, B1, height=13.6)
    flow("fig_flow_p2", [
        ("场景 B 的执行模型", "同核子图并为一个 Task：同核边界零搬运，跨核经 COPY_OUT + 500 cycle + COPY_IN"),
        ("S1–S2 分核", "沿用 CAP-LS 的无环切块与联合分配；代价 $F$ 的同步权重取 $\\delta=500$"),
        ("S3 分层 / 表调度", "候选一：(核心, 层次) 成子图；候选二：单算子子图 + 容量感知表调度"),
        ("S4 候选择优", "c0–c17 共 18 组候选全部交评估器，覆盖“每核一个子图”到“一算子一子图”"),
        ("优先级采样", "对最优单算子子图候选加 Gumbel 扰动采 16 个，事件模拟代理排序，前 3 名交评估器"),
        ("输出", "网格候选与采样候选中评估器 Makespan 最小者，输出为规定格式方案"),
    ], {0: (0, "单生产核中间张量与图输入张量的跨核搬运\n可写成以字节为权的 $(\\lambda-1)$ 超图割"),
        2: (0, "评分 = 向上秩 − 驻留增量 + 流水交错\n+ Gumbel 噪声（算法 5-1）"),
        4: (0, "采样只改核内顺序；按层稳定排序后\n引理 3-1 仍成立")}, C2, B2, height=12.4)
    flow("fig_flow_p3", [
        ("L2 命中规则", "只读 FIFO：发射时判命中、完成时写入、命中不刷新顺序，带宽独立于 DDR"),
        ("命中来源与复用度", "命中只来自多核复读与换入复读；复用度 reuse(t)、Cache 价值 value(t)"),
        ("Cache 感知代价", "预测命中字节 $H_k$ 按 250 B/cycle 折算进 PIPE_MTE2 占用与 DDR 下界"),
        ("CAP-LS 求解", "S1–S4 与采样同问题二，候选由问题三评估器择优"),
        ("两种配置对比", "配置最优比较：问题二、三各自方案；纯 L2 收益：同一方案在两种配置下评估"),
        ("机理与灵敏度", "命中 / 未命中来源拆分；L2 容量、带宽灵敏度（18 个用例子集）"),
    ], {1: (0, "命中字节上界与后续读取命中的\n时序条件（场景解析模型）"),
        2: (0, "搜索代理的修正：重复读取的\n代价按命中折算后下降"),
        4: (0, "题目要求：1～5 核对比曲线 +\n相同核数下的加速比")}, C3, B3, height=12.4)


