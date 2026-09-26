"""v3 数据图：由 solution/paper_v2/figs_data.py 复制而来，主结果改为“标准求解流程”口径。

    python paper/v3/tools/figs_data_v3.py            # 只重画依赖主结果的图
    python paper/v3/tools/figs_data_v3.py speedup    # 只画名字里含 speedup 的

与 v2 的差别：final 取 paper/v3/data/final_standard.csv（std_caliber.py 生成）；
加速比置信区间取 facts_v3.json；下界 CDF 按标准流程方案重算；图例措辞按 v3 术语修改。
输出到 figures/v3/。无 SimSun/Times New Roman 的环境用 Noto Serif CJK / Liberation Serif 代替。
"""

from __future__ import annotations

import json
import math
import sys

import matplotlib.pyplot as plt
import matplotlib.ticker as mt
import numpy as np
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import figstyle_v4  # noqa: E402,F401  必须先于 figstyle
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "solution" / "paper_v2"))
import figstyle  # noqa: E402
from figstyle import (C1, C2, C3, DARK, GREY, PCOL, PNAME, RED, ROOT, panel_label, save, use_serif)  # noqa: E402

figstyle.OUT = ROOT / "figures" / "v4"
figstyle.OUT.mkdir(parents=True, exist_ok=True)
R = ROOT / "results"
V3 = ROOT / "paper" / "v3" / "data"
use_serif()
CM = 1 / 2.54
NS = [2, 3, 4, 5]


def rj(name):
    return json.loads((R / name).read_text(encoding="utf-8"))


final = pd.read_csv(V3 / "final_standard.csv")
n1 = pd.read_csv(R / "n1.csv")
S = rj("summary.json")
_F3 = json.loads((V3 / "facts_v3.json").read_text(encoding="utf-8"))
for _p in (1, 2, 3):
    for _n in NS:
        _lo, _hi = _F3[f"P{_p}_CI_{_n}"].strip("[]").split(",")
        S[f"problem{_p}"]["speedup_ci"][str(_n)] = [float(_lo), float(_hi)]
feats = pd.DataFrame(rj("features.json")).set_index("case")
CASES = sorted(final["case"].unique())


def sp(p, n):
    if n == 1:
        d = n1[n1.problem == p].set_index("case")
        base = n1[n1.problem == 1].set_index("case")["makespan"]
        return (base / d["makespan"]).reindex(CASES)
    d = final[(final.problem == p) & (final.num_cores == n)].set_index("case")
    return d["speedup"].reindex(CASES)


def boot_ci(x, B=4000, seed=0):
    rng = np.random.default_rng(seed)
    x = np.asarray(x)
    m = rng.choice(x, (B, len(x))).mean(axis=1)
    return np.percentile(m, [2.5, 97.5])


# ------------------------------------------------------------------ 加速比折线（赛题要求的主图）
def fig_speedup(p):
    fig, ax = plt.subplots(figsize=(11.5 * CM, 7.6 * CM))
    xs = [1] + NS
    means, meds, lo, hi, mins, maxs = [], [], [], [], [], []
    for n in xs:
        v = sp(p, n).values
        means.append(v.mean())
        meds.append(np.median(v))
        if n == 1:
            lo.append(1)
            hi.append(1)
        else:
            a, b = S[f"problem{p}"]["speedup_ci"][str(n)]
            lo.append(a)
            hi.append(b)
        mins.append(v.min())
        maxs.append(v.max())
    col = PCOL[p]
    ax.plot([1, 5.3], [1, 5.3], color=GREY, lw=0.9, ls=(0, (4, 3)), label="理想线性加速 y = N", zorder=1)
    ax.fill_between(xs, mins, maxs, color=col, alpha=0.07, lw=0, label="逐用例范围", zorder=1)
    ax.fill_between(xs, lo, hi, color=col, alpha=0.25, lw=0, label="均值的 95% 置信区间", zorder=2)
    ax.plot(xs, meds, color=col, lw=1.1, ls=(0, (1.5, 1.5)), marker="s", ms=3.6, mfc="white",
            label="中位数", zorder=3)
    ax.plot(xs, means, color=col, lw=2.0, marker="o", ms=5.2, mec="white", mew=0.8,
            label="平均加速比（算术平均）", zorder=4)
    for x, m in zip(xs, means):
        if x == 1:
            continue
        ax.annotate(f"{m:.2f}", (x, m), textcoords="offset points", xytext=(7, -12), fontsize=8.2,
                    color=DARK)
    ax.set_xlim(0.8, 5.35)
    top = max(maxs) * 1.06
    ax.set_ylim(0.6, top)
    ax.set_xticks(xs)
    ax.set_xlabel("核心数 N")
    ax.set_ylabel("加速比")
    ax.legend(loc="upper left", fontsize=7.8, handlelength=2.2)
    save(fig, f"fig_speedup_p{p}")


# ------------------------------------------------------------------ 逐用例分布（云雨图：半边核密度 + 箱体 + 散点）
def fig_dist():
    from matplotlib.patches import Rectangle
    from scipy.stats import gaussian_kde
    fig, axes = plt.subplots(1, 3, figsize=(16 * CM, 6.6 * CM), sharey=True)
    rng = np.random.default_rng(1)
    for ax, p in zip(axes, (1, 2, 3)):
        col = PCOL[p]
        for n in NS:
            d = sp(p, n).values
            ys = np.linspace(d.min(), d.max(), 200)
            w = gaussian_kde(d, bw_method=0.35)(ys)
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
        # 线性加速参考线 y = N：贯通的斜虚线，置于其余元素之上
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
    save(fig, "fig_dist")


