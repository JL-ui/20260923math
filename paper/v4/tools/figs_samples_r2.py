"""第二轮图表样张：换风格（蓝色单色系、Nature 式森林图）与新图型（三维散点、云雨图、桑基图）。

    python paper/v4/tools/figs_samples_r2.py [名字片段 ...]

数据与 figs_data_v4.py 相同，全部来自评估程序的输出；输出到 figures/v4/_samples/（不进论文）。
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import PathPatch, Rectangle
from matplotlib.path import Path as MPath
from scipy.stats import gaussian_kde

sys.path.insert(0, str(Path(__file__).resolve().parent))
import figs_data_v4 as fd  # noqa: E402
import figstyle_v4  # noqa: E402

from figs_data_v4 import (C1, C2, C3, CASES, CM, DARK, GREY, NS, PCOL, PNAME, R, RED, S, feats, rj, save, sp)  # noqa: E402

figstyle_v4.OUT = fd.ROOT / "figures" / "v4" / "_samples"
figstyle_v4.OUT.mkdir(parents=True, exist_ok=True)

# 蓝色单色系：由浅到深，灰度打印时亮度单调
BLUES = LinearSegmentedColormap.from_list(
    "blues_mono", ["#F4F8FC", "#D6E4F2", "#A9C8E4", "#6FA3D0", "#3C78B4", "#1F4E8C", "#0B2A5B"])


# ------------------------------------------------------------------ 1. 热力图：蓝色单色系
# 分级色阶：效率集中在 0.8～1.1，等宽连续色阶在这一段区分不开，按分位附近的整数边界分 8 级
from matplotlib.colors import BoundaryNorm, ListedColormap  # noqa: E402

HEAT_EDGES = [0.0, 0.5, 0.7, 0.8, 0.9, 0.95, 1.0, 1.1, 2.0]
HEAT_CMAP = ListedColormap(["#F7FBFF", "#DEEBF7", "#C6DBEF", "#9ECAE1", "#6BAED6", "#4292C6", "#2171B5",
                            "#08306B"])
HEAT_NORM = BoundaryNorm(HEAT_EDGES, HEAT_CMAP.N)


def fig_heatmap_blue():
    order = feats.loc[CASES].sort_values("largest_component_frac").index
    fig, axes = plt.subplots(3, 1, figsize=(16 * CM, 8.2 * CM), sharex=True)
    for ax, p in zip(axes, (1, 2, 3)):
        M = np.array([[sp(p, n)[c] / n for c in order] for n in NS])
        im = ax.imshow(M, aspect="auto", cmap=HEAT_CMAP, norm=HEAT_NORM, interpolation="nearest")
        ax.set_yticks(range(4))
        ax.set_yticklabels([f"N={n}" for n in NS], fontsize=7)
        ax.set_ylabel(["问题一", "问题二", "问题三"][p - 1], fontsize=8, rotation=0, ha="right", va="center")
        ax.grid(False)
        for sp_ in ax.spines.values():
            sp_.set_visible(False)
    rho = feats.loc[order, "largest_component_frac"].values
    for thr in (0.2, 0.5):
        k = np.searchsorted(rho, thr)
        for ax in axes:
            ax.axvline(k - 0.5, color="#C0504D", lw=0.9, ls=(0, (3, 1.5)))
    k2, k5 = np.searchsorted(rho, 0.2), np.searchsorted(rho, 0.5)
    axes[-1].set_xticks([k2 / 2, (k2 + k5) / 2, (k5 + len(rho)) / 2])
    axes[-1].set_xticklabels([r"$\rho_{\max}<0.2$", r"$0.2\leq\rho_{\max}<0.5$", r"$\rho_{\max}\geq0.5$"],
                             fontsize=7.8)
    axes[-1].set_xlabel("100 个用例（按最大连通分量占比升序排列）")
    cb = fig.colorbar(im, ax=axes, fraction=0.025, pad=0.01, spacing="uniform", ticks=HEAT_EDGES[1:-1])
    cb.set_label("并行效率 = 加速比 / N", fontsize=7.8)
    cb.ax.set_yticklabels([f"{e:g}" for e in HEAT_EDGES[1:-1]])
    cb.ax.tick_params(labelsize=7)
    k1 = HEAT_EDGES.index(1.0)
    cb.ax.axhline(1.0, color="#C0504D", lw=1.2)
    save(fig, "heatmap_blue")


# ------------------------------------------------------------------ 2. 消融：Nature 式森林图（点 + 95% 置信区间）
ABL_ROWS = [("no_level_no_comm", "两者同时去掉"), ("no_level", "去掉同步层次分层"), ("no_comm", "去掉通信感知分块"),
            ("no_sync", "代价去掉同步深度项"), ("no_localsearch", "去掉局部搜索"), ("max_ops500", "子图至多 500 算子"),
            ("lvl_alap", "ALAP 填充层指派"), ("op_full", "单算子子图 + 表调度")]


def _abl_ci(B=2000, seed=0):
    """按用例整体重抽样（同一用例的 4 个核数一起抽），求平均加速比相对变化的 95% 置信区间。"""
    a = pd.read_csv(R / "ablation2.csv")
    a = a[a.feasible == True]  # noqa: E712
    rng = np.random.default_rng(seed)
    out = {}
    for p in (1, 2, 3):
        d = a[a.problem == p]
        base = d[d.variant == "full_c2"].set_index(["case", "num_cores"]).speedup
        for k, _ in ABL_ROWS:
            x = d[d.variant == k].set_index(["case", "num_cores"]).speedup
            if x.empty:
                continue
            j = x.index.intersection(base.index)
            xa = x[j].unstack().sort_index()
            xb = base[j].unstack().reindex(xa.index)
            A, Bm = xa.values, xb.values
            rel = np.nanmean(A) / np.nanmean(Bm) - 1
            idx = rng.integers(0, len(A), (B, len(A)))
            bs = np.array([np.nanmean(A[i]) / np.nanmean(Bm[i]) - 1 for i in idx])
            lo, hi = np.percentile(bs, [2.5, 97.5])
            ab = S["ablation2"][f"problem{p}"][k]["paired"]
            assert abs(ab["rel"] - rel) < 5e-4, (p, k, ab["rel"], rel)
            out[(p, k)] = (100 * rel, 100 * lo, 100 * hi, ab["p_holm"] < 0.05)
    return out


def fig_ablation_forest():
    ci = _abl_ci()
    fig, (a0, a1) = plt.subplots(1, 2, figsize=(15 * CM, 9.6 * CM), sharey=True,
                                 gridspec_kw=dict(width_ratios=[1, 3.2], wspace=0.05))
    n = len(ABL_ROWS)
    y0 = np.arange(n)[::-1].astype(float)
    off = {1: 0.24, 2: 0.0, 3: -0.24}
    for ax in (a0, a1):
        for i in range(n):
            if i % 2 == 0:
                ax.axhspan(y0[i] - 0.5, y0[i] + 0.5, color="#F3F5F8", lw=0, zorder=0)
        ax.grid(False)
        ax.tick_params(axis="y", length=0)
    for p in (1, 2, 3):
        for i, (k, _) in enumerate(ABL_ROWS):
            if (p, k) not in ci:
                continue
            m, lo, hi, sig = ci[(p, k)]
            yy = y0[i] + off[p]
            for ax in (a0, a1):
                ax.plot([lo, hi], [yy, yy], color=PCOL[p], lw=1.1, solid_capstyle="butt", zorder=3)
                ax.scatter([m], [yy], s=20, marker="o", zorder=4, lw=0.9, edgecolor=PCOL[p],
                           facecolor=PCOL[p] if sig else "white")
    a0.set_xlim(-64, -34)
    a1.set_xlim(-24, 5)
    a1.axvline(0, color=DARK, lw=0.8, zorder=2)
    for x in (-20, -10):
        a1.axvline(x, color="#DDDDDD", lw=0.6, zorder=1)
    a0.axvline(-40, color="#DDDDDD", lw=0.6, zorder=1)
    a0.axvline(-60, color="#DDDDDD", lw=0.6, zorder=1)
    a0.set_xticks([-60, -50, -40])
    a1.set_xticks([-20, -15, -10, -5, 0, 5])
    a0.spines["right"].set_visible(False)
    a1.spines["left"].set_visible(False)
    a1.tick_params(axis="y", left=False)
    a0.set_yticks(y0)
    a0.set_yticklabels([r[1] for r in ABL_ROWS], fontsize=8.2)
    a0.set_ylim(-0.6, n - 0.4)
    kw = dict(color=DARK, clip_on=False, lw=0.8)
    d = 0.012
    a0.plot((1 - d * 3, 1 + d * 3), (-d, d), transform=a0.transAxes, **kw)
    a1.plot((-d, d), (-d, d), transform=a1.transAxes, **kw)
    fig.supxlabel("相对基准配置 c2 的平均加速比变化 / %", fontsize=9, y=0.02)
    for p in (1, 2, 3):
        a1.scatter([], [], s=20, color=PCOL[p], label=PNAME[p])
    a1.scatter([], [], s=20, facecolor="white", edgecolor="#666666", lw=0.9, label="空心：Holm 校正后 p ≥ 0.05")
    a1.plot([], [], color="#666666", lw=1.1, label="横线：95% 置信区间（按用例重抽样）")
    a1.legend(loc="lower left", fontsize=7.2, bbox_to_anchor=(0.0, 0.0), handlelength=1.6, frameon=True,
              facecolor="white", edgecolor="none", framealpha=0.95)
    save(fig, "ablation_forest")


# ------------------------------------------------------------------ 3. 三维散点：加速比与两个结构特征
def fig_struct3d():
    f = feats.loc[CASES]
    x = f.largest_component_frac.values
    y = np.log10(f.cp_over_total.values)
    z = sp(2, 4).values
    fig = plt.figure(figsize=(13 * CM, 10 * CM))
    ax = fig.add_subplot(projection="3d")
    zmin = 0.0
    y0, y1 = np.floor(y.min() * 2) / 2, np.ceil(y.max() * 2) / 2
    for xi, yi, zi in zip(x, y, z):
        ax.plot([xi, xi], [yi, yi], [zmin, zi], color="#B8C4D6", lw=0.5, zorder=1)
    ax.scatter(x, y, np.full_like(z, zmin), s=6, color="#C9C9C9", depthshade=False, zorder=1)
    ax.scatter(x, y, z, c=z, cmap=BLUES, vmin=0.2, vmax=6.5, s=18, edgecolor="#1F3552", lw=0.3,
               depthshade=False, zorder=3)
    xx, yy = np.meshgrid([0, 1], [y0, y1])
    ax.plot_surface(xx, yy, np.full_like(xx, 4.0), color="#C0504D", alpha=0.10, lw=0, shade=False)
    ax.plot([0, 1, 1], [y0, y0, y1], [4, 4, 4], color="#C0504D", lw=0.8, ls=(0, (3, 2)))
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(facecolor="#C0504D", alpha=0.18, edgecolor="#C0504D", ls=(0, (3, 2)), lw=0.8,
                             label="加速比 = 4 的平面（线性加速）")],
              loc="upper left", bbox_to_anchor=(0.02, 0.93), fontsize=7.6, frameon=False, handlelength=1.6)
    ax.set_xlim(0, 1)
    ax.set_ylim(y0, y1)
    ax.set_zlim(zmin, 7)
    yt = [t for t in (-3, -2, -1) if y0 <= t <= y1]
    ax.set_yticks(yt)
    ax.set_yticklabels([f"$10^{{{t}}}$" for t in yt])
    ax.set_xlabel("最大连通分量占比", labelpad=3)
    ax.set_ylabel("关键路径 / 总计算量", labelpad=5)
    ax.set_zlabel("问题二加速比（N=4）", labelpad=3)
    ax.tick_params(labelsize=7.4, pad=0)
    for a in (ax.xaxis, ax.yaxis, ax.zaxis):
        a.pane.set_facecolor("#FAFBFD")
        a.pane.set_edgecolor("#BBBBBB")
        a._axinfo["grid"].update(color="#E6E6E6", linewidth=0.5)
    ax.view_init(elev=20, azim=-60)
    ax.set_box_aspect((1.25, 1.0, 0.85), zoom=0.92)
    save(fig, "struct3d")


# ------------------------------------------------------------------ 4. 云雨图：半边小提琴 + 箱线 + 散点
def fig_dist_rain():
    fig, axes = plt.subplots(1, 3, figsize=(16 * CM, 6.6 * CM), sharey=True)
    rng = np.random.default_rng(1)
    for ax, p in zip(axes, (1, 2, 3)):
        col = PCOL[p]
        for n in NS:
            d = sp(p, n).values
            kde = gaussian_kde(d, bw_method=0.35)
            ys = np.linspace(d.min(), d.max(), 200)
            w = kde(ys)
            w = w / w.max() * 0.36
            ax.fill_betweenx(ys, n - 0.06 - w, n - 0.06, color=col, alpha=0.30, lw=0)
            ax.plot(n - 0.06 - w, ys, color=col, lw=0.7)
            q1, med, q3 = np.percentile(d, [25, 50, 75])
            ax.add_patch(Rectangle((n - 0.045, q1), 0.09, q3 - q1, facecolor="white", edgecolor=DARK, lw=0.7,
                                   zorder=4))
            ax.plot([n - 0.045, n + 0.045], [med, med], color=DARK, lw=1.2, zorder=5)
            jit = 0.10 + rng.uniform(0, 0.22, len(d))
            sup = d > n
            ax.scatter(n + jit[~sup], d[~sup], s=4, color=col, alpha=0.6, lw=0, zorder=3)
            ax.scatter(n + jit[sup], d[sup], s=5.5, color=RED, alpha=0.85, lw=0, zorder=3)
        ax.plot([1.45, 5.55], [1.45, 5.55], color="#444444", lw=0.9, ls=(0, (4, 2.5)), zorder=6)
        ax.set_xlim(1.45, 5.55)
        ax.set_title(PNAME[p], fontsize=9)
        ax.set_xticks(NS)
        ax.set_xlabel("核心数 N")
        ax.grid(axis="x", visible=False)
    axes[0].set_ylabel("逐用例加速比")
    axes[0].scatter([], [], s=9, color=RED, label="超线性（加速比 > N）")
    axes[0].plot([], [], color="#444444", lw=0.9, ls=(0, (4, 2.5)), label="线性加速（加速比 = N）")
    axes[0].legend(loc="upper left", fontsize=7.2, handlelength=2.4)
    fig.tight_layout(w_pad=0.6)
    save(fig, "dist_rain")


# ------------------------------------------------------------------ 5. 桑基图：L2 读取字节的去向（N=4）
def _band(ax, x0, x1, y0a, y0b, y1a, y1b, color, alpha=0.45):
    """从 x0 处的 [y0a, y0b] 平滑过渡到 x1 处的 [y1a, y1b]。"""
    xm = (x0 + x1) / 2
    verts = [(x0, y0a), (xm, y0a), (xm, y1a), (x1, y1a), (x1, y1b), (xm, y1b), (xm, y0b), (x0, y0b), (x0, y0a)]
    codes = [MPath.MOVETO, MPath.CURVE4, MPath.CURVE4, MPath.CURVE4, MPath.LINETO, MPath.CURVE4, MPath.CURVE4,
             MPath.CURVE4, MPath.CLOSEPOLY]
    ax.add_patch(PathPatch(MPath(verts, codes), facecolor=color, edgecolor="none", alpha=alpha))


def fig_l2_sankey():
    d = rj("l2_sources.json")["by_n"]["4"]
    mb = 1e6
    hit = [("图输入张量复读", d["hit_input_reuse"], "#00A087"), ("跨核中间张量", d["hit_cross_core_mid"], "#3C5488"),
           ("换出后再读", d["hit_spill_reload"], "#8491B4")]
    miss = [("首次读入（不可避免）", d["miss_first_miss"], "#9E9E9E"),
            ("并发首读", d["miss_concurrent_first_read"], "#F39B7F"),
            ("被 FIFO 淘汰后再读", d["miss_fifo_evicted"], "#E64B35")]
    H, M = d["official_hit_bytes"], d["official_miss_bytes"]
    T = H + M
    fig, ax = plt.subplots(figsize=(15.5 * CM, 8.0 * CM))
    ax.set_xlim(0, 10)
    ax.set_ylim(-0.1, 10.9)
    ax.axis("off")
    scale = 9.2 / T            # 纵向：字节 → 图上长度
    gap = 0.9
    nw = 0.28
    # 左：全部读取
    L0 = 0.3
    ax.add_patch(Rectangle((1.0, L0), nw, T * scale + gap, facecolor="#4D4D4D", lw=0))
    # 中：命中 / 未命中
    mh = (L0 + gap + M * scale, L0 + gap + T * scale)      # 命中段在上
    mm = (L0, L0 + M * scale)
    ax.add_patch(Rectangle((4.4, mh[0]), nw, H * scale, facecolor="#00A087", lw=0))
    ax.add_patch(Rectangle((4.4, mm[0]), nw, M * scale, facecolor="#C0504D", lw=0))
    # 左 → 中
    _band(ax, 1.0 + nw, 4.4, L0 + gap + M * scale, L0 + gap + T * scale, mh[0], mh[1], "#00A087", 0.30)
    _band(ax, 1.0 + nw, 4.4, L0, L0 + M * scale, mm[0], mm[1], "#C0504D", 0.22)
    # 右：来源（命中、未命中各自从上到下排）
    def right(items, y_top, mid, color_in):
        y = y_top
        src = mid[1]
        for lab, v, c in items:
            h = v * scale
            if h < 0.02:
                ax.text(7.95, y - 0.02, f"{lab}：{v / 1e3:.1f} KB（可忽略）", fontsize=7.4, va="top", color="#666666")
                y -= 0.35
                continue
            ax.add_patch(Rectangle((7.6, y - h), nw, h, facecolor=c, lw=0))
            _band(ax, 4.4 + nw, 7.6, src - h, src, y - h, y, c, 0.35)
            share = v / (H if items is hit else M)
            ax.text(7.95, y - h / 2, f"{lab}  {v / mb:.0f} MB（{share:.0%}）", fontsize=7.6, va="center")
            src -= h
            y -= h + 0.22
        return y
    right(hit, mh[1] + 0.35, mh, "#00A087")
    right(miss, mm[1] + 0.25, mm, "#C0504D")
    ax.text(0.9, L0 + (T * scale + gap) / 2, f"COPY_IN 读取\n{T / mb:.0f} MB", ha="right", va="center", fontsize=8)
    ax.text(4.3, (mh[0] + mh[1]) / 2, f"命中\n{H / mb:.0f} MB（{H / T:.1%}）", ha="right", va="center",
            fontsize=8, color="#00755F")
    ax.text(4.3, (mm[0] + mm[1]) / 2, f"未命中\n{M / mb:.0f} MB", ha="right", va="center", fontsize=8,
            color="#9C2F2A")
    save(fig, "l2_sankey")


ALL = {"heatmap_blue": fig_heatmap_blue, "ablation_forest": fig_ablation_forest, "struct3d": fig_struct3d,
       "dist_rain": fig_dist_rain, "l2_sankey": fig_l2_sankey}

if __name__ == "__main__":
    want = sys.argv[1:]
    for k, fn in ALL.items():
        if not want or any(w in k for w in want):
            fn()
