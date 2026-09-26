"""v3 修订：从 results/ 已有的官方评估记录重算“标准求解流程”口径的统计量。

口径定义（见论文 v3 第 4.5 节与第 7.1 节）：
  标准求解流程 = CAP-LS 预定义候选网格 c0～c17 + 问题一模拟退火（sa1～sa3）
                 + 问题二、三优先级采样（s1～s16），由 experiment.run_portfolio 产生，
                 记录在 results/main.csv；每个 (用例, 问题, N) 取该流程选出的方案
                 （main.csv 中 variant=_best 的行；问题一 4 个代理兜底大图没有 _best 行，
                 取其已官方评估候选中 Makespan 最小者，与 run_portfolio 的选择一致）。
  离线候选扩展后的最好结果 = results/final.csv（基准候选集汇总，含消融/基线/粒度/
                 N-1 嵌入/跨场景复用），只用于说明可达性能上界。

本脚本不调用评估器，不改动 results/；输出：
  paper/v3/data/final_standard.csv   标准流程逐配置结果（附录 A 表格数据源）
  paper/v3/data/std_caliber.json     重算统计量（供核对）
  paper/v3/data/facts_v3.json        facts_v2.json + v3 新增/改口径的占位符
"""

from __future__ import annotations

import json
import math
import random
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
from scipy.stats import wilcoxon

ROOT = Path(__file__).resolve().parents[3]
R = ROOT / "results"
OUT = ROOT / "paper" / "v3" / "data"
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "solution"))

F = json.loads((R / "facts_v2.json").read_text(encoding="utf-8"))
J: dict = {}
NS = [2, 3, 4, 5]
KEY = ["case", "problem", "num_cores"]


def f2(x):
    return f"{x:.2f}"


def f3(x):
    return f"{x:.3f}"


def pct(x, d=1):
    return f"{100 * x:.{d}f}%"


def spct(x, d=1):
    return ("+" if x >= 0 else "") + f"{100 * x:.{d}f}%"


def sci(x, d=2):
    if x == 0:
        return "0"
    e = int(math.floor(math.log10(abs(x))))
    return f"{x / 10 ** e:.{d}f}\\times10^{{{e}}}"


def pval(p):
    if p >= 0.001:
        return f"{p:.3f}"
    e = int(math.floor(math.log10(p)))
    return f"{p / 10 ** e:.1f}\\times10^{{{e}}}"


def boot_ci(xs, n_boot=10000, seed=20260923):
    rng = random.Random(seed)
    n = len(xs)
    bs = sorted(st.mean(rng.choices(xs, k=n)) for _ in range(n_boot))
    return bs[int(0.025 * (n_boot - 1))], bs[int(0.975 * (n_boot - 1))]


def holm(ps: dict) -> dict:
    items = sorted(ps.items(), key=lambda kv: kv[1])
    m, out, run = len(items), {}, 0.0
    for i, (k, p) in enumerate(items):
        run = max(run, min(1.0, (m - i) * p))
        out[k] = run
    return out


def paired(a: dict, b: dict, tie=0.001):
    keys = sorted(set(a) & set(b))
    w = t = l = 0
    diffs = []
    for k in keys:
        r = a[k] / b[k] - 1
        w += r > tie
        l += r < -tie
        t += -tie <= r <= tie
        diffs.append(math.log(a[k]) - math.log(b[k]))
    p = float(wilcoxon(diffs, zero_method="wilcox").pvalue) if any(diffs) else 1.0
    ma, mb = st.mean(a[k] for k in keys), st.mean(b[k] for k in keys)
    return dict(n=len(keys), win=w, tie=t, loss=l, mean_a=ma, mean_b=mb, rel=ma / mb - 1, p=p)


# ---------------------------------------------------------------------------
# 1. 标准求解流程的逐配置结果
# ---------------------------------------------------------------------------
main = pd.read_csv(R / "main.csv")
cand = main[(main.variant != "_best") & (main.feasible == True)]  # noqa: E712
best_rows = main[main.variant == "_best"].set_index(KEY)
fallback = (cand.sort_values(KEY + ["makespan", "added_copy_bytes"])
            .groupby(KEY).head(1).set_index(KEY))
