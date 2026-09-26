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
        txt = wrap(body, w - 0.35, fs) if wrap_ else body
        tx = x + w / 2 if align == "center" else x + 0.18
        ax.text(tx, (y + top) / 2, txt, ha=align, va="center", fontsize=fs, color=INK, linespacing=1.4,
                zorder=z + 1)


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
    names = ["AI Core 0", "AI Core 1", "AI Core N−1"]
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
    W, H = 15.6, 8.4
    fig, ax = canvas(W, H)
    cx = W / 2
    tbox(ax, cx - 3.0, 3.4, 6.0, 2.1, "切图：子图粒度与边界\n分核：子图到核心的映射\n同核排序：各核子图的执行次序",
         title="三项联合决策")
    tbox(ax, cx - 3.6, 6.4, 7.2, 1.75, "子图数量与粒度决定可并行的任务规模；\n核间负载越均衡，Makespan 越容易下降",
         title="多核并行度")
    tbox(ax, 0.3, 0.45, 5.3, 2.6, "跨核依赖要经 COPY_OUT、同步与 COPY_IN；场景 A 中子图边界都经 DDR 中转",
         title="通信与同步开销")
    tbox(ax, W - 5.6, 0.45, 5.3, 2.6, "L1/UB 容量有限；同核复用减少读写，容量不足时触发换入换出",
         title="片上缓存复用")
    arr(ax, (cx, 5.5), (cx, 6.4), both=True)
    arr(ax, (cx - 1.8, 3.4), (2.95, 3.05), both=True)
    arr(ax, (cx + 1.8, 3.4), (W - 2.95, 3.05), both=True)
    ax.plot([5.6, W - 5.6], [1.8, 1.8], color="#8C8C8C", lw=0.8, ls=(0, (4, 2)))
    ax.text(cx, 1.95, "同核聚合：通信↓，复用↑", ha="center", va="bottom", fontsize=8)
    ax.text(cx, 1.65, "但负载失衡、缓存压力↑", ha="center", va="top", fontsize=8)
    ax.text(2.1, 5.0, "切得越细：并行↑\n边界与同步↑", ha="center", va="center", fontsize=8, color=SUBINK)
    ax.text(W - 2.1, 5.0, "切得越粗：复用↑\n并行空间↓", ha="center", va="center", fontsize=8, color=SUBINK)
    figstyle.save(fig, "fig_tradeoff")