# ------------------------------------------------------------------ 数据集特征
def fig_features():
    f = feats.loc[CASES]
    fig, axes = plt.subplots(1, 3, figsize=(16 * CM, 5.6 * CM))
    ax = axes[0]
    bins = np.logspace(np.log10(f.n_ops.min() * 0.9), np.log10(f.n_ops.max() * 1.1), 18)
    ax.hist(f.n_ops, bins=bins, color=C1, alpha=0.8, edgecolor="white", lw=0.6)
    ax.set_xscale("log")
    ax.set_xlabel("算子数")
    ax.set_ylabel("用例数")
    ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
    panel_label(ax, "(a)")
    ax = axes[1]
    cp = f.critical_path_cycles / f.total_cycles
    s2 = sp(2, 4)
    scat = ax.scatter(f.largest_component_frac, cp, c=s2.values, cmap="viridis", s=14, edgecolor="white",
                      lw=0.3)
    ax.set_yscale("log")
    ax.set_xlabel("最大连通分量占比")
    ax.set_ylabel("关键路径 / 总计算量")
    cb = fig.colorbar(scat, ax=ax, fraction=0.05, pad=0.02)
    cb.set_label("问题二 N=4 加速比", fontsize=7.8)
    cb.ax.tick_params(labelsize=7.4)
    ax.axvline(0.5, color=GREY, lw=0.8, ls=(0, (3, 2)))
    panel_label(ax, "(b)")
    ax = axes[2]
    ub = f.ub_pressure.clip(lower=0.05)
    ax.hist(ub, bins=np.logspace(np.log10(0.05), np.log10(ub.max() * 1.1), 18), color=C2, alpha=0.8,
            edgecolor="white", lw=0.6)
    ax.set_xscale("log")
    ax.axvline(1, color=RED, lw=0.9, ls=(0, (3, 2)))
    ax.text(1.5, ax.get_ylim()[1] * 0.97, "容量上限", color=RED, fontsize=7.6, va="top")
    ax.set_xlabel("UB 张量总量 / UB 容量")
    ax.set_ylabel("用例数")
    panel_label(ax, "(c)")
    fig.tight_layout(w_pad=0.8)
    save(fig, "fig_features")


# ------------------------------------------------------------------ 求解时间
def fig_runtime():
    main = pd.read_csv(R / "main.csv")
    main = main[main.variant != "_best"].copy()
    main["tot"] = main.runtime_s.fillna(0) + main.eval_s.fillna(0)
    ann = {}
    for _, r in main[main.variant.str.startswith("sa")].iterrows():
        k = (r.case, r.problem, r.num_cores)
        if k not in ann:
            try:
                ann[k] = json.loads(r.params).get("anneal_seconds", 0)
            except Exception:
                ann[k] = 0
    g = main.groupby(["case", "problem", "num_cores"])["tot"].sum()
    for k, v in ann.items():
        g[k] += v
    fig, axes = plt.subplots(1, 2, figsize=(16 * CM, 6.2 * CM))
    ax = axes[0]
    for p in (1, 2, 3):
        v = np.sort(g.xs(p, level=1).values)
        ax.step(v, np.arange(1, len(v) + 1) / len(v), where="post", color=PCOL[p], lw=1.5,
                label=["问题一", "问题二", "问题三"][p - 1])
    for t, lab, off, ha in ((300, "5 min", 0.94, "right"), (600, "10 min", 1.06, "left")):
        ax.axvline(t, color=GREY, lw=0.8, ls=(0, (3, 2)))
        ax.text(t * off, 0.06, lab, fontsize=7.4, color="#555555", ha=ha)
    ax.set_xscale("log")
    ax.set_xlabel("单个（用例，N）的端到端求解时间 / s")
    ax.set_ylabel("累计比例")
    ax.legend(loc="upper left", fontsize=7.6, handlelength=1.6)
    panel_label(ax, "(a)")
    ax = axes[1]
    cand = main[(~main.variant.str.startswith(("sa", "s"))) | main.variant.str.match(r"^c\d+$")]
    cand = cand[cand.variant.str.match(r"^c\d+$")]
    x = cand.case.map(feats.n_ops)
    ax.scatter(x, cand.runtime_s.clip(lower=1e-3), s=3, color=C1, alpha=0.25, lw=0)
    # 按规模分箱的中位数
    bins = np.logspace(np.log10(x.min()), np.log10(x.max()), 12)
    idx = np.digitize(x, bins)
    med = [(np.sqrt(bins[i - 1] * bins[i]), cand.runtime_s[idx == i].median()) for i in range(1, len(bins))
           if (idx == i).sum() > 5]
    ax.plot([m[0] for m in med], [m[1] for m in med], color=RED, lw=1.6, marker="o", ms=3.5, label="分箱中位数")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("算子数")
    ax.set_ylabel("单候选 S1～S3 算法时间 / s")
    ax.legend(loc="upper left", fontsize=7.6)
    panel_label(ax, "(b)")
    fig.tight_layout(w_pad=1.0)
    save(fig, "fig_runtime")