rows = []
for k, r in fallback.iterrows():
    if k in best_rows.index:
        b = best_rows.loc[k]
        # _best 行不记 variant：从候选中找出同 Makespan、同搬运量的那一个
        same = cand[(cand.case == k[0]) & (cand.problem == k[1]) & (cand.num_cores == k[2])
                    & (cand.makespan == b.makespan) & (cand.added_copy_bytes == b.added_copy_bytes)]
        src = same.variant.iloc[0] if len(same) else r.variant
        row = b.to_dict()
        if len(same):                      # 退火冠军的 _best 行缺少搬运拆分字段，从候选行补齐
            for col, val in same.iloc[0].items():
                if col in row and pd.isna(row[col]) and not pd.isna(val):
                    row[col] = val
        row["variant"] = src
        row["proxy_fallback"] = False
    else:
        row = r.to_dict()
        row["proxy_fallback"] = True
    row.update(dict(zip(KEY, k)))
    rows.append(row)
std = pd.DataFrame(rows)
std["speedup"] = std.baseline_makespan / std.makespan
std["mono_fix"] = False

# 单调性修复：对每个 (用例, 问题, N)，与"整图单核"及标准流程自身在更少核数下的
# 方案比较，取 Makespan 更优者（源方案末尾追加空核，不引入新依赖或新搬运，
# 由 build_mono_plans.py 逐个用官方评估脚本复核过，见 results/verify_final_mono.csv）。
# 这保证了标准流程口径下加速比恒 >= 1、随核数单调不降，不再是可选的后续工作。
mono_path = R / "final_plans_mono" / "manifest.csv"
if mono_path.is_file():
    mono = pd.read_csv(mono_path)
    std_idx = std.set_index(KEY)
    for r in mono[mono.source != "self"].itertuples():
        k = (r.case, r.problem, r.num_cores)
        source_n = r.source_n
        if source_n == 1:
            src = pd.read_csv(R / "n1.csv")
            src_row = src[(src.case == r.case) & (src.problem == r.problem)].iloc[0]
        else:
            src_row = std_idx.loc[(r.case, r.problem, source_n)]
        i = std_idx.index.get_loc(k)
        for col in ("makespan", "added_copy_bytes", "partition_added_copy_bytes",
                    "spill_added_copy_bytes", "scheduled_copy_bytes", "cache_hit_rate",
                    "cache_hit_bytes", "n_subgraphs"):
            std.loc[std_idx.index.get_indexer([k])[0], col] = src_row[col]
        std.loc[std_idx.index.get_indexer([k])[0], "variant"] = f"mono_embed_n{source_n}"
        std.loc[std_idx.index.get_indexer([k])[0], "plan_path"] = r.plan
        std.loc[std_idx.index.get_indexer([k])[0], "mono_fix"] = True
    std["speedup"] = std.baseline_makespan / std.makespan
    J["mono_fix_rows"] = int(std.mono_fix.sum())
    F["MONO_FIX_N"] = str(int(std.mono_fix.sum()))

std.to_csv(OUT / "final_standard.csv", index=False)
fin = pd.read_csv(R / "final.csv")
n1 = pd.read_csv(R / "n1.csv")
STD = {(r.case, r.problem, r.num_cores): r for r in std.itertuples()}
FIN = {(r.case, r.problem, r.num_cores): r for r in fin.itertuples()}
N1 = {(r.case, r.problem): r for r in n1.itertuples()}
CASES = sorted(fin.case.unique())
J["n_std_rows"] = len(std)
J["n_proxy_fallback_rows"] = int(std.proxy_fallback.sum())

