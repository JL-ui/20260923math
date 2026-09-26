"""v4 示意图（样式 1：白底细线直角框，虚线浅灰分组框；中文宋体，英文 Times New Roman）。

    python paper/v4/tools/figs_diagrams_v4.py

图 1-1 硬件结构、图 1-2 权衡关系、图 1-3 技术路线、CAP-LS 框架与三个问题的求解流程图在本文件重画；
全局申请序停摆示意、同步层次分层示意、场景 A 的 Task 时序三张机理图沿用 v3 的画法（配色随 v4）。
坐标单位均为厘米，画布宽度等于图在 Word 中的插入宽度，因此图内字号即印刷字号。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import figstyle_v4  # noqa: E402,F401  必须先于 figstyle
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "solution" / "paper_v2"))
import figstyle  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, Rectangle  # noqa: E402

import figs_diagrams_v3_legacy as legacy  # noqa: E402
import math  # noqa: E402
from richtext_v4 import PT, nlines, rtext  # noqa: E402  中西文与公式混排

INK = "#222222"
SUBINK = "#555555"
FS = 9          # 框内正文字号（磅）
FS_T = 9.5      # 框标题字号


def canvas(w, h):
    figstyle.use_sans()
    fig = plt.figure(figsize=(w / 2.54, h / 2.54))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.axis("off")
    return fig, ax


def wrap(text, width, fs):
    """自动折行，并做避头处理：行首不出现逗号、句号、右括号等标点。"""
    lines = figstyle.wrap_text(text, width * 0.96, fs).split("\n")
    for i in range(1, len(lines)):
        while lines[i] and lines[i][0] in "，。；：、）》”,.;:)":
            lines[i - 1] += lines[i][0]
            lines[i] = lines[i][1:]
    return "\n".join(x for x in lines if x)


def rect(ax, x, y, w, h, lw=0.8, ls="-", fc="white", ec=INK, z=2):
    ax.add_patch(Rectangle((x, y), w, h, fc=fc, ec=ec, lw=lw, ls=ls, zorder=z))


def tbox(ax, x, y, w, h, body="", title=None, fs=FS, lw=0.8, ls="-", fc="white", align="center", z=2, wrap_=True):
    """直角框：可选加粗标题（下接细分隔线），正文自动折行、在剩余区域内垂直居中。"""
    rect(ax, x, y, w, h, lw=lw, ls=ls, fc=fc, z=z)
    top = y + h
    if title:
        th = 0.62
        ax.text(x + w / 2, top - th / 2, title, ha="center", va="center", fontsize=FS_T, fontweight="bold",
                color=INK, zorder=z + 1)
        ax.plot([x, x + w], [top - th, top - th], color=INK, lw=0.5, zorder=z + 1)
        top -= th
    if body:
        tx = x + w / 2 if align == "center" else x + 0.18
        rtext(ax, tx, (y + top) / 2, body, (w - 0.36) if wrap_ else 99.0, fs=fs, align=align, z=z + 1)


def group(ax, x, y, w, h, label=None, fs=8.5):
    rect(ax, x, y, w, h, lw=0.6, ls=(0, (4, 2)), fc="#F2F2F2", ec="#8C8C8C", z=0.5)
    if label:
        ax.text(x + 0.15, y + h - 0.12, label, ha="left", va="top", fontsize=fs, color=SUBINK, zorder=0.6)


def arr(ax, p, q, ls="-", color=INK, lw=0.8, both=False, rad=0.0):
    a = FancyArrowPatch(p, q, arrowstyle="<|-|>" if both else "-|>", mutation_scale=8, lw=lw, color=color,
                        ls=ls, shrinkA=0, shrinkB=0, connectionstyle=f"arc3,rad={rad}", zorder=3)
    ax.add_patch(a)


def elbow(ax, pts, color=INK, lw=0.8, ls="-"):
    """折线箭头：pts 为折点序列，最后一段带箭头。"""
    for a, b in zip(pts[:-2], pts[1:-1]):
        ax.plot([a[0], b[0]], [a[1], b[1]], color=color, lw=lw, ls=ls, zorder=3)
    arr(ax, pts[-2], pts[-1], color=color, lw=lw, ls=ls)


# ------------------------------------------------------------------ 图 1-1 硬件结构
def hardware():
    W, H = 15.6, 9.0
    fig, ax = canvas(W, H)
    cw, gap, x0 = 4.45, 0.35, 0.35
    xs = [x0, x0 + cw + gap, W - 0.35 - cw]
    names = ["AI Core 0", "AI Core 1", r"AI Core $N\!-\!1$"]
    ytop, ch = 8.8, 5.0
    for x, nm in zip(xs, names):
        tbox(ax, x, ytop - ch, cw, ch, title=nm)
        # 计算单元
        hw = (cw - 0.45) / 2
        ax.text(x + 0.15, ytop - 0.9, "计算单元", fontsize=7.5, color=SUBINK, va="center")
        tbox(ax, x + 0.15, ytop - 2.0, hw, 0.85, "Cube 矩阵\nPIPE_M", fs=7.5, wrap_=False)
        tbox(ax, x + 0.3 + hw, ytop - 2.0, hw, 0.85, "Vector 向量\nPIPE_V", fs=7.5, wrap_=False)
        ax.text(x + 0.15, ytop - 2.3, "搬运单元", fontsize=7.5, color=SUBINK, va="center")
        tbox(ax, x + 0.15, ytop - 3.35, cw - 0.3, 0.85, "PIPE_MTE2\nDDR→L1/UB，UB→L1", fs=7.5, wrap_=False)
        tbox(ax, x + 0.15, ytop - 4.3, cw - 0.3, 0.85, "PIPE_MTE3\nL1/UB→DDR，L1→UB", fs=7.5, wrap_=False)
        tbox(ax, x + 0.15, ytop - 4.9, hw, 0.5, "L1  512 KB", fs=7.5, wrap_=False)
        tbox(ax, x + 0.3 + hw, ytop - 4.9, hw, 0.5, "UB  128 KB", fs=7.5, wrap_=False)
    ax.text((xs[1] + cw + xs[2]) / 2, ytop - ch / 2, "…", ha="center", va="center", fontsize=16, color=INK)
    # 总线
    ybus = ytop - ch - 0.45
    ax.plot([xs[0] + cw / 2, xs[2] + cw / 2], [ybus, ybus], color=INK, lw=0.8)
    for x in xs:
        ax.plot([x + cw / 2, x + cw / 2], [ytop - ch, ybus], color=INK, lw=0.8)
    # L2（仅问题三）
    group(ax, 0.35, 1.55, W - 0.7, 1.3)
    ax.text(W / 2, 2.38, "共享只读 L2 Cache（仅问题三）", ha="center", va="center", fontsize=FS_T, fontweight="bold")
    ax.text(W / 2, 1.9, "容量 1 MB，带宽 250 B/cycle，FIFO 淘汰，带宽与 DDR 相互独立", ha="center", va="center",
            fontsize=8.5)
    arr(ax, (W / 2, ybus), (W / 2, 2.85), both=True)
    tbox(ax, 0.35, 0.2, W - 0.7, 1.0, "共享片外主存 DDR：所有核心公平共享 60 B/cycle 总带宽；问题一、二中各核直接访问 DDR", fs=8.5)
    arr(ax, (W / 2, 1.55), (W / 2, 1.2), both=True)
    figstyle.save(fig, "fig_hardware")


# ------------------------------------------------------------------ 图 1-2 权衡关系
def tradeoff():
    """中间为三项决策，四周为三种效应；实线双箭头表示决策影响效应，虚线连接此消彼长的两种效应。"""
    W, H = 15.6, 8.6
    fig, ax = canvas(W, H)
    cx = W / 2
    GREY_LN = "#8C8C8C"
    top = (cx - 3.6, 6.55, 7.2, 1.75)          # 多核并行度
    mid = (cx - 3.0, 3.45, 6.0, 2.1)           # 三项联合决策
    lft = (0.3, 0.3, 5.3, 2.6)                 # 通信与同步开销
    rgt = (W - 5.6, 0.3, 5.3, 2.6)             # 片上缓存复用
    tbox(ax, *mid, "切图：子图粒度与边界\n分核：子图到核心的映射\n同核排序：各核子图的执行次序",
         title="三项联合决策")
    tbox(ax, *top, "子图数量与粒度决定可并行的任务规模；核间负载越均衡，Makespan 越容易下降",
         title="多核并行度")
    tbox(ax, *lft, "跨核依赖要经 COPY_OUT、同步与 COPY_IN；场景 A 中子图边界都经 DDR 中转",
         title="通信与同步开销")
    tbox(ax, *rgt, "L1/UB 容量有限；同核复用减少读写，容量不足时触发换入换出", title="片上缓存复用")
    # 决策 → 三种效应
    arr(ax, (cx, mid[1] + mid[3]), (cx, top[1]), both=True)
    arr(ax, (cx - 1.8, mid[1]), (lft[0] + lft[2] - 1.2, lft[1] + lft[3]), both=True)
    arr(ax, (cx + 1.8, mid[1]), (rgt[0] + 1.2, rgt[1] + rgt[3]), both=True)
    # 此消彼长的效应之间用虚线相连，并在线旁注明关系
    dash = dict(color=GREY_LN, lw=0.8, ls=(0, (4, 2)), zorder=1)
    yl = top[1] + top[3] / 2
    xl, xr = lft[0] + 1.0, rgt[0] + rgt[2] - 1.0
    ax.plot([top[0], xl, xl], [yl, yl, lft[1] + lft[3]], **dash)
    ax.plot([top[0] + top[2], xr, xr], [yl, yl, rgt[1] + rgt[3]], **dash)
    ax.plot([lft[0] + lft[2], rgt[0]], [1.6, 1.6], **dash)
    for x_, y_ in ((top[0], yl), (xl, lft[1] + lft[3]), (top[0] + top[2], yl), (xr, rgt[1] + rgt[3]),
                   (lft[0] + lft[2], 1.6), (rgt[0], 1.6)):
        ax.plot([x_], [y_], "o", ms=2.6, color=GREY_LN, zorder=1.5)
    rtext(ax, xl + 0.2, 5.25, "切得越细\n并行度↑\n通信与同步↑", fs=8.5, align="left", color=SUBINK)
    rtext(ax, xr - 0.2, 5.25, "切得越粗\n缓存复用↑\n并行空间↓", fs=8.5, align="right", color=SUBINK)
    rtext(ax, cx, 1.78, "同核聚合：通信↓，复用↑", fs=8.5, va="bottom", color=SUBINK)
    rtext(ax, cx, 1.42, "但负载失衡、缓存压力↑", fs=8.5, va="top", color=SUBINK)
    figstyle.save(fig, "fig_tradeoff")


# ------------------------------------------------------------------ 图 1-3 技术路线
def roadmap():
    rows = [
        ("问题分析", 2.6, [("评估规则分析", "边界重建、核内执行次序、发射次序、换出与 Cache 命中规则"),
                         ("测试数据特征", "规模、深度、连通分量与缓存压力"),
                         ("难点归纳", "粒度折中、跨核等待、片上驻留与重复读取")]),
        ("模型准备", 2.6, [("统一优化模型", "决策 $x$、$y$、$\\pi$，约束（C1）～（C9），字典序目标"),
                         ("跨核同步层次", "$r(v)$ 与（核心，层次）子图，结构约束由构造满足"),
                         ("性能下界", "Cube、Vector、DDR 与关键路径下界")]),
        ("模型求解", 2.6, [("问题一（场景 A）", "Task 级时序模型，粒度折中，CAP-LS 与模拟退火"),
                         ("问题二（场景 B）", "$(\\lambda-1)$ 超图割，单算子子图与容量感知表调度"),
                         ("问题三（场景 B + L2）", "命中来源与时序条件，Cache 感知分配代价，两种配置对比")]),
        ("检验评价", 2.2, [("对比与消融", "四类基线配对检验与事后消融"),
                         ("灵敏度", "粒度参数与硬件参数"),
                         ("可靠性", "下界差距、代理排序能力、结构特征与难例")]),
    ]
    W, LW, vg = 15.6, 1.3, 0.55
    H = sum(r[1] for r in rows) + vg * (len(rows) - 1) + 0.3
    fig, ax = canvas(W, H)
    x0 = 0.3 + LW + 0.25
    gw = W - x0 - 0.3
    ytop = H - 0.15
    for k, (name, h, items) in enumerate(rows):
        y = ytop - h
        tbox(ax, 0.3, y, LW, h, "\n".join(name), fs=FS_T, wrap_=False)
        group(ax, x0, y, gw, h)
        n = len(items)
        bw = (gw - 0.3 * (n + 1)) / n
        for i, (t, b) in enumerate(items):
            bx = x0 + 0.3 + i * (bw + 0.3)
            tbox(ax, bx, y + 0.18, bw, h - 0.36, b, title=t, fs=8.5)
            if i < n - 1 and name == "模型准备":
                arr(ax, (bx + bw, y + h / 2), (bx + bw + 0.3, y + h / 2))
        if k < len(rows) - 1:
            arr(ax, (x0 + gw / 2, y), (x0 + gw / 2, y - vg))
        ytop = y - vg
    figstyle.save(fig, "fig_roadmap")


# ------------------------------------------------------------------ CAP-LS 框架
def framework():
    W, H = 15.6, 8.0
    fig, ax = canvas(W, H)
    group(ax, 0.25, 3.9, W - 0.5, 3.85, "对候选网格中的每组参数构造一个方案")
    bw, gap = 3.45, 0.35
    xs = [0.45 + i * (bw + gap) for i in range(4)]
    items = [("S1 无环切块", "按扇出阈值 $\\theta$ 亲和原子化，合并强连通分量，沿线性扩展 $\\sigma$ 切成连续块"),
             ("S2 核心分配", "LPT、轮转或连续段初始分配，按代理 $F$ 做块级换核局部搜索"),
             ("S3 分层成子图", "计算同步层次 $r(v)$，取（核心，层次）等价类为子图并按层次、核心编号"),
             ("S4 评估择优", "评估程序计算 Makespan，结果按方案哈希缓存，补充搜索后取最小者")]
    for i, (x, (t, b)) in enumerate(zip(xs, items)):
        tbox(ax, x, 4.15, bw, 3.0, b, title=t, fs=8.5)
        if i < 3:
            arr(ax, (x + bw, 5.65), (x + bw + gap, 5.65))
    tbox(ax, 0.45, 2.3, 4.4, 1.0, "输入：计算图 $G$、核心数 $N$、问题编号", fs=8.5)
    arr(ax, (2.65, 3.3), (2.65, 4.15))
    tbox(ax, W - 4.85, 2.3, 4.4, 1.0, "输出：node_to_subgraph 与 core_schedules", fs=8.5)
    arr(ax, (xs[3] + bw / 2, 4.15), (xs[3] + bw / 2, 3.3))
    cols = [("问题一", "Task = 子图；$\\omega=1000$；c0～c13 + 模拟退火"),
            ("问题二", "Task = 核心；$\\omega=500$；另加单算子子图与表调度、优先级采样"),
            ("问题三", "同问题二；分配代价按预测命中字节折算")]
    cw = (W - 0.9 - 0.5) / 3
    for i, (t, b) in enumerate(cols):
        tbox(ax, 0.45 + i * (cw + 0.25), 0.2, cw, 1.7, b, title=t, fs=8.5)
    figstyle.save(fig, "fig_framework")


# ------------------------------------------------------------------ 三个问题的求解流程
def flow(name, steps, notes, ncol, fs=8.5, fsn=8.0):
    """网格式流程图：各步按行从左到右排列，换行处用折线箭头连接。
    每个框上部为步骤名，中部为做法，框内虚线以下（灰字）为该步的性质或说明。"""
    W = 15.6
    mx, gx, gy = 0.12, 0.5, 0.8
    bw = (W - 2 * mx - (ncol - 1) * gx) / ncol
    tw = bw - 0.5
    th = 0.6
    lhb, lhn = fs * 1.42 * PT, fsn * 1.42 * PT
    nb = max(nlines(b, tw, fs) for _, b in steps)
    nn = max((nlines(t, tw, fsn) for t in notes.values()), default=0)
    body_h = nb * lhb + 0.3
    note_h = nn * lhn + 0.26 if notes else 0.0
    bh = th + body_h + note_h
    nrow = math.ceil(len(steps) / ncol)
    H = nrow * bh + (nrow - 1) * gy + 0.3
    fig, ax = canvas(W, H)
    pos = []
    for i, (t, b) in enumerate(steps):
        r, c = divmod(i, ncol)
        x = mx + c * (bw + gx)
        y = H - 0.15 - (r + 1) * bh - r * gy
        rect(ax, x, y, bw, bh)
        ax.text(x + bw / 2, y + bh - th / 2, t, ha="center", va="center", fontsize=fs + 0.5, fontweight="bold",
                color=INK, zorder=4)
        ax.plot([x, x + bw], [y + bh - th] * 2, color=INK, lw=0.5, zorder=3)
        if i in notes:
            yd = y + note_h
            ax.plot([x + 0.1, x + bw - 0.1], [yd, yd], color="#8C8C8C", lw=0.6, ls=(0, (3, 2)), zorder=3)
            rtext(ax, x + bw / 2, y + note_h / 2, notes[i], tw, fs=fsn, color=SUBINK)
            rtext(ax, x + bw / 2, (yd + y + bh - th) / 2, b, tw, fs=fs)
        else:
            rtext(ax, x + bw / 2, y + (bh - th) / 2, b, tw, fs=fs)
        pos.append((x, y))
    for i in range(len(steps) - 1):
        (x1, y1), (x2, y2) = pos[i], pos[i + 1]
        if abs(y1 - y2) < 1e-6:
            arr(ax, (x1 + bw, y1 + bh / 2), (x2, y2 + bh / 2))
        else:
            ym = y1 - gy / 2
            elbow(ax, [(x1 + bw / 2, y1), (x1 + bw / 2, ym), (x2 + bw / 2, ym), (x2 + bw / 2, y2 + bh)])
    figstyle.save(fig, name)


def flows():
    flow("fig_flow_p1", [
        ("S1 无环切块", "收缩 COPY 节点得到算子级 DAG；按扇出阈值亲和原子化，合并强连通分量，"
                       "沿 $\\sigma$ 切成计算量不超过 $\\beta W/N$ 的块"),
        ("S2 核心分配", "LPT、轮转或连续段初始分配，以代理 $F$（$\\omega=1000$）做块级局部搜索"),
        ("S3 分层成子图", "按同步层次把（核心，层次）等价类作为子图，每个子图即一个 Task"),
        ("S4 候选评估", "c0～c13 按图规模裁剪后交评估程序计算 Makespan"),
        ("模拟退火", "从评估第一名出发，以 Task 级时序模型为适应度，合并、拆分或迁移 Task"),
        ("输出", "在全部已评估候选中取 Makespan 最小者，写成规定格式的方案文件"),
    ], {0: "强连接张量的生产者与\u200b消费者进同一原子，块级商图无环",
        1: "代价计入 Cube、Vector 负载、搬入搬出字节与同步深度",
        2: "由性质 1，结构约束（C1）～（C5）自动满足",
        3: "评估耗时较长的 4 个大图先用代理预筛",
        4: "每步检查 Task 图无环；代理值前 3 的方案交评估程序"}, ncol=3)
    flow("fig_flow_p2", [
        ("场景 B 的执行模型", "同核子图并为一个 Task，同核边界不搬运；跨核经 COPY_OUT、500 cycle 同步与 COPY_IN"),
        ("S1～S2 核心分配", "沿用无环切块与联合分配，代理 $F$ 的同步权重 $\\omega=500$"),
        ("两类子图成形", "（核心，层次）等价类；或每个算子单独成子图、核内次序由容量感知表调度给出"),
        ("S4 候选评估", "c0～c17 共 18 组候选交评估程序，覆盖从每核约一个子图到每个算子一个子图"),
        ("优先级采样", "对评估第一名的单算子子图候选加 Gumbel 扰动采样 16 个，事件模拟代理排序后前 3 个交评估程序"),
        ("输出", "在全部已评估候选中取 Makespan 最小者，写成规定格式的方案文件"),
    ], {0: "单生产核中间张量与图输入张量的跨核搬运可写成 $(\\lambda-1)$ 超图割",
        2: "评分 = 向上秩 − 驻留增量 + 流水线交错 + 噪声；按层稳定排序后性质 1 仍成立",
        4: "采样只改变核内次序，不改变分核"}, ncol=3)
    flow("fig_flow_p3", [
        ("L2 命中规则", "只读、FIFO；发射时判定命中，搬运完成时写入，命中不刷新顺序"),
        ("命中来源与复用度", "命中只来自多核重复读入与同核再次读入；定义复用度与 Cache 价值"),
        ("Cache 感知代价", "预测命中字节按 250 B/cycle 折算进 PIPE_MTE2 占用与 DDR 下界"),
        ("CAP-LS 求解", "候选网格、表调度与采样同问题二，由问题三的评估程序择优"),
        ("两种配置对比", "各自择优比较：两种配置各自求解；纯 L2 收益：同一方案在两种配置下评估"),
        ("机理与灵敏度", "拆分命中与未命中来源；L2 容量、带宽灵敏度（18 个用例子集）"),
    ], {1: "给出命中字节上界与后续读取命中的时序条件",
        2: "重复读取的代价按预测命中下调",
        4: "输出 1～5 核对比曲线与相同核数下的加速比"}, ncol=3)


# ------------------------------------------------------------------ 图 5-2 场景 A 的 Task 时序
def task_timeline():
    """两核示例。s1→s4、s4→s5 为跨核依赖；各 Task 的开始时刻按式 (5-4)(5-5) 取三个释放时刻的最大值。"""
    W, H = 14.0, 5.1
    fig, ax = canvas(W, H)
    x0, k = 1.35, 1.36                      # 时间原点与每单位时间的长度（cm）
    X = lambda t: x0 + k * t                # noqa: E731
    Ws, Wc = 0.35, 0.9                      # 示意用的 W_same、W_cross（与真实比例无关）
    yc = {0: 3.35, 1: 1.95}                 # 两条泳道的中心高度
    hh = 0.36                               # 半条高
    fill = {0: "#DCE2EE", 1: "#FADBD5"}
    edge = {0: figstyle.C1, 1: figstyle.C2}
    tasks = {"s_1": (0, 0.4, 3.0), "s_3": (0, 3.0 + Ws, 5.3), "s_5": (0, 6.3 + Wc, 8.9),
             "s_2": (1, 0.4, 2.3), "s_4": (1, 3.0 + Wc, 6.3), "s_6": (1, 6.3 + Ws, 8.0)}
    # 空闲区：核 0 在 s3 结束后等待跨核前驱 s4
    ax.add_patch(Rectangle((X(5.3), yc[0] - hh), X(6.3 + Wc) - X(5.3), 2 * hh, fc="white", ec="#9A9A9A",
                           lw=0.5, hatch="////", zorder=1))
    for nm, (c, a, e) in tasks.items():
        ax.add_patch(Rectangle((X(a), yc[c] - hh), X(e) - X(a), 2 * hh, fc=fill[c], ec=edge[c], lw=0.9, zorder=2))
        ax.text((X(a) + X(e)) / 2, yc[c], f"${nm}$", ha="center", va="center", fontsize=10, zorder=3)
    for c in (0, 1):
        rtext(ax, 0.15, yc[c], f"核 {c}", fs=9.5, align="left")
    # 同核切换等待 W_same（尺寸线）
    def dim(t1, t2, y, label, color=INK, above=True):
        ax.add_patch(FancyArrowPatch((X(t1), y), (X(t2), y), arrowstyle="<|-|>", mutation_scale=5, lw=0.6,
                                     color=color, shrinkA=0, shrinkB=0, zorder=4))
        for t in (t1, t2):
            ax.plot([X(t), X(t)], [y - 0.1, y + 0.1], color=color, lw=0.6, zorder=4)
        ax.text((X(t1) + X(t2)) / 2, y + (0.12 if above else -0.12), label, ha="center",
                va="bottom" if above else "top", fontsize=8.5, color=color, zorder=4)
    dim(3.0, 3.0 + Ws, yc[0] + hh + 0.22, r"$W_{\mathrm{same}}$")
    dim(6.3, 6.3 + Ws, yc[1] - hh - 0.22, r"$W_{\mathrm{same}}$", above=False)
    # 跨核依赖：前驱结束 → 后继开始，水平跨度即 W_cross
    red = figstyle.RED
    for (t1, c1), (t2, c2), lab_dx in (((3.0, 0), (3.0 + Wc, 1), -0.1), ((6.3, 1), (6.3 + Wc, 0), 0.22)):
        y1 = yc[c1] - hh if c1 == 0 else yc[c1] + hh
        y2 = yc[c2] + hh if c2 == 1 else yc[c2] - hh
        ax.add_patch(FancyArrowPatch((X(t1), y1), (X(t2), y2), arrowstyle="-|>", mutation_scale=7, lw=0.9,
                                     color=red, ls=(0, (3, 2)), shrinkA=0, shrinkB=0, zorder=4))
        ax.text((X(t1) + X(t2)) / 2 + lab_dx, (y1 + y2) / 2 - (0.04 if lab_dx > 0 else 0), r"$W_{\mathrm{cross}}$",
                color=red, fontsize=8.5, ha="right" if lab_dx < 0 else "left", va="center", zorder=4)
    # 时间轴
    ya = 0.45
    arr(ax, (x0 - 0.1, ya), (W - 1.0, ya), lw=0.7)
    rtext(ax, W - 0.9, ya, "时间", fs=8.5, align="left")
    # 图例
    lx, ly = X(4.6), H - 0.32
    ax.add_patch(FancyArrowPatch((lx, ly), (lx + 0.8, ly), arrowstyle="-|>", mutation_scale=7, lw=0.9, color=red,
                                 ls=(0, (3, 2)), shrinkA=0, shrinkB=0))
    rtext(ax, lx + 0.95, ly, "跨核依赖", fs=8.5, align="left")
    lx2 = lx + 3.0
    ax.add_patch(Rectangle((lx2, ly - 0.17), 0.8, 0.34, fc="white", ec="#9A9A9A", lw=0.5, hatch="////"))
    rtext(ax, lx2 + 0.95, ly, "核心空闲（等待跨核前驱）", fs=8.5, align="left")
    figstyle.save(fig, "fig_task_timeline")


if __name__ == "__main__":
    figstyle.use_sans()
    hardware()
    tradeoff()
    roadmap()
    framework()
    flows()
    legacy.stall_mechanism()
    legacy.levels_sketch()
    task_timeline()