# ------------------------------------------------------------------ 超线性来源
def fig_superlinear():
    """单核基准自身换入换出为 0 的用例单独放在左侧窄栏（横轴断开），其余用例按对数横轴排列。"""
    sc = rj("singlecore_baseline.json")
    spill = pd.Series({c: sc[c]["spill_added_copy_bytes"] for c in CASES})
    s = sp(2, 4)
    rho = feats.loc[CASES, "largest_component_frac"]
    cols = pd.Series(np.where(rho < 0.2, C1, np.where(rho < 0.5, C3, C2)), index=CASES)
    fig, (a0, a1) = plt.subplots(1, 2, figsize=(11.5 * CM, 7.0 * CM), sharey=True,
                                 gridspec_kw={"width_ratios": [1, 6.5], "wspace": 0.06})
    zero = spill <= 0
    rng = np.random.default_rng(3)
    jit = rng.uniform(-0.28, 0.28, zero.sum())
    a0.scatter(jit, s[zero], c=cols[zero], s=16, edgecolor="white", lw=0.4, zorder=3)
    a0.set_xlim(-0.6, 0.6)
    a0.set_xticks([0])
    a0.set_xticklabels(["0"])
    a1.scatter(spill[~zero], s[~zero], c=cols[~zero], s=16, edgecolor="white", lw=0.4, zorder=3)
    a1.set_xscale("log")
    a1.spines["left"].set_visible(False)
    a1.tick_params(axis="y", length=0)
    for ax in (a0, a1):
        ax.axhline(4, color=GREY, lw=0.9, ls=(0, (4, 3)), zorder=1)
    # 断轴记号
    d = 0.018
    kw = dict(color="#333333", lw=0.7, clip_on=False)
    a0.plot([1 - 0.1, 1 + 0.1], [-d * 3, d * 3], transform=a0.transAxes, **kw)
    a1.plot([-0.015, 0.015], [-d * 3, d * 3], transform=a1.transAxes, **kw)
    a0.set_ylabel("问题二 N=4 加速比")
    bb = a1.get_position()
    a1.set_xlabel("单核基准自身的换入换出字节数")
    a1.xaxis.set_label_coords((0.5 - bb.x0) / bb.width, -0.1)
    a0.set_title("无换入换出", fontsize=7.6, color="#555555")
    for c, lab in ((C1, r"$\rho_{\max}<0.2$"), (C3, r"$0.2\leq\rho_{\max}<0.5$"), (C2, r"$\rho_{\max}\geq0.5$")):
        a1.scatter([], [], c=c, s=16, label=lab)
    a1.plot([], [], color=GREY, lw=0.9, ls=(0, (4, 3)), label="加速比 = 核心数 4")
    a1.legend(loc="lower right", fontsize=7.2, ncol=2, handletextpad=0.3, columnspacing=1.0,
              borderaxespad=0.3, handlelength=1.8)
    save(fig, "fig_superlinear")


# ------------------------------------------------------------------ 额外搬运构成
def fig_traffic():
    sc = rj("singlecore_baseline.json")
    single = sum(sc[c]["spill_added_copy_bytes"] for c in CASES) / 1e9
    fig, ax = plt.subplots(figsize=(14 * CM, 6.2 * CM))
    xs, labels = [], []
    k = 0
    for p in (1, 2, 3):
        for n in NS:
            d = final[(final.problem == p) & (final.num_cores == n)]
            part = d.partition_added_copy_bytes.sum() / 1e9
            spl = d.spill_added_copy_bytes.sum() / 1e9
            ax.bar(k, part, color=PCOL[p], alpha=0.9, width=0.72, edgecolor="white", lw=0.5)
            ax.bar(k, spl, bottom=part, color=PCOL[p], alpha=0.38, width=0.72, edgecolor="white", lw=0.5,
                   hatch="////")
            xs.append(k)
            labels.append(f"N={n}")
            k += 1
        k += 0.6
    ax.axhline(single, color=RED, lw=1.0, ls=(0, (4, 3)))
    ax.text(len(xs) + 1.7, single + 0.03, f"单核基准自身换入换出 {single:.2f} GB", color=RED, fontsize=7.6,
            ha="right", va="bottom")
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, fontsize=7.8)
    for i, p in enumerate((1, 2, 3)):
        ax.text(i * 4.6 + 1.5, -0.33, PNAME[p], ha="center", va="top", fontsize=8.2, color=DARK,
                transform=ax.get_xaxis_transform() if False else ax.transData)
    ax.set_ylabel("100 个用例合计新增搬运 / GB")
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(facecolor="#777777", label="切分边界引入的搬运"),
                       Patch(facecolor="#BBBBBB", hatch="////", edgecolor="white", label="核内换入换出")],
              loc="upper right", fontsize=7.6, ncol=2)
    ax.set_ylim(-0.02, max(single, 1.8) * 1.12)
    ax.grid(axis="x", visible=False)
    fig.subplots_adjust(bottom=0.2)
    save(fig, "fig_traffic")


# ------------------------------------------------------------------ 问题三：两种配置
def fig_p3_compare():
    xs = [1] + NS
    no_l2, ro = [], []
    gain_final, gain_same, hit = [], [], []
    for n in xs:
        if n == 1:
            a = n1[n1.problem == 2].set_index("case").makespan.reindex(CASES)
            b = n1[n1.problem == 3].set_index("case").makespan.reindex(CASES)
            base = n1[n1.problem == 1].set_index("case").makespan.reindex(CASES)
            h = n1[n1.problem == 3].set_index("case").cache_hit_rate.reindex(CASES).fillna(0)
        else:
            a = final[(final.problem == 2) & (final.num_cores == n)].set_index("case").makespan.reindex(CASES)
            b = final[(final.problem == 3) & (final.num_cores == n)].set_index("case").makespan.reindex(CASES)
            base = final[(final.problem == 2) & (final.num_cores == n)].set_index("case").baseline_makespan.reindex(CASES)
            h = final[(final.problem == 3) & (final.num_cores == n)].set_index("case").cache_hit_rate.reindex(CASES).fillna(0)
        no_l2.append((base / a).mean())
        ro.append((base / b).mean())
        gain_final.append((a / b).mean())
        gain_same.append(S["l2_gain"][str(n)])
        hit.append(100 * h.mean())
    fig, axes = plt.subplots(1, 3, figsize=(16 * CM, 5.9 * CM))
    ax = axes[0]
    ax.plot([1, 5.2], [1, 5.2], color=GREY, lw=0.8, ls=(0, (4, 3)), label="加速比 = N")
    ax.plot(xs, no_l2, color=C2, marker="s", ms=4.2, lw=1.6, label="无 L2")
    ax.plot(xs, ro, color=C3, marker="o", ms=4.6, lw=1.6, label="只读 Cache")
    ax.annotate(f"{ro[-1]:.2f}", (5, ro[-1]), textcoords="offset points", xytext=(5, 3), fontsize=7.6,
                color=DARK, ha="left")
    ax.annotate(f"{no_l2[-1]:.2f}", (5, no_l2[-1]), textcoords="offset points", xytext=(5, -9), fontsize=7.6,
                color=DARK, ha="left")
    ax.set_xlim(0.7, 5.9)
    ax.set_xticks(xs)
    ax.set_xlabel("核心数 N")
    ax.set_ylabel("相对单核基准的平均加速比")
    ax.legend(loc="lower right", fontsize=7.6, bbox_to_anchor=(1.0, 0.02))
    panel_label(ax, "(a)")
    ax = axes[1]
    ax.plot(xs, gain_final, color=C1, marker="o", ms=4.6, lw=1.6, label="各自择优比较")
    ax.plot(xs, gain_same, color=C3, marker="^", ms=4.2, lw=1.1, ls=(0, (3, 2)), label="纯 L2 收益\n（同一方案）")
    ax.axhline(1, color=GREY, lw=0.8)
    ax.set_xticks(xs)
    ax.set_xlabel("核心数 N")
    ax.set_ylabel("Makespan 比（无 L2 / 只读 Cache）")
    ax.legend(loc="upper left", bbox_to_anchor=(0.0, 1.0), fontsize=7.6, handlelength=1.8)
    ax.set_ylim(0.995, max(max(gain_same), max(gain_final)) + 0.012)
    panel_label(ax, "(b)")
    ax = axes[2]
    ax.bar(xs, hit, color=C3, alpha=0.85, width=0.6, edgecolor="white")
    for x, h in zip(xs, hit):
        ax.text(x, h + 0.6, f"{h:.1f}%", ha="center", fontsize=7.6)
    ax.set_xticks(xs)
    ax.set_xlabel("核心数 N")
    ax.set_ylabel("按字节命中率 / %")
    ax.set_ylim(0, max(hit) * 1.28)
    ax.grid(axis="x", visible=False)
    panel_label(ax, "(c)")
    fig.tight_layout(w_pad=0.9)
    save(fig, "fig_p3_compare")