# ---------------------------------------------------------------------------
# 2. 主结果统计（标准流程），并与离线扩展结果对照
# ---------------------------------------------------------------------------
for p in (1, 2, 3):
    means, fmeans = [], []
    for n in NS:
        xs = [STD[(c, p, n)].speedup for c in CASES]
        fx = [FIN[(c, p, n)].speedup for c in CASES]
        m, fm = st.mean(xs), st.mean(fx)
        means.append(m)
        fmeans.append(fm)
        lo, hi = boot_ci(xs)
        F[f"P{p}_MEAN_{n}"] = f2(m)
        F[f"P{p}_MEAN3_{n}"] = f3(m)
        F[f"P{p}_CI_{n}"] = f"[{lo:.2f}, {hi:.2f}]"
        F[f"P{p}_GEO_{n}"] = f2(math.exp(st.mean(math.log(x) for x in xs)))
        F[f"P{p}_MED_{n}"] = f2(st.median(xs))
        F[f"P{p}_MIN_{n}"] = f2(min(xs))
        F[f"P{p}_MAX_{n}"] = f2(max(xs))
        F[f"P{p}_SUPER_{n}"] = str(sum(x > n + 1e-9 for x in xs))
        F[f"P{p}_EFF_{n}"] = f"{100 * m / n:.0f}%"
        F[f"P{p}_LT1_{n}"] = str(sum(x < 1 - 1e-9 for x in xs))
        # 离线扩展口径
        F[f"OFF_P{p}_MEAN_{n}"] = f2(fm)
        F[f"OFF_P{p}_GAP_{n}"] = spct(fm / m - 1)
        better = [c for c in CASES if FIN[(c, p, n)].makespan < STD[(c, p, n)].makespan]
        F[f"OFF_P{p}_BETTER_{n}"] = str(len(better))
        gaps = [STD[(c, p, n)].makespan / FIN[(c, p, n)].makespan - 1 for c in CASES]
        F[f"OFF_P{p}_MAXGAP_{n}"] = pct(max(gaps))
        mx = max(CASES, key=lambda c: STD[(c, p, n)].makespan / FIN[(c, p, n)].makespan)
        F[f"OFF_P{p}_MAXGAPC_{n}"] = mx
        J[f"p{p}_n{n}"] = dict(std_mean=m, off_mean=fm, off_better=len(better),
                               max_gap=max(gaps), max_gap_case=mx,
                               median_gap=st.median(gaps))
    F[f"P{p}_MEAN_LIST"] = "、".join(f2(x) for x in means)
    F[f"OFF_P{p}_MEAN_LIST"] = "、".join(f2(x) for x in fmeans)
    # 单调性（标准流程不做 N-1 嵌入）
    viol, lt1 = 0, 0
    for c in CASES:
        prev = int(N1[(c, p)].makespan)
        for n in NS:
            mk = int(STD[(c, p, n)].makespan)
            viol += mk > prev
            prev = mk
    F[f"P{p}_MONO_VIOL"] = str(viol)
    F[f"P{p}_LT1_ALL"] = str(sum(STD[(c, p, n)].speedup < 1 - 1e-9 for c in CASES for n in NS))
    worst = sorted((STD[(c, p, 4)].speedup, c) for c in CASES)[:6]
    F[f"P{p}_WORST_N4"] = "、".join(f"{c}（{s:.2f}）" for s, c in worst)
    rows4 = [STD[(c, p, 4)] for c in CASES]
    part = sum(r.partition_added_copy_bytes for r in rows4)
    spill = sum(r.spill_added_copy_bytes for r in rows4)
    F[f"P{p}_ADDED_N4"] = sci(sum(r.added_copy_bytes for r in rows4))
    F[f"P{p}_CUTSHARE_N4"] = pct(part / (part + spill))
    F[f"P{p}_SPILLSHARE_N4"] = pct(spill / (part + spill))
    F[f"P{p}_ZERO_ADDED_N4"] = str(sum(r.added_copy_bytes == 0 for r in rows4))
    F[f"P{p}_SUBG_MED_N4"] = f"{st.median(r.n_subgraphs for r in rows4):g}"
    for n in NS:
        J.setdefault("mono_viol", {})[f"p{p}"] = viol

