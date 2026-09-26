"""评估器执行轨迹甘特图（v3）：同一用例的“不分层”方案、分层方案与标准求解流程方案。

    python paper/v3/tools/trace_fig_v3.py [case]

由 solution/paper_v2/trace_fig.py 复制而来，差别：(c) 取标准求解流程方案
（paper/v3/data/final_standard.csv），面板标题不用千分位，输出写到 figures/v3 与
paper/v3/data/trace_stall_v3.json（不写 results/）。

用官方命令行评估器的 --trace-output 生成 Perfetto trace（写到临时目录，data/ 只读），
统计“四条流水同时空闲而该核仍有未完成算子”的区间（整核停摆），输出
（原脚本输出 figures/v2/fig_trace.png 与 results/trace_stall_v2.json。）
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "solution"))
sys.path.insert(0, str(ROOT / "solution" / "paper_v2"))

from npu import experiment, paths, variants  # noqa: E402

import matplotlib.pyplot as plt               # noqa: E402
from matplotlib.patches import Patch          # noqa: E402

import figstyle  # noqa: E402
from figstyle import PIPE_COL, RED, save, use_serif  # noqa: E402

figstyle.OUT = ROOT / "figures" / "v3"

PIPES = ("PIPE_MTE2", "PIPE_M", "PIPE_V", "PIPE_MTE3")


def run_trace(case, plan, tag, tmp):
    plan_path = Path(tmp) / f"{case}_{tag}_plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    trace = Path(tmp) / f"{case}_{tag}_trace.json"
    cmd = [sys.executable, str(paths.CODE_DIR / "multicore_cut_evaluate_problem_2.py"),
           str(paths.case_path(case)), str(plan_path), "--config", str(paths.CONFIG_PATH),
           "-o", str(Path(tmp) / f"{case}_{tag}_res.json"), "--trace-output", str(trace),
           "--log-output", str(Path(tmp) / f"{case}_{tag}_log.txt")]
    subprocess.run(cmd, check=True, capture_output=True, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    return json.loads(trace.read_text(encoding="utf-8"))


def core_spans(trace):
    names = {}
    for ev in trace["traceEvents"]:
        if ev.get("ph") == "M" and ev.get("name") == "thread_name":
            names[(ev["pid"], ev["tid"])] = ev["args"]["name"]
    out = {}
    for ev in trace["traceEvents"]:
        if ev.get("ph") != "X" or ev.get("cat") == "SUBGRAPH":
            continue
        core = ev["pid"] - 1000
        pipe = names.get((ev["pid"], ev["tid"]), ev.get("cat"))
        out.setdefault(core, {p: [] for p in PIPES}).setdefault(pipe, []).append((ev["ts"], ev["ts"] + ev["dur"]))
    return out


def stalls(spans):
    iv = sorted(x for lst in spans.values() for x in lst)
    if not iv:
        return []
    end_all = max(e for _, e in iv)
    gaps, cur = [], iv[0][0]
    for s, e in iv:
        if s > cur:
            gaps.append((cur, s))
        cur = max(cur, e)
    return [(a, b) for a, b in gaps if a < end_all and b > a]


def main():
    case = sys.argv[1] if len(sys.argv) > 1 else "case_003"
    final = {}
    import csv
    with open(ROOT / "paper" / "v3" / "data" / "final_standard.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            final[(r["case"], int(float(r["problem"])), int(float(r["num_cores"])))] = r
    g = experiment.get_graph(case)
    champ = final[(case, 2, 4)]
    # (a)(b) 只差“是否按 (核心, 层次) 成子图”一项（消融实验的 no_level / full 对）；(c) 为最终方案
    plans = [("不分层", variants.build(g, "a_no_level", 2, 4)),
             ("同步层次分层（分核与 (a) 相同）", variants.build(g, "a_full", 2, 4)),
             ("标准求解流程方案", json.loads((ROOT / champ["plan_path"].replace("\\", "/")).read_text(encoding="utf-8")))]
    tmp = Path(tempfile.gettempdir()) / "npu_trace_v3"
    tmp.mkdir(parents=True, exist_ok=True)
    use_serif()
    from matplotlib import font_manager as _fm
    if "SimSun" not in {f.name for f in _fm.fontManager.ttflist}:
        plt.rcParams["font.family"] = ["Times New Roman", "Liberation Serif", "Noto Serif CJK SC"]
    plt.rcParams.update({"axes.grid": False})
    fig, axes = plt.subplots(3, 1, figsize=(16 / 2.54, 10.6 / 2.54), sharex=True)
    report = {"case": case, "problem": 2, "num_cores": 4}
    xmax = 0
    for k, (tag, plan) in enumerate(plans):
        tr = run_trace(case, plan, f"v{k}", tmp)
        spans = core_spans(tr)
        mk = tr["otherData"]["makespan"]
        xmax = max(xmax, mk)
        st_all = {c: sum(b - a for a, b in stalls(sp)) for c, sp in spans.items()}
        busy = {c: {p: sum(e - s for s, e in sp.get(p, [])) for p in PIPES} for c, sp in spans.items()}
        report[tag] = {"makespan": mk, "stall_by_core": st_all, "stall_total": sum(st_all.values()),
                       "busy_by_core": busy}
        ax = axes[k]
        sp0 = spans.get(0, {})
        for i, p in enumerate(PIPES):
            ax.broken_barh([(s, e - s) for s, e in sp0.get(p, [])], (3 - i - 0.36, 0.72),
                           facecolors=PIPE_COL[p], linewidth=0)
        for a, b in stalls(sp0):
            ax.axvspan(a, b, color=RED, alpha=0.16, lw=0)
        ax.axvline(mk, color="black", lw=0.9, ls=(0, (3, 2)))
        ax.set_yticks([3, 2, 1, 0])
        ax.set_yticklabels(list(PIPES), fontsize=7.4)
        ax.set_title(f"({'abc'[k]}) {tag}：Makespan = {mk} cycle，四核整核停摆合计 "
                     f"{sum(st_all.values())} cycle", fontsize=8.4, loc="left")
        for sp_ in ("top", "right"):
            ax.spines[sp_].set_visible(False)
    axes[-1].set_xlabel("时间 / cycle")
    axes[-1].set_xlim(0, xmax * 1.02)
    axes[-1].legend(handles=[Patch(color=PIPE_COL[p], label=p) for p in PIPES]
                    + [Patch(color=RED, alpha=0.3, label="0 号核整核停摆区间")],
                    loc="upper center", bbox_to_anchor=(0.5, -0.5), ncol=5, fontsize=7.4)
    fig.tight_layout(h_pad=0.6)
    save(fig, "fig_trace")
    (ROOT / "paper" / "v3" / "data" / "trace_stall_v3.json").write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                                          encoding="utf-8")
    print(json.dumps({k: (v if not isinstance(v, dict) else {kk: vv for kk, vv in v.items() if kk != "busy_by_core"})
                      for k, v in report.items()}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