def fig_l2_case():
    fig, axes = plt.subplots(1, 2, figsize=(16 * CM, 6.0 * CM), sharey=True)
    for ax, n in zip(axes, (4, 5)):
        # 纯 L2 收益：同一方案（问题三标准流程方案）分别在问题二、三评估器下的 Makespan 之比
        pc = pd.read_csv(R / "p3_compare.csv")
        pc = pc[(pc.variant == "_best") & (pc.num_cores == n)]
        a = pc[pc.eval_problem == 2].set_index("case").makespan.reindex(CASES)
        b = final[(final.problem == 3) & (final.num_cores == n)].set_index("case")
        g = a / pc[pc.eval_problem == 3].set_index("case").makespan.reindex(CASES)
        h = 100 * b.cache_hit_rate.reindex(CASES).fillna(0)
        ax.scatter(h, g, s=16, color=C3, alpha=0.75, edgecolor="white", lw=0.4)
        ax.axhline(1.01, color=GREY, lw=0.8, ls=(0, (3, 2)))
        ax.axhline(1.0, color="#BBBBBB", lw=0.7)
        top = g.sort_values(ascending=False).head(3)
        for c, v in top.items():
            ax.annotate(c.replace("case_", ""), (h[c], v), textcoords="offset points", xytext=(4, 2), fontsize=7.2)
        ax.set_xlabel("只读 Cache 按字节命中率 / %")
        ax.set_title(f"N = {n}", fontsize=9)
    axes[0].set_ylabel("纯 L2 收益（同一方案 MK 比）")
    fig.tight_layout(w_pad=0.6)
    save(fig, "fig_l2_case")


def fig_l2_sources():
    d = rj("l2_sources.json")["by_n"]
    fig, axes = plt.subplots(1, 2, figsize=(16 * CM, 5.8 * CM))
    ns = ["2", "3", "4", "5"]
    x = np.arange(len(ns))
    ax = axes[0]
    parts = [("hit_input_reuse", "图输入张量复读", C3, 1.0), ("hit_cross_core_mid", "跨核中间张量", C1, 1.0),
             ("hit_spill_reload", "换出后再读", "#8491B4", 1.0)]
    bottom = np.zeros(len(ns))
    for k, lab, c, a in parts:
        v = np.array([d[n][k] / 1e6 for n in ns])
        ax.bar(x, v, bottom=bottom, color=c, alpha=0.85, width=0.6, label=lab, edgecolor="white", lw=0.5)
        bottom += v
    ax.set_xticks(x)
    ax.set_xticklabels([f"N={n}" for n in ns])
    ax.set_ylabel("命中字节 / MB")
    ax.legend(fontsize=7.4, loc="upper left")
    ax.set_ylim(0, bottom.max() * 1.45)
    ax.set_title("命中来源", fontsize=9)
    ax.grid(axis="x", visible=False)
    panel_label(ax, "(a)")
    ax = axes[1]
    parts = [("miss_first_miss", "首次读入（不可避免）", "#BDBDBD"),
             ("miss_concurrent_first_read", "并发首读", "#F39B7F"),
             ("miss_fifo_evicted", "被 FIFO 淘汰后再读", C2)]
    bottom = np.zeros(len(ns))
    for k, lab, c in parts:
        v = np.array([d[n][k] / 1e6 for n in ns])
        ax.bar(x, v, bottom=bottom, color=c, alpha=0.8, width=0.6, label=lab, edgecolor="white", lw=0.5)
        bottom += v
    ax.set_xticks(x)
    ax.set_xticklabels([f"N={n}" for n in ns])
    ax.set_ylabel("未命中字节 / MB")
    ax.legend(fontsize=7.4, loc="upper left")
    ax.set_title("未命中来源", fontsize=9)
    ax.set_ylim(0, bottom.max() * 1.45)
    ax.grid(axis="x", visible=False)
    panel_label(ax, "(b)")
    fig.tight_layout(w_pad=1.0)
    save(fig, "fig_l2_sources")


def fig_p2p3():
    a = sp(2, 4)
    b = sp(3, 4)
    fig, ax = plt.subplots(figsize=(8.5 * CM, 7.6 * CM))
    hi = max(a.max(), b.max()) * 1.05
    ax.plot([1, hi], [1, hi], color=GREY, lw=0.8, ls=(0, (4, 3)), label="y = x")
    better = b > a + 1e-9
    ax.scatter(a[~better], b[~better], s=14, color="#9AA5B1", edgecolor="white", lw=0.3, label="两者相等")
    ax.scatter(a[better], b[better], s=16, color=C3, edgecolor="white", lw=0.3, label="问题三更快")
    ax.set_xlabel("问题二标准流程方案的加速比（N=4）")
    ax.set_ylabel("问题三标准流程方案的加速比（N=4）")
    ax.set_xlim(1, hi)
    ax.set_ylim(1, hi)
    ax.set_aspect("equal")
    ax.legend(loc="upper left", fontsize=7.6)
    save(fig, "fig_p2p3")