# 可选的单调性保障：把标准流程自身的 N-1 方案补一个空核嵌入 N 核，并与整图单核方案比较。
# pool.csv 中 900 个 embed_n* 方案的 Makespan 与其 N-1 源方案逐一相等（已核对），
# 因此该口径可由标准流程逐核结果的前缀最小值直接得到，无需新的评估。
emb = pd.read_csv(R / "pool.csv")
emb = emb[emb.label.str.startswith("embed")]
src_mk = {(r.case, r.problem, r.num_cores): r.makespan for r in fin.itertuples()}
J["embed_equal_check"] = f"{sum(r.makespan == src_mk[(r.case, r.problem, r.num_cores - 1)] for r in emb.itertuples())}/{len(emb)}"
for p in (1, 2, 3):
    vals = []
    for n in NS:
        xs = []
        for c in CASES:
            mk = min([int(N1[(c, p)].makespan)] + [int(STD[(c, p, k)].makespan) for k in range(2, n + 1)])
            xs.append(STD[(c, p, n)].baseline_makespan / mk)
        vals.append(f2(st.mean(xs)))
        F[f"MONO_P{p}_MEAN_{n}"] = vals[-1]
    F[f"MONO_P{p}_MEAN_LIST"] = "、".join(vals)

# 标准流程的方案来源
src = Counter()
for r in std.itertuples():
    v = str(r.variant)
    if v.startswith("mono_embed"):
        cat = "mono"
    elif v.startswith("sa"):
        cat = "sa"
    elif v.startswith("s") and v[1:].isdigit():
        cat = "samp"
    else:
        k = int(v[1:])
        cat = "grid_a" if k <= 11 else ("grid_b" if k <= 13 else "grid_op")
    src[(r.problem, cat)] += 1
for p in (1, 2, 3):
    for cat in ("grid_a", "grid_b", "grid_op", "samp", "sa", "mono"):
        val = src.get((p, cat), 0)
        F[f"STDSRC_P{p}_{cat.upper()}"] = str(val) if (val or cat not in ("grid_op", "samp", "sa", "mono")) else "—"
    F[f"STDSRC_P{p}_FALLBACK"] = str(int(std[(std.problem == p)].proxy_fallback.sum()))
J["std_sources"] = {f"{k[0]}_{k[1]}": v for k, v in src.items()}

# 离线扩展口径中“严格优于标准流程”的配置按来源分类
strict = Counter()
for r in fin.itertuples():
    k = (r.case, r.problem, r.num_cores)
    if r.makespan < STD[k].makespan:
        v = str(r.variant).replace("pool:", "")
        cat = ("abl" if v.startswith("a_") else "gran" if v.startswith("g_") else
               "base" if v.startswith("b_") else "embed" if v.startswith("embed") else
               "cross" if v.startswith("cross") or v.startswith("x3_") else
               "pruned" if v.startswith("c") and v[1:].isdigit() else "other:" + v)
        strict[(r.problem, cat)] += 1
for p in (1, 2, 3):
    tot = sum(v for (pp, _), v in strict.items() if pp == p)
    F[f"OFF_STRICT_P{p}"] = str(tot)
    for cat in ("abl", "gran", "base", "embed", "cross", "pruned"):
        F[f"OFF_STRICT_P{p}_{cat.upper()}"] = str(strict.get((p, cat), 0))
J["off_strict_sources"] = {f"{k[0]}_{k[1]}": v for k, v in strict.items()}

# 离线扩展口径的来源（沿用 facts_v2 的 SRC_*，另给出“非标准流程来源”合计）
for p in (1, 2, 3):
    extra = 0
    for cat in ("ABL", "GRAN", "BASE", "EMBED", "CROSS", "SINGLE"):
        v = F.get(f"SRC_P{p}_{cat}", "0")
        extra += int(v) if v.isdigit() else 0
    F[f"SRC_P{p}_EXTRA"] = str(extra)

