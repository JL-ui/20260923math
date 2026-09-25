"""从 results/ 提取论文正文用到的全部数字，写入 results/facts_v2.json。

    python solution/paper_v2/facts.py

论文源文件 paper/v2/论文_完善版.md 里的 @@KEY@@ 全部由这里给出；
build_docx.py 遇到未定义的键会直接报错，因此正文不存在手工填写的实验数字。
每个数字的来源写在同一行的注释里（文件 + 字段/口径）。
"""

from __future__ import annotations

import csv
import glob
import json
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
R = ROOT / "results"
F: dict[str, str] = {}


def rj(name):
    return json.loads((R / name).read_text(encoding="utf-8"))


def rcsv(name):
    with open(R / name, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def f2(x):
    return f"{x:.2f}"


def f3(x):
    return f"{x:.3f}"


def pct(x, d=1):
    return f"{100 * x:.{d}f}%"


def spct(x, d=1):
    """带符号百分比，负号用 U+2212。"""
    s = f"{100 * x:+.{d}f}%"
    return s.replace("-", "−")


def sci(x, d=2):
    """1.70×10^{9} 形式（LaTeX，放在 $ $ 里用）"""
    if x == 0:
        return "0"
    import math
    e = int(math.floor(math.log10(abs(x))))
    m = x / 10 ** e
    return f"{m:.{d}f}\\times10^{{{e}}}"


def pval(p):
    import math
    if p >= 0.001:
        return f"{p:.3f}"
    e = int(math.floor(math.log10(p)))
    m = p / 10 ** e
    return f"{m:.1f}\\times10^{{{e}}}"


S = rj("summary.json")
final = rcsv("final.csv")
n1 = rcsv("n1.csv")
feats = {r["case"]: r for r in rj("features.json")}
for r in final:
    r["problem"] = int(r["problem"])
    r["num_cores"] = int(r["num_cores"])
    r["makespan"] = int(r["makespan"])
    r["speedup"] = float(r["speedup"])
    r["added_copy_bytes"] = int(float(r["added_copy_bytes"] or 0))
    r["partition_added_copy_bytes"] = int(float(r["partition_added_copy_bytes"] or 0))
    r["spill_added_copy_bytes"] = int(float(r["spill_added_copy_bytes"] or 0))
    r["n_subgraphs"] = int(r["n_subgraphs"])
FIN = {(r["case"], r["problem"], r["num_cores"]): r for r in final}
N1 = {(r["case"], int(r["problem"])): r for r in n1}
CASES = sorted({r["case"] for r in final})
NS = [2, 3, 4, 5]


def sp(p, n):
    return [FIN[(c, p, n)]["speedup"] for c in CASES]


# ----------------------------------------------------------------------------
# 一、主结果（final.csv；加速比按赛题取算术平均）
# ----------------------------------------------------------------------------
for p in (1, 2, 3):
    key = f"problem{p}"
    means = []
    for n in NS:
        xs = sp(p, n)
        m = st.mean(xs)
        means.append(m)
        F[f"P{p}_MEAN_{n}"] = f2(m)                                     # 平均加速比
        F[f"P{p}_MEAN3_{n}"] = f3(m)
        lo, hi = S[key]["speedup_ci"][str(n)]                           # summary.json bootstrap CI
        F[f"P{p}_CI_{n}"] = f"[{lo:.2f}, {hi:.2f}]"
        F[f"P{p}_GEO_{n}"] = f2(S[key]["speedup_geomean"][str(n)])
        F[f"P{p}_MED_{n}"] = f2(st.median(xs))
        F[f"P{p}_MIN_{n}"] = f2(min(xs))
        F[f"P{p}_MAX_{n}"] = f2(max(xs))
        F[f"P{p}_SUPER_{n}"] = str(sum(1 for x in xs if x > n + 1e-9))   # 超线性用例数
        F[f"P{p}_EFF_{n}"] = f"{100 * m / n:.0f}%"                      # 并行效率 = 均值 / N
    F[f"P{p}_MEAN_LIST"] = "、".join(f2(x) for x in means)
    # 逐用例单调性：MK_N <= MK_{N-1}
    viol = 0
    for c in CASES:
        prev = int(N1[(c, p)]["makespan"])
        for n in NS:
            mk = FIN[(c, p, n)]["makespan"]
            viol += mk > prev
            prev = mk
    F[f"P{p}_MONO_VIOL"] = str(viol)
    # N=4 最差用例
    worst = sorted(((FIN[(c, p, 4)]["speedup"], c) for c in CASES))[:6]
    F[f"P{p}_WORST_N4"] = "、".join(f"{c}（{s:.2f}）" for s, c in worst)
    # 额外搬运（N=4）
    rows4 = [FIN[(c, p, 4)] for c in CASES]
    tot = sum(r["added_copy_bytes"] for r in rows4)
    part = sum(r["partition_added_copy_bytes"] for r in rows4)
    spill = sum(r["spill_added_copy_bytes"] for r in rows4)
    F[f"P{p}_ADDED_N4"] = sci(tot)
    F[f"P{p}_CUTSHARE_N4"] = pct(part / (part + spill))
    F[f"P{p}_SPILLSHARE_N4"] = pct(spill / (part + spill))
    F[f"P{p}_ZERO_ADDED_N4"] = str(sum(1 for r in rows4 if r["added_copy_bytes"] == 0))
    F[f"P{p}_SUBG_MED_N4"] = f"{st.median(r['n_subgraphs'] for r in rows4):g}"
    F[f"P{p}_SUBG_MED_ALL"] = f"{st.median(FIN[(c, p, n)]['n_subgraphs'] for c in CASES for n in NS):g}"

F["P1_MEAN_N1"] = "1.00"
F["N_CASES"] = str(len(CASES))
F["N_FINAL"] = str(len(final))                                          # 1200
F["N_FINAL_ALL"] = str(len(final) + len(n1))                            # 含 N=1 共 1500

# 超线性（问题二）
F["P2_SUPER4_N4"] = F["P2_SUPER_4"]
F["P2_SUPER2_N2"] = F["P2_SUPER_2"]

# ----------------------------------------------------------------------------
# 二、单核基准与数据特征（features.json、singlecore_baseline.json）
# ----------------------------------------------------------------------------
sc = rj("singlecore_baseline.json")
spills = {c: sc[c]["spill_added_copy_bytes"] for c in sc}
F["SC_SPILL_CASES"] = str(sum(1 for v in spills.values() if v > 0))    # 单核基准有换入换出的用例数
F["SC_SPILL_TOTAL"] = sci(sum(spills.values()))
F["SC_SPILL_MAX"] = sci(max(spills.values()))
sup4 = [c for c in CASES if FIN[(c, 2, 4)]["speedup"] > 4]
F["P2_SUPER4_WITH_SPILL"] = str(sum(1 for c in sup4 if spills.get(c, 0) > 0))
p2rows4 = [FIN[(c, 2, 4)] for c in CASES]
F["P2_ADDED_VS_SC"] = f"{100 * sum(r['added_copy_bytes'] for r in p2rows4) / sum(spills.values()):.0f}%"


def q(vals, fmt):
    vals = sorted(vals)
    return fmt(vals[0]), fmt(st.median(vals)), fmt(vals[-1])


fe = list(feats.values())
rows_feat = {
    "NOPS": ([r["n_ops"] for r in fe], lambda x: f"{x:g}"),
    "DEPTH": ([r["depth"] for r in fe], lambda x: f"{x:g}"),
    "WIDTH": ([r["avg_width"] for r in fe], lambda x: f"{x:.1f}"),
    "COMP": ([r["n_components"] for r in fe], lambda x: f"{x:g}"),
    "RHO": ([r["largest_component_frac"] for r in fe], lambda x: f"{x:.3f}"),
    "CPR": ([r["critical_path_cycles"] / r["total_cycles"] for r in fe], lambda x: f"{x:.4f}"),
    "CDDR": ([max(r["pipe_m_cycles"], r["pipe_v_cycles"]) / r["ddr_time_lb"] for r in fe], lambda x: f"{x:.1f}"),
    "UBP": ([r["ub_pressure"] for r in fe], lambda x: f"{x:.1f}"),
}
for k, (vals, fmt) in rows_feat.items():
    a, b, c = q(vals, fmt)
    F[f"FT_{k}_MIN"], F[f"FT_{k}_MED"], F[f"FT_{k}_MAX"] = a, b, c
F["FT_COMP40"] = str(sum(1 for r in fe if r["n_components"] >= 40))
F["FT_ONECOMP"] = str(sum(1 for r in fe if r["n_components"] == 1))
F["FT_RHO05"] = str(sum(1 for r in fe if r["largest_component_frac"] > 0.5))
F["FT_RHO02"] = str(sum(1 for r in fe if r["largest_component_frac"] < 0.2))
c16 = feats["case_016"]
F["C16_NOPS"] = str(c16["n_ops"])
F["C16_DEPTH"] = str(c16["depth"])
F["C16_WIDTH"] = f"{c16['avg_width']:.1f}"
F["C16_PAR"] = f"{c16['total_cycles'] / c16['critical_path_cycles']:.1f}"
F["C16_P2_N4"] = f2(FIN[("case_016", 2, 4)]["speedup"])
F["C16_P1_N4"] = f2(FIN[("case_016", 1, 4)]["speedup"])
F["NOPS_MIN"] = F["FT_NOPS_MIN"]

# 结构分层（summary.json speedup_by_strata）
for p in (1, 2, 3):
    for s_key, tag in (("rho<0.2", "A"), ("0.2<=rho<0.5", "B"), ("rho>=0.5", "C")):
        d = S[f"problem{p}"]["speedup_by_strata"]["4"][s_key]
        F[f"P{p}_STR{tag}_N"] = str(d["n"])
        F[f"P{p}_STR{tag}_MEAN"] = f2(d["amean"])
        F[f"P{p}_STR{tag}_MED"] = f2(d["median"])
        F[f"P{p}_STR{tag}_MIN"] = f2(d["min"])

# 结构特征与加速比的相关性（问题二 N=4）
try:
    from scipy import stats as sst
    y = [FIN[(c, 2, 4)]["speedup"] for c in CASES]
    for k, fn in (("RHO", lambda r: r["largest_component_frac"]),
                  ("CPR", lambda r: r["critical_path_cycles"] / r["total_cycles"]),
                  ("WIDTH", lambda r: r["avg_width"]),
                  ("NOPS", lambda r: r["n_ops"])):
        x = [fn(feats[c]) for c in CASES]
        import math
        xl = [math.log10(v) if k in ("WIDTH", "NOPS") else v for v in x]
        F[f"CORR_{k}_P"] = f"{sst.pearsonr(xl, y)[0]:+.2f}".replace("-", "−")
        F[f"CORR_{k}_S"] = f"{sst.spearmanr(x, y)[0]:+.2f}".replace("-", "−")
except Exception as e:  # pragma: no cover
    print("相关性计算失败", e)

# ----------------------------------------------------------------------------
# 三、问题一：求解时间、候选裁剪、退火、兜底
# ----------------------------------------------------------------------------
main = rcsv("main.csv")
# 端到端 = 全部候选的构造时间 + 官方评估时间 + 问题一退火时间（退火耗时记在 sa 行 params 里，每配置一次）
agg = defaultdict(lambda: [0.0, 0.0])
anneal_done = set()
for r in main:
    if r["variant"] == "_best":
        continue
    key = (r["case"], int(r["problem"]), int(r["num_cores"]))
    rt = float(r["runtime_s"] or 0)
    ev = float(r["eval_s"] or 0)
    agg[key][0] += rt + ev
    agg[key][1] += rt
    if r["variant"].startswith("sa") and key not in anneal_done:
        try:
            a_s = float(json.loads(r["params"] or "{}").get("anneal_seconds", 0))
        except Exception:
            a_s = 0.0
        agg[key][0] += a_s
        agg[key][1] += a_s
        anneal_done.add(key)
for p in (1, 2, 3):
    tots = [v[0] for k, v in agg.items() if k[1] == p]
    noev = [v[1] for k, v in agg.items() if k[1] == p]
    tots.sort()
    F[f"P{p}_RT_MED"] = f"{st.median(tots):.1f}"
    F[f"P{p}_RT_P90"] = f"{tots[int(0.9 * (len(tots) - 1))]:.0f}"
    F[f"P{p}_RT_LE5"] = str(sum(1 for t in tots if t <= 300))
    F[f"P{p}_RT_LE10"] = str(sum(1 for t in tots if t <= 600))
    F[f"P{p}_RT_NOEV_MED"] = f"{st.median(noev):.1f}"
    F[f"P{p}_RT_NOEV_LE10"] = str(sum(1 for t in noev if t <= 600))
    F[f"P{p}_RT_CFG"] = str(len(tots))
    F[f"P{p}_RT_MAX"] = f"{max(tots):.0f}"
over = sorted({k[0] for k, v in agg.items() if k[1] == 1 and v[0] > 600})
# 仅网格候选 c0～c17 由官方择优（即 solve.py 的口径），N=4
grid_best = defaultdict(float)
for r in main:
    v = r["variant"]
    if v.startswith("c") and v[1:].isdigit() and r["feasible"] == "True" and r["speedup"]:
        key = (r["case"], int(r["problem"]), int(r["num_cores"]))
        grid_best[key] = max(grid_best[key], float(r["speedup"]))
for p in (1, 2, 3):
    vals = [grid_best[(c, p, 4)] for c in CASES if (c, p, 4) in grid_best]
    F[f"GRID_P{p}_N4"] = f2(st.mean(vals))
F["P1_RT_OVER_CASES"] = str(len(over))
F["P1_RT_OVER_LIST"] = "、".join(c.replace("case_", "") for c in over)
rt = S["runtime"]
F["ALG_RT_MED"] = f"{rt['median']:.2f}"
F["ALG_RT_N"] = f"{rt['n']:,}"
F["ALG_RT_P95"] = f"{rt['p95']:.1f}"
F["ALG_RT_MAX"] = f"{rt['max']:.1f}"
F["EVAL_MAX"] = f"{S['eval_time']['max']:.0f}"
# 候选按规模裁剪（问题一）
n_small = sum(1 for r in fe if r["n_ops"] <= 6000)
n_mid = sum(1 for r in fe if 6000 < r["n_ops"] <= 12000)
n_big = sum(1 for r in fe if r["n_ops"] > 12000)
F["P1_PRUNE_SMALL"], F["P1_PRUNE_MID"], F["P1_PRUNE_BIG"] = str(n_small), str(n_mid), str(n_big)
big4 = ["case_014", "case_072", "case_076", "case_091"]
v4 = [FIN[(c, 1, 4)]["speedup"] for c in big4]
F["BIG4_N4_MIN"], F["BIG4_N4_MAX"] = f2(min(v4)), f2(max(v4))
an = rj("p1_anneal_report.json")
F["SA_ITERS"] = str(an["anneal_iters"])
F["SA_MED_S"] = f"{an['anneal_seconds']['median']:.1f}"
F["SA_MAX_S"] = f"{an['anneal_seconds']['max']:.0f}"
F["SA_OVER60"] = str(an["anneal_seconds"]["configs_over_limit"])
F["SA_CHAMP_MAIN"] = str(an["sa_champion_configs_main"])
src = Counter()
for r in final:
    v = r["variant"].replace("pool:", "")
    if v.startswith("sa"):
        cat = "sa"
    elif v.startswith("s") and v[1:].isdigit():
        cat = "samp"
    elif v.startswith("c") and v[1:].isdigit():
        k = int(v[1:])
        cat = "grid_a" if k <= 11 else ("grid_b" if k <= 13 else "grid_op")
    elif v.startswith("cross_from_p"):
        cat = "cross"
    elif v.startswith("embed_n"):
        cat = "embed"
    elif v.startswith("a_"):
        cat = "abl"
    elif v.startswith("g_"):
        cat = "gran"
    elif v.startswith("b_"):
        cat = "base"
    elif v.startswith("single"):
        cat = "single"
    else:
        cat = "other:" + v
    src[(r["problem"], cat)] += 1
for p in (1, 2, 3):
    for cat in ("grid_a", "grid_b", "grid_op", "samp", "sa", "abl", "gran", "base", "embed", "cross", "single"):
        val = src.get((p, cat), 0)
        F[f"SRC_P{p}_{cat.upper()}"] = str(val) if (val or cat not in ("grid_op", "samp", "sa")) else "—"
F["SA_FINAL"] = str(src.get((1, "sa"), 0))
F["CROSS_P2"] = str(src.get((2, "cross"), 0))
F["CROSS_P3"] = str(src.get((3, "cross"), 0))
F["POOL_ROWS"] = f"{sum(1 for _ in open(R / 'pool.csv', encoding='utf-8')) - 1:,}"

# 官方评估次数（正式配置的方案哈希缓存条目）
tot = 0
for p in ("p1", "p2", "p3"):
    for fpath in glob.glob(str(R / "cache" / p / "*.json")):
        tot += len(json.loads(Path(fpath).read_text(encoding="utf-8")))
F["TOTAL_EVALS"] = f"{tot:,}"

# 最终方案官方 CLI 复核
vf = rcsv("verify_final.csv")
F["VERIFY_N"] = str(len(vf))
F["VERIFY_MISMATCH"] = str(sum(1 for r in vf if r["match"] != "True"))

# 搬运量解析模型检验
tm = rcsv("traffic_model_check.csv")
F["TRAFFIC_N"] = str(len(tm))
F["TRAFFIC_CASES"] = str(len({r["case"] for r in tm}))
F["TRAFFIC_MAXERR"] = f"{100 * max(float(r['rel_err']) for r in tm):.4f}%"

# ----------------------------------------------------------------------------
# 四、问题二：表调度、采样、超线性
# ----------------------------------------------------------------------------
op = rj("op_mode_report.json")
F["OP_TOTAL"] = str(op["op_candidates_total"])
F["OP_FEAS"] = str(op["op_candidates_feasible"])
F["OP_CHAMP"] = str(op["op_champion_configs"])
F["SPILL_BEFORE"] = sci(op["p2_n4_spill_champions_before_T11"])
F["SPILL_AFTER"] = sci(op["p2_n4_spill_champions_after_T11"])
F["SPILL_DROP"] = f"{100 * op['spill_drop_frac']:.0f}%"
mu = op["mu1_vs_mu0_paired"]
F["C14C16_REL"] = spct(mu["rel"])
F["C14C16_WTL"] = f"{mu['win']}/{mu['tie']}/{mu['loss']}"
F["C14C16_N"] = str(mu["n"])
F["C14C16_P"] = pval(mu["p"])
sm = rj("sampling_report.json")
F["SAMP_EVALS"] = f"{sm['new_official_evals']:,}"
F["SAMP_CHAMP"] = str(sm["champion_s_configs"])
F["SAMP_P2_N4_K0"] = f2(sm["by_K"]["0"]["P2_N4"])
F["SAMP_P2_N4_K16"] = f2(sm["by_K"]["16"]["P2_N4"])
F["SAMP_P3_N4_K0"] = f2(sm["by_K"]["0"]["P3_N4"])
F["SAMP_P3_N4_K16"] = f2(sm["by_K"]["16"]["P3_N4"])

# ----------------------------------------------------------------------------
# 五、问题三：L2
# ----------------------------------------------------------------------------
gains = {}
for n in [1] + NS:
    g = []
    for c in CASES:
        if n == 1:
            a, b = int(N1[(c, 2)]["makespan"]), int(N1[(c, 3)]["makespan"])
        else:
            a, b = FIN[(c, 2, n)]["makespan"], FIN[(c, 3, n)]["makespan"]
        g.append((a / b, c))
    gains[n] = g
    F[f"L2G_{n}"] = f3(st.mean(x for x, _ in g))                         # 最终方案口径
    F[f"L2G_GT1_{n}"] = str(sum(1 for x, _ in g if x > 1.01))
    mx = max(g)
    F[f"L2G_MAX_{n}"] = f2(mx[0])
    F[f"L2G_MAXC_{n}"] = mx[1]
    F[f"L2G_MAXCS_{n}"] = mx[1].replace("case_", "")
    if n == 1:
        hits = [float(N1[(c, 3)]["cache_hit_rate"] or 0) for c in CASES]
    else:
        hits = [float(FIN[(c, 3, n)]["cache_hit_rate"] or 0) for c in CASES]
    F[f"HIT_{n}"] = pct(st.mean(hits))
    F[f"HIT_NZ_{n}"] = str(sum(1 for h in hits if h > 0))
    F[f"L2SAME_{n}"] = f3(S["l2_gain"][str(n)])                          # 同一方案口径
    F[f"P3_MEANN_{n}"] = f2(st.mean(int(N1[(c, 2)]['makespan']) / int((N1[(c, 3)] if n == 1 else FIN[(c, 3, n)])['makespan'])
                                    for c in CASES)) if n == 1 else F[f"P3_MEAN_{n}"]
F["L2G_LIST"] = "、".join(F[f"L2G_{n}"] for n in [1] + NS)
F["HIT_RANGE"] = f"{F['HIT_1']}～{F['HIT_5']}"
F["P3_MEAN_1"] = f2(st.mean(int(N1[(c, 1)]["makespan"]) / int(N1[(c, 3)]["makespan"]) for c in CASES))
# 问题三 vs 问题二冠军（N=4）
fa = sum(1 for c in CASES if FIN[(c, 3, 4)]["makespan"] < FIN[(c, 2, 4)]["makespan"])
eq = sum(1 for c in CASES if FIN[(c, 3, 4)]["makespan"] == FIN[(c, 2, 4)]["makespan"])
F["P3VSP2_FASTER"], F["P3VSP2_EQUAL"] = str(fa), str(eq)
F["P3VSP2_SLOWER"] = str(len(CASES) - fa - eq)
exc = rj("pool_condition4_exceptions.json")
F["P3EXC_N"] = str(exc["count"])
F["P3EXC_MAXREL"] = f"{100 * exc['max_rel_observed']:.4f}%"
e0, e1 = exc["exceptions"][0], exc["exceptions"][1]
F["P3EXC_1"] = f"{e0['case']}（$N={e0['num_cores']}$，{e0['p3_makespan']} 对 {e0['p2_makespan']}）"
F["P3EXC_2"] = f"{e1['case']}（$N={e1['num_cores']}$，{e1['p3_makespan']} 对 {e1['p2_makespan']}）"
ls = rj("l2_sources.json")["by_n"]["4"]
F["HIT_INPUT_N4"] = pct(ls["hit_input_reuse"] / ls["official_hit_bytes"])
F["HIT_CROSS_N4"] = pct(ls["hit_cross_core_mid"] / ls["official_hit_bytes"])
F["MISS_FIRST_N4"] = pct(ls["miss_first_miss"] / ls["official_miss_bytes"])
F["MISS_CONC_N4"] = pct(ls["miss_concurrent_first_read"] / ls["official_miss_bytes"])
F["MISS_FIFO_N4"] = pct(ls["miss_fifo_evicted"] / ls["official_miss_bytes"])
F["MISS_AVOID_N4"] = pct((ls["miss_concurrent_first_read"] + ls["miss_fifo_evicted"]) / ls["official_miss_bytes"], 0)
# 敏感性（18 个用例，N=4，几何平均 MK_default / MK_knob）
sens = rcsv("sensitivity.csv")
bykn = defaultdict(dict)
for r in sens:
    if r["feasible"] != "True":
        continue
    bykn[(r["knob"], r["case"])][float(r["value"])] = int(r["makespan"])
import math
sens_cases = sorted({r["case"] for r in sens})
F["SENS_CASES"] = str(len(sens_cases))
defaults = {"bandwidth": 60, "L1": 524288, "UB": 131072, "cache_capacity_bytes": 1048576,
            "cache_bandwidth_bytes_per_cycle": 250, "cross_core_copy_delay_cycles": 500,
            "task_cross_core_wait_cycles": 1000}
SENS = {}
for knob, dv in defaults.items():
    vals = sorted({v for (k, c), d in bykn.items() if k == knob for v in d})
    for v in vals:
        rs = []
        for c in sens_cases:
            d = bykn.get((knob, c), {})
            if dv in d and v in d:
                rs.append(math.log(d[dv] / d[v]))
        if rs:
            SENS[(knob, v)] = math.exp(st.mean(rs))
for (knob, v), g in SENS.items():
    F[f"SENS_{knob}_{int(v)}"] = f3(g)
l2s = set(rj("samples.json")["l2_strata"])
top10 = [c for _, c in sorted(gains[4], reverse=True)[:10]]
F["SENS_TOP10_IN"] = str(sum(1 for c in top10 if c in sens_cases))
F["SENS_HIT_MEAN"] = pct(st.mean(float(FIN[(c, 3, 4)]["cache_hit_rate"] or 0) for c in sens_cases))
F["L2_COEF_250"] = f"{100 * (1 - 60 / 250):.0f}%"
F["L2_COEF_125"] = f"{100 * (1 - 60 / 125):.0f}%"
F["L2_DT_COEF"] = f"{1 / 60 - 1 / 250:.4f}"

# ----------------------------------------------------------------------------
# 六、基线、消融、粒度、下界、代理
# ----------------------------------------------------------------------------
bs = S["baseline_speedup"]
paired = S["paired"]
for p in (1, 2, 3):
    b = bs[f"p{p}_n4"]
    for k, tag in (("random", "B1"), ("topo", "B2"), ("balance", "B3"), ("comm", "B4")):
        F[f"BASE_P{p}_{tag}"] = f2(b[k])
    d = paired[f"problem{p}"]["capls_vs_comm"]
    F[f"VSB4_P{p}_REL"] = spct(d["rel"], 0)
    F[f"VSB4_P{p}_WTL"] = f"{d['win']}/{d['tie']}/{d['loss']}"
    F[f"VSB4_P{p}_P"] = pval(d["p_holm"])
    for k in ("random", "topo", "balance"):
        d = paired[f"problem{p}"][f"capls_vs_{k}"]
        F[f"VS{k.upper()}_P{p}_REL"] = spct(d["rel"], 0)
F["BASE_RANDOM_P1_N4"] = F["BASE_P1_B1"]
ba = S["baseline_added_total"]
F["BASE_ADDED_P2N4_B3"] = sci(ba["p2_n4"]["balance"])
F["BASE_ADDED_P2N4_B4"] = sci(ba["p2_n4"]["comm"])
F["BASE_ADDED_P1N4_B3"] = sci(ba["p1_n4"]["balance"])
# 消融（ablation2：N=2..5 配对，相对 full_c2）
ab = S["ablation2"]
for p in (1, 2, 3):
    d = ab[f"problem{p}"]
    base = d["full_c2"]["describe"]["amean"]
    F[f"ABL_P{p}_BASE"] = f3(base)
    F[f"ABL_P{p}_NCASE"] = str(d["full_c2"]["describe"]["n"] // 4)
    for v in ("no_level", "no_comm", "no_level_no_comm", "no_sync", "no_localsearch", "max_ops500",
              "lvl_alap", "lvl_compress", "op_full", "op_mu0", "op_nu0", "op_alpha1"):
        if v in d and "paired" in d[v]:
            pr = d[v]["paired"]
            F[f"ABL_P{p}_{v.upper()}"] = spct(pr["rel"])
            F[f"ABLP_P{p}_{v.upper()}"] = pval(pr["p_holm"])
            F[f"ABLW_P{p}_{v.upper()}"] = f"{pr['win']}/{pr['tie']}/{pr['loss']}"
        else:
            F[f"ABL_P{p}_{v.upper()}"] = "—"
            F[f"ABLP_P{p}_{v.upper()}"] = "—"
# 表调度内部消融（相对 op_full）：直接由 ablation2.csv 配对计算
abl_rows = rcsv("ablation2.csv")
byv = defaultdict(dict)
for r in abl_rows:
    if r["feasible"] == "True" and r["speedup"]:
        byv[(int(r["problem"]), r["variant"])][(r["case"], int(r["num_cores"]))] = float(r["speedup"])
try:
    from scipy.stats import wilcoxon
    for p in (2, 3):
        basev = byv[(p, "op_full")]
        ps = []
        for v in ("op_mu0", "op_nu0", "op_alpha1"):
            other = byv[(p, v)]
            keys = sorted(set(basev) & set(other))
            a = [other[k] for k in keys]
            b = [basev[k] for k in keys]
            rel = st.mean(a) / st.mean(b) - 1
            pv = wilcoxon(a, b).pvalue if any(x != y for x, y in zip(a, b)) else 1.0
            ps.append((v, rel, pv))
        # Holm 校正（每个问题三个比较）
        order = sorted(ps, key=lambda t: t[2])
        adj = {}
        running = 0
        m = len(order)
        for i, (v, rel, pv) in enumerate(order):
            running = max(running, min(1.0, (m - i) * pv))
            adj[v] = running
        for v, rel, pv in ps:
            F[f"OPABL_P{p}_{v.upper()}"] = spct(rel)
            F[f"OPABLP_P{p}_{v.upper()}"] = pval(adj[v])
except Exception as e:  # pragma: no cover
    print("表调度消融计算失败", e)
# c2 单一配置相对 B4（同一批用例）
for p in (1, 2, 3):
    c2 = ab[f"problem{p}"]["full_c2"]["by_n"]["4"]
    F[f"C2_P{p}_N4"] = f2(c2)
base_rows = rcsv("baseline.csv")
b4 = {(r["case"], int(r["problem"]), int(r["num_cores"])): float(r["speedup"])
      for r in base_rows if r["algorithm"] == "comm" and r["feasible"] == "True"}
for p in (1, 2, 3):
    c2v = byv[(p, "full_c2")]
    keys = [k for k in c2v if k[1] == 4 and (k[0], p, 4) in b4]
    a = st.mean(c2v[k] for k in keys)
    b = st.mean(b4[(k[0], p, 4)] for k in keys)
    F[f"C2VSB4_P{p}"] = spct(a / b - 1)
    F[f"C2VSB4_P{p}_B4"] = f2(b)
F["P2_C2_TO_FINAL"] = f"{F['C2_P2_N4']} 到 {F['P2_MEAN_4']}"
# 粒度（granularity.csv，study30 中 29 个用例，N=4，算术平均）
gr = rcsv("granularity.csv")
gm = defaultdict(list)
for r in gr:
    if r["feasible"] == "True":
        gm[(int(r["problem"]), float(r["variant"]))].append(float(r["speedup"]))
F["GRAN_CASES"] = str(len({r["case"] for r in gr}))
for p in (1, 2, 3):
    betas = sorted(b for (pp, b) in gm if pp == p)
    means = {b: st.mean(gm[(p, b)]) for b in betas}
    best = max(means, key=means.get)
    F[f"GRAN_P{p}_BEST"] = f"{best:g}"
    F[f"GRAN_P{p}_BESTV"] = f2(means[best])
    F[f"GRAN_P{p}_FINEV"] = f2(means[min(betas)])
    F[f"GRAN_P{p}_FINELOSS"] = pct(1 - means[min(betas)] / means[best])
    mid = [means[b] for b in betas if 0.12 <= b <= 0.5]
    F[f"GRAN_P{p}_SWING"] = pct(max(mid) / min(mid) - 1)
    for b in betas:
        F[f"GRAN_P{p}_{str(b).replace('.', '_')}"] = f2(means[b])
# 下界
bd = rj("bounds.json")
for p in (1, 2, 3):
    for n in NS:
        d = bd["ratio"][f"p{p}_n{n}"]
        F[f"LB_P{p}_{n}"] = f"{d['amean']:.2f} / {d['median']:.2f}"
        F[f"LBMED_P{p}_{n}"] = f2(d["median"])
        e = bd["efficiency"][f"p{p}_n{n}"]
        F[f"LBEFF_P{p}_{n}"] = f"{100 * e['amean']:.0f}%"
for n in NS:
    F[f"LB_ACH_{n}"] = f2(bd["upper_bound"][f"p2_n{n}"]["speedup_upper"]["amean"])      # 可达加速比上界 MK1/LB_N
    for p in (1, 2, 3):
        F[f"LBFRAC_P{p}_{n}"] = f"{100 * bd['upper_bound'][f'p{p}_n{n}']['fraction_of_upper']['amean']:.0f}%"
F["SC_VS_LB_MED"] = f2(bd["single_over_lb1_median"])
# 代理
for tag, fn in (("SIM", "model_validation_summary_sim.json"), ("LEG", "model_validation_summary_legacy.json")):
    d = rj(fn)
    for p in (1, 2, 3):
        x = d[f"problem{p}"]
        F[f"PX_{tag}_P{p}_SP"] = f2(x["spearman_median"])
        F[f"PX_{tag}_P{p}_KD"] = f2(x["kendall_median"])
        F[f"PX_{tag}_P{p}_R1"] = f"{100 * x['recall1']:.0f}%"
        F[f"PX_{tag}_P{p}_R3"] = f"{100 * x['recall3']:.0f}%"
        F[f"PX_{tag}_P{p}_T3"] = f"{100 * x['top3_slowdown_p90']:.1f}%"
pa = rj("portfolio_analysis.json")
ps_ = pa["proxy_selection"]
for p in (1, 2, 3):
    d = ps_[f"P{p}"]
    F[f"PXSEL_P{p}"] = f2(d["proxy_only_amean"])
    F[f"PXOFF_P{p}"] = f2(d["official_main_amean"])
    F[f"PXLOSS_P{p}"] = spct(d["proxy_only_amean"] / d["official_main_amean"] - 1)
    F[f"PXWORSE_P{p}"] = str(d["proxy_vs_official_main"]["loss"])
gr_ = pa["greedy"]
F["GREEDY_P1_1"] = f3(gr_["P1"][0]["amean"])
F["GREEDY_P1_4"] = f3(gr_["P1"][3]["amean"])
F["GREEDY_P1_ALL"] = f3(gr_["P1"][-1]["amean"])
F["GREEDY_P1_K"] = str(len(gr_["P1"]))
F["GREEDY_P2_1"] = f3(gr_["P2"][0]["amean"])
F["GREEDY_P2_4"] = f3(gr_["P2"][3]["amean"])
F["GREEDY_P2_ALL"] = f3(gr_["P2"][-1]["amean"])
F["GREEDY_P2_K"] = str(len(gr_["P2"]))
cv = rj("cv_select.json")
F["CV_LOSS_MAX"] = pct(cv["cv_loss_max"])
rels = [cv["problems"][f"problem{p}"][fold]["block_cap_rel_vs_default"]
        for p in (1, 2, 3) for fold in ("train_A", "train_B")]
F["CV_BETA_MIN"] = spct(min(rels))
F["CV_BETA_MAX"] = spct(max(rels))

# 官方 trace：不分层方案 vs 最终方案（trace_fig.py 生成）
tr_path = R / "trace_stall_v2.json"
if tr_path.exists():
    tr = rj("trace_stall_v2.json")
    a = tr["不分层"]
    b = tr["同步层次分层（分核与 (a) 相同）"]
    c = tr["最终方案"]
    F["TRACE_CASE"] = tr["case"]
    F["TRACE_MK_A"] = f"{a['makespan']:,}"
    F["TRACE_MK_B"] = f"{b['makespan']:,}"
    F["TRACE_MK_C"] = f"{c['makespan']:,}"
    F["TRACE_MK_DROP"] = pct(1 - b["makespan"] / a["makespan"])
    F["TRACE_ST_A"] = f"{a['stall_total']:,}"
    F["TRACE_ST_B"] = f"{b['stall_total']:,}"
    F["TRACE_ST_C"] = f"{c['stall_total']:,}"
    F["TRACE_ST_DROP"] = pct(1 - b["stall_total"] / a["stall_total"], 0)
    F["TRACE_ST_SHARE_A"] = pct(a["stall_total"] / (4 * a["makespan"]))

# 杂项
F["SINGLE_CFG_RT_MED"] = F["ALG_RT_MED"]

out = R / "facts_v2.json"
out.write_text(json.dumps(F, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
print(f"写出 {len(F)} 个数字 -> {out}")