# ------------------------------------------------------------------ 基线
def fig_baselines():
    base = pd.read_csv(R / "baseline.csv")
    names = [("random", "B1 随机", "#BDBDBD", "v"), ("topo", "B2 拓扑等分", "#969696", "D"),
             ("balance", "B3 负载均衡", "#636363", "^"), ("comm", "B4 通信聚类", "#8491B4", "s")]
    fig, axes = plt.subplots(1, 3, figsize=(16 * CM, 6.0 * CM), sharey=True)
    for ax, p in zip(axes, (1, 2, 3)):
        for alg, lab, c, m in names:
            ys = [1.0]
            for n in NS:
                d = base[(base.problem == p) & (base.num_cores == n) & (base.algorithm == alg)]
                ys.append(d.speedup.mean())
            ax.plot([1] + NS, ys, color=c, marker=m, ms=3.6, lw=1.1, label=lab)
        ys = [1.0] + [sp(p, n).mean() for n in NS]
        ax.plot([1] + NS, ys, color=PCOL[p], marker="o", ms=4.6, lw=2.0, label="CAP-LS 标准流程")
        ax.plot([1, 5], [1, 5], color=GREY, lw=0.7, ls=(0, (4, 3)))
        ax.set_title(PNAME[p], fontsize=9)
        ax.set_xticks([1] + NS)
        ax.set_xlabel("核心数 N")
    axes[0].set_ylabel("平均加速比")
    h, lab = axes[0].get_legend_handles_labels()
    fig.legend(h[:4] + [plt.Line2D([], [], color=DARK, marker="o", lw=2)], lab[:4] + ["CAP-LS 标准流程"],
               loc="lower center", ncol=5, fontsize=7.6, bbox_to_anchor=(0.5, -0.02))
    fig.tight_layout(rect=(0, 0.08, 1, 1), w_pad=0.6)
    save(fig, "fig_baselines")