# ---------------------------------------------------------------------------
# 3. 标准流程 vs 基线 B1～B4（N=4），以及 c2 vs B4
# ---------------------------------------------------------------------------
base = pd.read_csv(R / "baseline.csv")
tags = {"random": "B1", "topo": "B2", "balance": "B3", "comm": "B4"}
res, ps = {}, {}
for p in (1, 2, 3):
    a = {c: STD[(c, p, 4)].speedup for c in CASES}
    for algo, tag in tags.items():
        bb = base[(base.problem == p) & (base.num_cores == 4) & (base.algorithm == algo)
                  & (base.feasible == True)]  # noqa: E712
        b = {r.case: r.speedup for r in bb.itertuples()}
        d = paired(a, b)
        res[(p, tag)] = d
        ps[(p, tag)] = d["p"]
adj = holm(ps)
for (p, tag), d in res.items():
    d["p_holm"] = adj[(p, tag)]
    J[f"std_vs_{tag}_p{p}"] = d
    if tag == "B4":
        F[f"VSB4_P{p}_REL"] = spct(d["rel"], 0)
        F[f"VSB4_P{p}_REL1"] = spct(d["rel"], 1)
        F[f"VSB4_P{p}_WTL"] = f"{d['win']}/{d['tie']}/{d['loss']}"
        F[f"VSB4_P{p}_P"] = pval(d["p_holm"])
    else:
        F[f"VS{tag}_P{p}_REL"] = spct(d["rel"], 0)
# 离线扩展口径 vs B4（原 v2 数字，只作对照）
S = json.loads((R / "summary.json").read_text(encoding="utf-8"))
for p in (1, 2, 3):
    d = S["paired"][f"problem{p}"]["capls_vs_comm"]
    F[f"OFFVSB4_P{p}_REL"] = spct(d["rel"], 0)
    F[f"OFFVSB4_P{p}_WTL"] = f"{d['win']}/{d['tie']}/{d['loss']}"
# 离线扩展口径中直接来自基线方案的最终方案数（循环比较的来源）
for p in (1, 2, 3):
    F[f"OFF_FROMBASE_P{p}"] = F.get(f"SRC_P{p}_BASE", "0")

# ---------------------------------------------------------------------------
# 4. 问题二：超线性、换入换出、结构分层（标准流程）
# ---------------------------------------------------------------------------
sc = json.loads((R / "singlecore_baseline.json").read_text(encoding="utf-8"))
spills = {c: sc[c]["spill_added_copy_bytes"] for c in sc}
sup4 = [c for c in CASES if STD[(c, 2, 4)].speedup > 4]
F["P2_SUPER4_WITH_SPILL"] = str(sum(spills.get(c, 0) > 0 for c in sup4))
F["P2_SUPER4_NO_SPILL"] = str(sum(spills.get(c, 0) == 0 for c in sup4))
F["P2_ADDED_VS_SC"] = f"{100 * sum(STD[(c, 2, 4)].added_copy_bytes for c in CASES) / sum(spills.values()):.0f}%"
F["P2_SPILL_STD_N4"] = sci(sum(STD[(c, 2, 4)].spill_added_copy_bytes for c in CASES))
feats = {r["case"]: r for r in json.loads((R / "features.json").read_text(encoding="utf-8"))}
for p in (1, 2):
    for tag, lo, hi in (("A", 0, 0.2), ("B", 0.2, 0.5), ("C", 0.5, 1.01)):
        xs = [STD[(c, p, 4)].speedup for c in CASES if lo <= feats[c]["largest_component_frac"] < hi]
        F[f"P{p}_STR{tag}_N"] = str(len(xs))
        F[f"P{p}_STR{tag}_MEAN"] = f2(st.mean(xs))
        F[f"P{p}_STR{tag}_MED"] = f2(st.median(xs))
        F[f"P{p}_STR{tag}_MIN"] = f2(min(xs))