# ------------------------------------------------------------------ 图 1-3 技术路线
def roadmap():
    rows = [
        ("问题分析", 2.2, [("评估规则分析", "边界重建、核内执行次序、发射次序、换出与 Cache 命中规则"),
                         ("测试数据特征", "规模、深度、连通分量与缓存压力"),
                         ("难点归纳", "粒度折中、跨核等待、片上驻留与重复读取")]),
        ("模型准备", 2.2, [("统一优化模型", "决策 x、y、π，约束（C1）～（C9），字典序目标"),
                         ("跨核同步层次", "r(v) 与（核心，层次）子图，结构约束由构造满足"),
                         ("性能下界", "Cube、Vector、DDR 与关键路径下界")]),
        ("模型求解", 2.6, [("问题一（场景 A）", "Task 级时序模型，粒度折中，CAP-LS 与模拟退火"),
                         ("问题二（场景 B）", "(λ−1) 超图割，单算子子图与容量感知表调度"),
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
    items = [("S1 无环切块", "按扇出阈值 θ 亲和原子化，合并强连通分量，沿线性扩展 σ 切成连续块"),
             ("S2 核心分配", "LPT、轮转或连续段初始分配，按代理 F 做块级换核局部搜索"),
             ("S3 分层成子图", "计算同步层次 r(v)，取（核心，层次）等价类为子图并按层次、核心编号"),
             ("S4 评估择优", "评估程序计算 Makespan，结果按方案哈希缓存，补充搜索后取最小者")]
    for i, (x, (t, b)) in enumerate(zip(xs, items)):
        tbox(ax, x, 4.15, bw, 3.0, b, title=t, fs=8.5)
        if i < 3:
            arr(ax, (x + bw, 5.65), (x + bw + gap, 5.65))
    tbox(ax, 0.45, 2.3, 4.4, 1.0, "输入：计算图 G、核心数 N、问题编号", fs=8.5)
    arr(ax, (2.65, 3.3), (2.65, 4.15))
    tbox(ax, W - 4.85, 2.3, 4.4, 1.0, "输出：node_to_subgraph 与 core_schedules", fs=8.5)
    arr(ax, (xs[3] + bw / 2, 4.15), (xs[3] + bw / 2, 3.3))
    cols = [("问题一", "Task = 子图；ω = 1000；c0～c13 + 模拟退火"),
            ("问题二", "Task = 核心；ω = 500；另加单算子子图与表调度、优先级采样"),
            ("问题三", "同问题二；分配代价按预测命中字节折算")]
    cw = (W - 0.9 - 0.5) / 3
    for i, (t, b) in enumerate(cols):
        tbox(ax, 0.45 + i * (cw + 0.25), 0.2, cw, 1.7, b, title=t, fs=8.5)
    figstyle.save(fig, "fig_framework")


# ------------------------------------------------------------------ 三个问题的求解流程
def flow(name, steps, notes):
    W = 15.6
    bh, gap = 1.75, 0.45
    H = len(steps) * bh + (len(steps) - 1) * gap + 0.4
    fig, ax = canvas(W, H)
    bx, bw = 0.3, 8.6
    nx, nw = 9.6, W - 9.6 - 0.3
    for i, (t, b) in enumerate(steps):
        y = H - 0.2 - (i + 1) * bh - i * gap
        tbox(ax, bx, y, bw, bh, b, title=t, fs=8.5)
        if i < len(steps) - 1:
            arr(ax, (bx + bw / 2, y), (bx + bw / 2, y - gap))
        if i in notes:
            tbox(ax, nx, y + 0.12, nw, bh - 0.24, notes[i], fs=8.3, ls=(0, (4, 2)), align="left")
            ax.plot([bx + bw, nx], [y + bh / 2, y + bh / 2], color="#8C8C8C", lw=0.7, ls=(0, (4, 2)))
    figstyle.save(fig, name)


def flows():
    flow("fig_flow_p1", [
        ("读图与预处理", "读入计算图与固定配置，收缩 COPY 节点得到算子级 DAG"),
        ("S1 无环切块", "按扇出阈值亲和原子化，合并强连通分量，沿 σ 切成计算量不超过 βW/N 的块"),
        ("S2 核心分配", "LPT、轮转或连续段初始分配，以代理 F（ω = 1000）做块级局部搜索"),
        ("S3 分层成子图", "按同步层次把（核心，层次）等价类作为子图，每个子图即一个 Task"),
        ("S4 候选评估", "c0～c13 按图规模裁剪后交评估程序；4 个评估最慢的大图先用代理预筛"),
        ("模拟退火", "从最优候选出发，以 Task 级时序模型为适应度，合并、拆分、迁移 Task"),
        ("输出", "全部已评估候选中 Makespan 最小者，写成规定格式的方案文件"),
    ], {1: "强连接张量的生产者与消费者进同一原子，块级商图无环",
        2: "代价同时计入 Cube、Vector 负载、搬入搬出字节与同步深度",
        3: "由性质 1，结构约束（C1）～（C5）自动满足",
        5: "每步检查 Task 图无环；代理最好的 3 个方案交评估程序"})
    flow("fig_flow_p2", [
        ("场景 B 的执行模型", "同核子图并为一个 Task，同核边界不搬运；跨核经 COPY_OUT、500 cycle 同步与 COPY_IN"),
        ("S1～S2 核心分配", "沿用无环切块与联合分配，代理 F 的同步权重 ω = 500"),
        ("两类子图成形", "（核心，层次）等价类；或每个算子单独成子图、核内次序由容量感知表调度给出"),
        ("S4 候选评估", "c0～c17 共 18 组候选交评估程序，覆盖从每核约一个子图到每个算子一个子图"),
        ("优先级采样", "对最优单算子子图候选加 Gumbel 扰动采样 16 个，事件模拟代理排序后前 3 个交评估程序"),
        ("输出", "全部已评估候选中 Makespan 最小者"),
    ], {0: "单生产核中间张量与图输入张量的跨核搬运可写成 (λ−1) 超图割",
        2: "评分 = 向上秩 − 驻留增量 + 流水线交错 + 噪声；按层稳定排序后性质 1 仍成立",
        4: "采样只改变核内次序，不改变分核"})
    flow("fig_flow_p3", [
        ("L2 命中规则", "只读、FIFO；发射时判定命中，搬运完成时写入，命中不刷新顺序"),
        ("命中来源与复用度", "命中只来自多核重复读入与同核再次读入；定义复用度与 Cache 价值"),
        ("Cache 感知代价", "预测命中字节按 250 B/cycle 折算进 PIPE_MTE2 占用与 DDR 下界"),
        ("CAP-LS 求解", "候选网格、表调度与采样同问题二，由问题三的评估程序择优"),
        ("两种配置对比", "配置最优比较：各自求解；纯 L2 收益：同一方案在两种配置下评估"),
        ("机理与灵敏度", "命中与未命中来源拆分；L2 容量、带宽灵敏度（18 个用例子集）"),
    ], {1: "给出命中字节上界与后续读取命中的时序条件",
        2: "重复读取的代价按预测命中下调",
        4: "输出 1～5 核对比曲线与相同核数下的加速比"})


if __name__ == "__main__":
    figstyle.use_sans()
    hardware()
    tradeoff()
    roadmap()
    framework()
    flows()
    legacy.stall_mechanism()
    legacy.levels_sketch()
    legacy.task_timeline()