# ------------------------------------------------------------------ 消融
def fig_ablation():
    ab = S["ablation2"]
    rows = [("no_level", "去掉同步层次分层"), ("no_comm", "去掉通信感知分块"), ("no_level_no_comm", "两者同时去掉"),
            ("no_sync", "代价去掉同步深度项"), ("no_localsearch", "去掉局部搜索"), ("max_ops500", "子图至多 500 算子"),
            ("lvl_alap", "ALAP 填充层指派"), ("op_full", "单算子子图 + 表调度")]
    fig, ax = plt.subplots(figsize=(15 * CM, 12 * CM))
    y = np.arange(len(rows))[::-1] * 1.25
    h = 0.3
    for j, p in enumerate((1, 2, 3)):
        vals, sig = [], []
        for k, _ in rows:
            d = ab[f"problem{p}"].get(k, {})
            if "paired" in d:
                vals.append(100 * d["paired"]["rel"])
                sig.append(d["paired"]["p_holm"] < 0.05)
            else:
                vals.append(np.nan)
                sig.append(False)
        yy = y + (1 - j) * h
        ax.barh(yy, vals, height=h * 0.92, color=PCOL[p], alpha=0.85, label=PNAME[p])
        for v, s_, yv in zip(vals, sig, yy):
            if np.isnan(v):
                continue
            if abs(v) < 1.5:
                continue
            ax.text(v + (0.8 if v >= 0 else -0.8), yv, f"{v:+.1f}%" + ("*" if s_ else ""), va="center",
                    ha="left" if v >= 0 else "right", fontsize=7, color=DARK)
    ax.axvline(0, color=DARK, lw=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels([r[1] for r in rows], fontsize=8.2)
    ax.set_xlabel("相对基准配置 c2 的平均加速比变化 / %（* 表示 Holm 校正后 p < 0.05）")
    ax.set_xlim(-70, 12)
    ax.set_ylim(y.min() - 0.7, y.max() + 0.7)
    ax.legend(loc="lower left", fontsize=7.6)
    ax.grid(axis="y", visible=False)
    save(fig, "fig_ablation")


# ------------------------------------------------------------------ 粒度
def fig_granularity():
    g = pd.read_csv(R / "granularity.csv")
    g = g[g.feasible == True]  # noqa: E712
    fig, ax = plt.subplots(figsize=(11.5 * CM, 6.6 * CM))
    for p in (1, 2, 3):
        d = g[g.problem == p].groupby("variant").speedup.mean()
        ax.plot(d.index, d.values, color=PCOL[p], marker="o", ms=4.2, lw=1.6, label=PNAME[p])
        b = d.idxmax()
        ax.scatter([b], [d.max()], s=80, facecolor="none", edgecolor=PCOL[p], lw=1.2, zorder=5)
    ax.axvline(0.35, color=GREY, lw=0.8, ls=(0, (3, 2)))
    ax.text(0.33, ax.get_ylim()[0] + 0.02, "默认 β = 0.35", fontsize=7.4, color="#555555", va="bottom", ha="right")
    ax.set_xscale("log")
    ax.set_xticks([0.03, 0.06, 0.12, 0.25, 0.5, 1, 2])
    ax.get_xaxis().set_major_formatter(mt.FuncFormatter(lambda v, _: f"{v:g}"))
    ax.set_xlabel("粒度参数 β（单块计算量上限为 βW/N）")
    ax.set_ylabel(f"{g.case.nunique()} 个用例的平均加速比（N=4）")
    ax.legend(loc="lower right", fontsize=7.6, bbox_to_anchor=(1, 0.08))
    save(fig, "fig_granularity")


# ------------------------------------------------------------------ 硬件灵敏度
def fig_sensitivity():
    s = pd.read_csv(R / "sensitivity.csv")
    s = s[s.feasible == True]  # noqa: E712
    knobs = [("bandwidth", "DDR 带宽 / (B/cycle)", 60, 1), ("L1", "L1 容量 / KB", 524288, 1024),
             ("UB", "UB 容量 / KB", 131072, 1024), ("cross_core_copy_delay_cycles", "问题二同步延迟 / cycle", 500, 1),
             ("task_cross_core_wait_cycles", "问题一跨核等待 / cycle", 1000, 1),
             ("cache_capacity_bytes", "L2 容量 / KB", 1048576, 1024),
             ("cache_bandwidth_bytes_per_cycle", "L2 带宽 / (B/cycle)", 250, 1)]
    fig, axes = plt.subplots(2, 4, figsize=(16 * CM, 7.8 * CM))
    axes = axes.ravel()
    for ax, (k, lab, dv, div) in zip(axes, knobs):
        d = s[s.knob == k]
        piv = d.pivot_table(index="case", columns="value", values="makespan")
        lr = np.log(piv[dv].values[:, None] / piv.values)
        ratio = np.exp(np.nanmean(lr, axis=0))
        vals = piv.columns.values / div
        col = C1 if k == "task_cross_core_wait_cycles" else (C3 if k.startswith("cache") else C2)
        ax.plot(range(len(vals)), ratio, color=col, marker="o", ms=3.6, lw=1.4)
        di = list(piv.columns.values).index(dv)
        ax.scatter([di], [1.0], s=50, facecolor="none", edgecolor=RED, lw=1.1, zorder=5)
        ax.axhline(1, color=GREY, lw=0.7, ls=(0, (3, 2)))
        ax.set_xticks(range(len(vals)))
        ax.set_xticklabels([f"{v:g}" for v in vals], fontsize=6.8, rotation=0)
        ax.set_xlabel(lab, fontsize=7.6)
        ax.tick_params(axis="y", labelsize=7)
        lo, hi = min(ratio.min(), 0.98), max(ratio.max(), 1.02)
        ax.set_ylim(lo - 0.02 * (hi - lo), hi + 0.08 * (hi - lo))
    axes[0].set_ylabel("Makespan 比（默认 / 变动后）", fontsize=7.4)
    axes[4].set_ylabel("Makespan 比（默认 / 变动后）", fontsize=7.4)
    ax = axes[7]
    ax.axis("off")
    ax.text(0.02, 0.62, "纵轴 > 1 表示比给定配置更快\n红圈为给定配置\n18 个用例几何平均，N=4", fontsize=7.4,
            va="center", color="#444444", transform=ax.transAxes, linespacing=1.6)
    fig.tight_layout(h_pad=0.8, w_pad=0.5)
    save(fig, "fig_sensitivity")


# ------------------------------------------------------------------ 下界
def fig_bounds():
    b = pd.read_csv(R / "bounds_cdf.csv")
    fin = pd.read_csv(R / "final.csv").set_index(["case", "problem", "num_cores"]).makespan
    std = final.set_index(["case", "problem", "num_cores"]).makespan
    idx = list(zip(b.case, b.problem, b.num_cores))
    lb = fin.reindex(idx).values / b.mk_over_lb.values
    b = b.assign(mk_over_lb=std.reindex(idx).values / lb)
    fig, ax = plt.subplots(figsize=(10.5 * CM, 6.4 * CM))
    for p in (1, 2, 3):
        d = b[(b.problem == p) & (b.num_cores == 4)].sort_values("mk_over_lb")
        ax.step(d.mk_over_lb, np.arange(1, len(d) + 1) / len(d), where="post", color=PCOL[p], lw=1.6,
                label=PNAME[p])
    ax.axvline(1, color=DARK, lw=0.8)
    ax.set_xscale("log")
    ax.set_xticks([1, 1.25, 1.5, 2, 3, 5])
    ax.get_xaxis().set_major_formatter(mt.FuncFormatter(lambda v, _: f"{v:g}"))
    ax.xaxis.set_minor_formatter(mt.NullFormatter())
    ax.set_xlabel("标准流程方案 Makespan / 理论下界（N=4）")
    ax.set_ylabel("累计比例")
    ax.legend(loc="lower right", fontsize=7.6)
    save(fig, "fig_bounds")


# ------------------------------------------------------------------ 代理检验与候选组合
def fig_proxy():
    leg = rj("model_validation_summary_legacy.json")
    sim = rj("model_validation_summary_sim.json")
    fig, axes = plt.subplots(1, 2, figsize=(16 * CM, 5.8 * CM))
    ax = axes[0]
    x = np.arange(3)
    w = 0.36
    lv = [leg[f"problem{p}"]["spearman_median"] for p in (1, 2, 3)]
    sv = [sim[f"problem{p}"]["spearman_median"] for p in (1, 2, 3)]
    lv[0] = np.nan  # 问题一只用 Task 级代理
    ax.bar(x - w / 2, lv, w, color="#BDBDBD", label="解析代理 F")
    ax.bar(x + w / 2, sv, w, color=C1, label="事件模拟代理")
    for i in range(3):
        if not np.isnan(lv[i]):
            ax.text(i - w / 2, lv[i] + 0.02, f"{lv[i]:.2f}", ha="center", fontsize=7.2)
        ax.text(i + w / 2, sv[i] + 0.02, f"{sv[i]:.2f}", ha="center", fontsize=7.2)
    ax.set_xticks(x)
    ax.set_xticklabels(["问题一", "问题二", "问题三"])
    ax.set_ylabel("用例内 Spearman 相关（中位数）")
    ax.set_ylim(0, 1.12)
    ax.legend(loc="upper right", fontsize=7.4)
    ax.grid(axis="x", visible=False)
    panel_label(ax, "(a)")
    ax = axes[1]
    ks = [1, 3, 5]
    lv = [leg["problem2"][f"recall{k}"] for k in ks]
    sv = [sim["problem2"][f"recall{k}"] for k in ks]
    x = np.arange(3)
    ax.bar(x - w / 2, lv, w, color="#BDBDBD", label="解析代理 F")
    ax.bar(x + w / 2, sv, w, color=C1, label="事件模拟代理")
    for i in range(3):
        ax.text(i - w / 2, lv[i] + 0.02, f"{100 * lv[i]:.0f}%", ha="center", fontsize=7.2)
        ax.text(i + w / 2, sv[i] + 0.02, f"{100 * sv[i]:.0f}%", ha="center", fontsize=7.2)
    ax.set_xticks(x)
    ax.set_xticklabels([f"前 {k} 名" for k in ks])
    ax.set_ylabel("评估第一名落入代理前 K 名的比例")
    ax.set_ylim(0, 1.12)
    ax.legend(loc="upper left", fontsize=7.4)
    ax.set_title("问题二", fontsize=9)
    ax.grid(axis="x", visible=False)
    panel_label(ax, "(b)")
    fig.tight_layout(w_pad=1.0)
    save(fig, "fig_proxy")


def fig_greedy():
    pa = rj("portfolio_analysis.json")
    fig, ax = plt.subplots(figsize=(11.5 * CM, 6.4 * CM))
    for p in (1, 2, 3):
        g = pa["greedy"][f"P{p}"]
        ax.plot([r["k"] for r in g], [r["amean"] for r in g], color=PCOL[p], marker="o", ms=3.2, lw=1.5,
                label=PNAME[p])
        px = pa["proxy_selection"][f"P{p}"]["proxy_only_amean"]
        ax.axhline(px, color=PCOL[p], lw=0.9, ls=(0, (2, 2)))
    ax.plot([], [], color=GREY, ls=(0, (2, 2)), label="点线：只凭代理选 1 个候选")
    ax.set_xlabel("贪心加入的候选数 k")
    ax.set_ylabel("N=4 平均加速比")
    ax.legend(loc="lower right", fontsize=7.4)
    save(fig, "fig_greedy")


# ------------------------------------------------------------------ 结构特征
def fig_struct():
    f = feats.loc[CASES]
    s = sp(2, 4)
    items = [(f.largest_component_frac, "最大连通分量占比", False),
             (f.critical_path_cycles / f.total_cycles, "关键路径 / 总计算量", True),
             (f.avg_width, "DAG 平均宽度", True), (f.n_ops, "算子数", True)]
    fig, axes = plt.subplots(1, 4, figsize=(16 * CM, 4.9 * CM), sharey=True)
    for ax, (x, lab, log) in zip(axes, items):
        ax.scatter(x, s, s=9, color=C2, alpha=0.75, lw=0)
        if log:
            ax.set_xscale("log")
        from scipy.stats import spearmanr
        rho = spearmanr(x, s)[0]
        ax.set_title(f"Spearman {rho:+.2f}".replace("-", "−"), fontsize=8.2)
        ax.set_xlabel(lab, fontsize=7.8)
        ax.axhline(4, color=GREY, lw=0.7, ls=(0, (3, 2)))
    axes[0].set_ylabel("问题二 N=4 加速比")
    fig.tight_layout(w_pad=0.4)
    save(fig, "fig_struct")


# 蓝色单色系分级色阶：效率集中在 0.8～1.1，连续色阶在这一段区分不开，按整数边界分 8 级；最深两级为超线性
HEAT_EDGES = [0.0, 0.5, 0.7, 0.8, 0.9, 0.95, 1.0, 1.1, 2.0]
HEAT_COLORS = ["#F7FBFF", "#DEEBF7", "#C6DBEF", "#9ECAE1", "#6BAED6", "#4292C6", "#2171B5", "#08306B"]


def fig_heatmap():
    from matplotlib.colors import BoundaryNorm, ListedColormap
    cmap = ListedColormap(HEAT_COLORS)
    norm = BoundaryNorm(HEAT_EDGES, cmap.N)
    order = feats.loc[CASES].sort_values("largest_component_frac").index
    fig, axes = plt.subplots(3, 1, figsize=(16 * CM, 8.2 * CM), sharex=True)
    for ax, p in zip(axes, (1, 2, 3)):
        M = np.array([[sp(p, n)[c] / n for c in order] for n in NS])
        im = ax.imshow(M, aspect="auto", cmap=cmap, norm=norm, interpolation="nearest")
        ax.set_yticks(range(4))
        ax.set_yticklabels([f"N={n}" for n in NS], fontsize=7)
        ax.set_ylabel(["问题一", "问题二", "问题三"][p - 1], fontsize=8, rotation=0, ha="right", va="center")
        ax.grid(False)
        for sp_ in ax.spines.values():
            sp_.set_visible(False)
    rho = feats.loc[order, "largest_component_frac"].values
    k2, k5 = np.searchsorted(rho, 0.2), np.searchsorted(rho, 0.5)
    for k in (k2, k5):
        for ax in axes:
            ax.axvline(k - 0.5, color="#C0504D", lw=0.9, ls=(0, (3, 1.5)))
    axes[-1].set_xticks([k2 / 2, (k2 + k5) / 2, (k5 + len(rho)) / 2])
    axes[-1].set_xticklabels([r"$\rho_{\max}<0.2$", r"$0.2\leq\rho_{\max}<0.5$", r"$\rho_{\max}\geq0.5$"],
                             fontsize=7.8)
    axes[-1].set_xlabel("100 个用例（按最大连通分量占比升序排列）")
    cb = fig.colorbar(im, ax=axes, fraction=0.025, pad=0.01, spacing="uniform", ticks=HEAT_EDGES[1:-1])
    cb.set_label("并行效率 = 加速比 / N", fontsize=7.8)
    cb.ax.set_yticklabels([f"{e:g}" for e in HEAT_EDGES[1:-1]])
    cb.ax.tick_params(labelsize=7)
    cb.ax.axhline(1.0, color="#C0504D", lw=1.2)
    save(fig, "fig_heatmap")


# ------------------------------------------------------------------ 三维散点：加速比与两个结构特征（问题二，N=4）
def fig_struct3d():
    from matplotlib.colors import LinearSegmentedColormap
    from matplotlib.patches import Patch
    blues = LinearSegmentedColormap.from_list("blues_mono", ["#F4F8FC", "#D6E4F2", "#A9C8E4", "#6FA3D0", "#3C78B4",
                                                             "#1F4E8C", "#0B2A5B"])
    f = feats.loc[CASES]
    x = f.largest_component_frac.values
    y = np.log10(f.cp_over_total.values)
    z = sp(2, 4).values
    # 三维坐标轴默认四周留白很大：让坐标轴铺满画布再放大，裁切后的实际尺寸约等于插入 Word 的宽度，字号不被放大
    fig = plt.figure(figsize=(12.5 * CM, 9.6 * CM))
    ax = fig.add_axes([0, 0, 1, 1], projection="3d")
    zmin = 0.0
    y0, y1 = np.floor(y.min() * 2) / 2, np.ceil(y.max() * 2) / 2
    for xi, yi, zi in zip(x, y, z):
        ax.plot([xi, xi], [yi, yi], [zmin, zi], color="#B8C4D6", lw=0.5, zorder=1)
    ax.scatter(x, y, np.full_like(z, zmin), s=6, color="#C9C9C9", depthshade=False, zorder=1)
    ax.scatter(x, y, z, c=z, cmap=blues, vmin=0.2, vmax=6.5, s=18, edgecolor="#1F3552", lw=0.3,
               depthshade=False, zorder=3)
    xx, yy = np.meshgrid([0, 1], [y0, y1])
    ax.plot_surface(xx, yy, np.full_like(xx, 4.0), color="#C0504D", alpha=0.10, lw=0, shade=False)
    ax.plot([0, 1, 1], [y0, y0, y1], [4, 4, 4], color="#C0504D", lw=0.8, ls=(0, (3, 2)))
    ax.legend(handles=[Patch(facecolor="#C0504D", alpha=0.18, edgecolor="#C0504D", ls=(0, (3, 2)), lw=0.8,
                             label="加速比 = 4 的平面（线性加速）")],
              loc="upper left", bbox_to_anchor=(0.02, 0.98), fontsize=7.6, frameon=False, handlelength=1.6)
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
    for a_ in (ax.xaxis, ax.yaxis, ax.zaxis):
        a_.pane.set_facecolor("#FAFBFD")
        a_.pane.set_edgecolor("#BBBBBB")
        a_._axinfo["grid"].update(color="#E6E6E6", linewidth=0.5)
    ax.view_init(elev=20, azim=-60)
    ax.set_box_aspect((1.25, 1.0, 0.85), zoom=1.02)
    _save_trimmed(fig, "fig_struct3d")


def _save_trimmed(fig, name, pad=0.03):
    """三维坐标轴的 tight 边界含大片空白：先按 tight 边界渲染一次，找出有墨迹的范围，再按它裁切保存。"""
    import io
    from PIL import Image
    from matplotlib.transforms import Bbox
    fig.canvas.draw()
    tb = fig.get_tightbbox(fig.canvas.get_renderer())
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches=tb, pad_inches=0, facecolor="white")
    im = np.asarray(Image.open(buf).convert("L"))
    rows, cols = np.where(im.min(axis=1) < 245)[0], np.where(im.min(axis=0) < 245)[0]
    h, w = im.shape
    crop = Bbox([[tb.x0 + cols[0] / w * tb.width - pad, tb.y1 - (rows[-1] + 1) / h * tb.height - pad],
                 [tb.x0 + (cols[-1] + 1) / w * tb.width + pad, tb.y1 - rows[0] / h * tb.height + pad]])
    out = figstyle_v4.OUT
    svg = out / f"{name}.svg"
    fig.savefig(svg, facecolor="white", bbox_inches=crop)
    figstyle_v4._fix_svg_fonts(svg)
    fig.savefig(out / f"{name}.png", facecolor="white", bbox_inches=crop)
    plt.close(fig)
    print("  ", svg.relative_to(ROOT))