F["C16_P2_N4"] = f2(STD[("case_016", 2, 4)].speedup)
F["C16_P1_N4"] = f2(STD[("case_016", 1, 4)].speedup)
big4 = ["case_014", "case_072", "case_076", "case_091"]
v4 = [STD[(c, 1, 4)].speedup for c in big4]
F["BIG4_N4_MIN"], F["BIG4_N4_MAX"] = f2(min(v4)), f2(max(v4))
# 结构相关（问题二 N=4）
from scipy.stats import pearsonr, spearmanr  # noqa: E402
y = [STD[(c, 2, 4)].speedup for c in CASES]
for tag, fn in (("RHO", lambda f: f["largest_component_frac"]),
                ("CPR", lambda f: f["critical_path_cycles"] / f["total_cycles"]),
                ("WIDTH", lambda f: f["avg_width"]),
                ("NOPS", lambda f: f["n_ops"])):
    x = [fn(feats[c]) for c in CASES]
    xl = [math.log10(v) if tag in ("WIDTH", "NOPS") else v for v in x]   # 与 v2 facts.py 相同
    F[f"CORR_{tag}_P"] = f"{pearsonr(xl, y)[0]:+.2f}".replace("-", "−")
    F[f"CORR_{tag}_S"] = f"{spearmanr(x, y)[0]:+.2f}".replace("-", "−")
# 三维散点图（问题二 N=4）：各 ρ_max 分层中加速比超过 4 的用例数，以及分层内关键路径占比与加速比的 Spearman 相关
for tag, lo, hi in (("A", 0, 0.2), ("B", 0.2, 0.5), ("C", 0.5, 1.01)):
    cs = [c for c in CASES if lo <= feats[c]["largest_component_frac"] < hi]
    F[f"P2_STR{tag}_SUP4"] = str(sum(STD[(c, 2, 4)].speedup > 4 + 1e-9 for c in cs))   # 与 P2_SUPER_4 同口径
    cpr = [feats[c]["critical_path_cycles"] / feats[c]["total_cycles"] for c in cs]
    F[f"P2_STR{tag}_CPR_S"] = f"{spearmanr(cpr, [STD[(c, 2, 4)].speedup for c in cs])[0]:+.2f}".replace("-", "−")

# ---------------------------------------------------------------------------
# 5. 问题三：两类 Cache 指标（标准流程）
# ---------------------------------------------------------------------------
pc = pd.read_csv(R / "p3_compare.csv")
same2 = {(r.case, r.num_cores): r.makespan for r in pc[(pc.eval_problem == 2) & (pc.variant == "_best")].itertuples()}
same3 = {(r.case, r.num_cores): r.makespan for r in pc[(pc.eval_problem == 3) & (pc.variant == "_best")].itertuples()}
single2 = {r.case: r.makespan for r in pc[(pc.eval_problem == 2) & (pc.algorithm == "single")].itertuples()}
single3 = {r.case: r.makespan for r in pc[(pc.eval_problem == 3) & (pc.algorithm == "single")].itertuples()}
chk = sum(same3[(c, n)] == STD[(c, 3, n)].makespan for c in CASES for n in NS)
J["p3_compare_best_matches_std_p3"] = f"{chk}/400"
glist, slist = [], []
for n in [1] + NS:
    if n == 1:
        g = [(int(N1[(c, 2)].makespan) / int(N1[(c, 3)].makespan), c) for c in CASES]
        s = [single2[c] / single3[c] for c in CASES]
        hits = [float(N1[(c, 3)].cache_hit_rate or 0) for c in CASES]
    else:
        g = [(STD[(c, 2, n)].makespan / STD[(c, 3, n)].makespan, c) for c in CASES]
        s = [same2[(c, n)] / same3[(c, n)] for c in CASES]
        hits = [float(STD[(c, 3, n)].cache_hit_rate or 0) for c in CASES]
    F[f"L2G_{n}"] = f3(st.mean(x for x, _ in g))
    F[f"L2G_GT1_{n}"] = str(sum(x > 1.01 for x, _ in g))
    F[f"L2G_LT1_{n}"] = str(sum(x < 1 - 1e-9 for x, _ in g))
    mx = max(g)
    F[f"L2G_MAX_{n}"] = f2(mx[0])
    F[f"L2G_MAXC_{n}"] = mx[1]
    F[f"L2G_MAXCS_{n}"] = mx[1].replace("case_", "")
    F[f"L2SAME_{n}"] = f3(st.mean(s))
    F[f"L2SAME_GT1_{n}"] = str(sum(x > 1.01 for x in s))
    F[f"L2SAME_LT1_{n}"] = str(sum(x < 1 - 1e-9 for x in s))
    ms = max(zip(s, CASES))
    F[f"L2SAME_MAX_{n}"] = f2(ms[0])
    F[f"L2SAME_MAXC_{n}"] = ms[1]
    F[f"HIT_{n}"] = pct(st.mean(hits))
    F[f"HIT_NZ_{n}"] = str(sum(h > 0 for h in hits))
    glist.append(F[f"L2G_{n}"])
    slist.append(F[f"L2SAME_{n}"])
F["L2G_LIST"] = "、".join(glist)
F["L2SAME_LIST"] = "、".join(slist)
F["HIT_RANGE"] = f"{F['HIT_1']}～{F['HIT_5']}"
fa = sum(STD[(c, 3, 4)].makespan < STD[(c, 2, 4)].makespan for c in CASES)
eq = sum(STD[(c, 3, 4)].makespan == STD[(c, 2, 4)].makespan for c in CASES)
F["P3VSP2_FASTER"], F["P3VSP2_EQUAL"] = str(fa), str(eq)
F["P3VSP2_SLOWER"] = str(len(CASES) - fa - eq)
slow_all = [(STD[(c, 3, n)].makespan / STD[(c, 2, n)].makespan - 1, c, n)
            for c in CASES for n in NS if STD[(c, 3, n)].makespan > STD[(c, 2, n)].makespan]
F["P3SLOW_ALL_N"] = str(len(slow_all))
F["P3SLOW_ALL_MAX"] = pct(max(slow_all)[0], 2) if slow_all else "0"
F["P3SLOW_ALL_MAXC"] = f"{max(slow_all)[1]}（$N={max(slow_all)[2]}$）" if slow_all else "—"
F["P3SLOW_ALL_MED"] = pct(st.median(x for x, _, _ in slow_all), 2) if slow_all else "0"
# 同一方案在两种配置下变慢的次数（纯硬件口径的非单调性）
same_slow = [(same3[(c, n)] / same2[(c, n)] - 1, c, n) for c in CASES for n in NS if same3[(c, n)] > same2[(c, n)]]
F["SAME_SLOW_N"] = str(len(same_slow))
F["SAME_SLOW_MAX"] = pct(max(same_slow)[0], 3) if same_slow else "0"
J["p3_slower_than_p2_std"] = sorted(slow_all, reverse=True)[:10]
J["same_plan_p3_slower"] = sorted(same_slow, reverse=True)[:10]
# 灵敏度样本的命中率（标准流程口径）
sens = pd.read_csv(R / "sensitivity.csv")
sens_cases = sorted(sens.case.unique())
F["SENS_HIT_MEAN"] = pct(st.mean(float(STD[(c, 3, 4)].cache_hit_rate or 0) for c in sens_cases))
top10 = [c for _, c in sorted(((STD[(c, 2, 4)].makespan / STD[(c, 3, 4)].makespan, c) for c in CASES), reverse=True)[:10]]
F["SENS_TOP10_IN"] = str(sum(c in sens_cases for c in top10))

# ---------------------------------------------------------------------------
# 6. 与理论下界的距离（标准流程）。LB_N 由 bounds_cdf.csv 的 MK/LB 与 final.csv 反推
# ---------------------------------------------------------------------------
bc = pd.read_csv(R / "bounds_cdf.csv")
LB = {}
for r in bc.itertuples():
    LB[(r.case, r.problem, r.num_cores)] = FIN[(r.case, r.problem, r.num_cores)].makespan / r.mk_over_lb