def fig_summary():
    fig, ax = plt.subplots(figsize=(11.5 * CM, 7.2 * CM))
    xs = [1] + NS
    ax.plot([1, 5.2], [1, 5.2], color=GREY, lw=0.9, ls=(0, (4, 3)), label="理想线性加速 y = N")
    mk = {1: "o", 2: "s", 3: "^"}
    for p in (1, 2, 3):
        ys = [1.0] + [sp(p, n).mean() for n in NS]
        ax.plot(xs, ys, color=PCOL[p], marker=mk[p], ms=5, lw=1.8,
                label=PNAME[p] + "：" + " / ".join(f"{v:.2f}" for v in ys[1:]))
    ax.set_xticks(xs)
    ax.set_xlabel("核心数 N")
    ax.set_ylabel("平均加速比（100 个用例算术平均）")
    ax.legend(loc="upper left", fontsize=7.6)
    save(fig, "fig_summary")


ALL = {"speedup": lambda: [fig_speedup(p) for p in (1, 2, 3)], "dist": fig_dist, "features": fig_features,
       "runtime": fig_runtime, "superlinear": fig_superlinear, "traffic": fig_traffic,
       "p3_compare": fig_p3_compare, "l2_case": fig_l2_case, "l2_sources": fig_l2_sources, "p2p3": fig_p2p3,
       "baselines": fig_baselines, "ablation": fig_ablation, "granularity": fig_granularity,
       "sensitivity": fig_sensitivity, "bounds": fig_bounds, "proxy": fig_proxy, "greedy": fig_greedy,
       "struct": fig_struct, "struct3d": fig_struct3d, "heatmap": fig_heatmap, "summary": fig_summary}

NEEDED = ("speedup", "dist", "superlinear", "traffic", "p3_compare", "l2_case", "p2p3", "baselines",
          "bounds", "struct", "heatmap", "summary")  # "struct" 同时匹配 struct 与 struct3d

if __name__ == "__main__":
    want = sys.argv[1:] or list(NEEDED)
    for k, fn in ALL.items():
        if not want or any(w in k for w in want):
            fn()