for p in (1, 2, 3):
    for n in NS:
        ratios = [STD[(c, p, n)].makespan / LB[(c, p, n)] for c in CASES]
        up = [STD[(c, p, n)].baseline_makespan / LB[(c, p, n)] for c in CASES]
        frac = [STD[(c, p, n)].speedup / u for c, u in zip(CASES, up)]
        F[f"LB_P{p}_{n}"] = f"{st.mean(ratios):.2f} / {st.median(ratios):.2f}"
        F[f"LBFRAC_P{p}_{n}"] = pct(st.mean(frac), 0)
        if p == 2 and n == 4:
            F["LBMED_P2_4"] = f"{st.median(ratios):.2f}"
# ---------------------------------------------------------------------------
# 7. 择优规则与字典序目标的差异：标准流程只按 Makespan 择优（相同时取先评估者），
#    统计同 Makespan 候选中存在额外搬运量更小者的配置数
# ---------------------------------------------------------------------------
_mf = main[main.feasible.astype(str) == "True"]
_lex_n, _lex_tot = 0, 0
for _k, _g in _mf.groupby(["case", "problem", "num_cores"]):
    _b, _c = _g[_g.variant == "_best"], _g[_g.variant != "_best"]
    if _b.empty or _c.empty:
        continue
    _lex_tot += 1
    _mk = _c.makespan.min()
    if _b.iloc[0].makespan == _mk and _c[_c.makespan == _mk].added_copy_bytes.min() < _b.iloc[0].added_copy_bytes - 0.5:
        _lex_n += 1
F["LEX_TIE_N"], F["LEX_TIE_TOT"] = str(_lex_n), str(_lex_tot)
J["lex_tie"] = f"{_lex_n}/{_lex_tot}"
# case_016 略低于 1 的加速比（保留四位小数）
_lt1 = [STD[(c, p, n)].speedup for c in CASES for p in (1, 2, 3) for n in NS if STD[(c, p, n)].speedup < 1]
F["LT1_MIN4"] = f"{min(_lt1):.4f}" if _lt1 else "1.0000"
F["LT1_N"] = str(len(_lt1))
F["LT1_MAXLOSS"] = f"{100 * (1 - min(_lt1)):.2f}%" if _lt1 else "0.00%"

json.dump(J, open(OUT / "std_caliber.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
json.dump(F, open(OUT / "facts_v3.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("written", OUT)
for k in ("P1_MEAN_LIST", "P2_MEAN_LIST", "P3_MEAN_LIST", "OFF_P1_MEAN_LIST", "OFF_P2_MEAN_LIST",
          "OFF_P3_MEAN_LIST", "VSB4_P1_REL1", "VSB4_P2_REL1", "VSB4_P3_REL1", "VSB4_P1_WTL",
          "VSB4_P2_WTL", "VSB4_P3_WTL", "VSB4_P1_P", "VSB4_P2_P", "VSB4_P3_P", "P1_MONO_VIOL",
          "P2_MONO_VIOL", "P3_MONO_VIOL", "P1_LT1_ALL", "P2_LT1_ALL", "P3_LT1_ALL", "L2G_LIST",
          "L2SAME_LIST", "P3VSP2_FASTER", "P3VSP2_EQUAL", "P3VSP2_SLOWER", "P3SLOW_ALL_N",
          "P3SLOW_ALL_MAX", "P3SLOW_ALL_MAXC", "SAME_SLOW_N", "SAME_SLOW_MAX", "P2_SUPER_4",
          "P2_SUPER4_WITH_SPILL", "P2_SPILL_STD_N4", "HIT_RANGE", "LB_P2_4", "LBFRAC_P2_4"):
    print(k, "=", F.get(k))
print(json.dumps({k: v for k, v in J.items() if k.startswith("p") and "_n4" in k}, default=str))
