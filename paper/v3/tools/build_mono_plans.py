"""把"标准求解流程"补上单调性修复后的方案导出为官方格式，并用官方评估脚本逐个复核。

修复方式：不改变标准流程本身（不引入消融/基线/粒度实验的方案），只在
"整图单核"（N=1）与"标准流程自身在更少核数下的方案"之间，对每个 (用例, 问题, N)
取 Makespan 最小者；当最小者来自核数 k<N 时，直接在其 core_schedules 末尾
补 (N-k) 个空核心（不改变 node_to_subgraph 与已占用核心的调度，因此新增的空核
不引入任何新依赖或新搬运，方案本身仍合法）。这保证了加速比恒 >= 1 且随 N 单调不降。

    python paper/v3/tools/build_mono_plans.py                 # 写 results/final_plans_mono/
    python paper/v3/tools/build_mono_plans.py --verify --jobs 16   # 额外对补出的方案跑官方评估脚本复核

输出：results/final_plans_mono/p<problem>/n<N>/<case>_multicore_res.json
      results/final_plans_mono/manifest.csv（含 source 列：self / embed_from_k）
      --verify 时另写 results/verify_final_mono.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "solution"))

from npu import evaluate, experiment, paths, plots  # noqa: E402

OUT = paths.RESULTS_DIR / "final_plans_mono"


def load_n1():
    """case,problem -> (该问题官方评估的 N=1 Makespan, 固定加速比分母)。

    两者不同：分母是场景无关的整图单核基准（核内调度算法给出，同一用例的
    问题 1/2/3 共用同一个值）；N=1 的 Makespan 则按问题各自评估——问题三
    即使只有一个核心，只读 L2 仍可能命中，makespan 可以低于该分母。
    """
    n1 = {}
    for r in plots.read_csv("n1.csv"):
        if r.get("feasible"):
            n1[(r["case"], int(r["problem"]))] = (r["makespan"], r["baseline_makespan"])
    return n1


def load_std():
    """case,problem,num_cores -> (makespan, plan_path)，来自标准流程口径。"""
    std = {}
    with open(ROOT / "paper" / "v3" / "data" / "final_standard.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            p, n = int(float(r["problem"])), int(float(r["num_cores"]))
            std[(r["case"], p, n)] = (int(float(r["makespan"])), r["plan_path"].replace("\\", "/"))
    return std


def n1_plan(case):
    g = experiment.get_graph(case)
    return evaluate.make_plan({v: 0 for v in g.nodes}, [[0]])


def embed(plan, extra_cores):
    return evaluate.canonical_plan({
        "node_to_subgraph": plan["node_to_subgraph"],
        "core_schedules": [list(o) for o in plan["core_schedules"]] + [[] for _ in range(extra_cores)]})


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    std = load_std()
    n1_table = load_n1()
    cases = paths.all_cases()
    manifest = []
    to_verify = []
    for case in cases:
        base_plan = n1_plan(case)
        for p in (1, 2, 3):
            n1_mk, baseline_mk = n1_table[(case, p)]
            n1_mk, baseline_mk = int(n1_mk), int(baseline_mk)
            chain_mk = {1: n1_mk}
            chain_plan = {1: base_plan}
            for n in (2, 3, 4, 5):
                item = std.get((case, p, n))
                if item is None:
                    continue
                chain_mk[n] = item[0]
                chain_plan[n] = None  # 延迟加载
            for n in (1, 2, 3, 4, 5):
                if n not in chain_mk:
                    continue
                cand = [(k, chain_mk[k]) for k in range(1, n + 1) if k in chain_mk]
                best_k, best_mk = min(cand, key=lambda kv: kv[1])
                dst = OUT / f"p{p}" / f"n{n}"
                dst.mkdir(parents=True, exist_ok=True)
                dst_file = dst / f"{case}_multicore_res.json"
                if best_k == n == 1:
                    plan = base_plan
                    source = "self"
                elif best_k == n:
                    src = ROOT / std[(case, p, n)][1]
                    plan = json.loads(src.read_text(encoding="utf-8"))
                    source = "self"
                else:
                    if best_k == 1:
                        embed_src = base_plan
                    else:
                        src = ROOT / std[(case, p, best_k)][1]
                        embed_src = json.loads(src.read_text(encoding="utf-8"))
                    plan = embed(embed_src, n - best_k)
                    source = f"embed_from_{best_k}"
                    to_verify.append((p, case, n, best_mk))
                dst_file.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
                manifest.append({"case": case, "problem": p, "num_cores": n,
                                 "makespan": best_mk, "baseline_makespan": baseline_mk,
                                 "speedup": round(baseline_mk / best_mk, 4),
                                 "source": source, "source_n": best_k,
                                 "plan": str(dst_file.relative_to(ROOT))})
    experiment.write_csv(manifest, OUT / "manifest.csv")
    print(f"built {len(manifest)} plans -> {OUT}  ({len(to_verify)} are embedded, need verification)")
    return to_verify


def run_cli(problem, case, n, expected_mk, slot, tmpdir):
    plan = OUT / f"p{problem}" / f"n{n}" / f"{case}_multicore_res.json"
    out = Path(tmpdir) / f"slot{slot}_res.json"
    cmd = [sys.executable, str(paths.CODE_DIR / f"multicore_cut_evaluate_problem_{problem}.py"),
           str(paths.case_path(case)), str(plan), "--config", str(paths.CONFIG_PATH), "-o", str(out),
           "--trace-output", str(Path(tmpdir) / f"slot{slot}_trace.json"),
           "--log-output", str(Path(tmpdir) / f"slot{slot}_log.txt")]
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    secs = time.perf_counter() - t0
    if proc.returncode != 0 or not out.is_file():
        return {"case": case, "problem": problem, "num_cores": n, "ok": False,
                "error": (proc.stderr or proc.stdout)[-300:], "cli_seconds": round(secs, 1)}
    res = json.loads(out.read_text(encoding="utf-8"))
    got_mk = int(res["makespan"])
    return {"case": case, "problem": problem, "num_cores": n, "ok": got_mk == expected_mk,
            "expected_makespan": expected_mk, "cli_makespan": got_mk, "cli_seconds": round(secs, 1), "error": ""}


def verify(items, jobs):
    import tempfile
    rows = []
    with tempfile.TemporaryDirectory(dir=str(paths.RESULTS_DIR)) as tmpdir, \
            ProcessPoolExecutor(max_workers=jobs) as ex:
        futs = {ex.submit(run_cli, p, c, n, mk, i % jobs, tmpdir): (p, c, n)
                for i, (p, c, n, mk) in enumerate(items)}
        done = 0
        for fut in as_completed(futs):
            rows.append(fut.result())
            done += 1
            if done % 20 == 0 or done == len(items):
                bad = sum(1 for r in rows if not r["ok"])
                print(f"[verify-mono] {done}/{len(items)} mismatches={bad}", flush=True)
    experiment.write_csv(rows, paths.RESULTS_DIR / "verify_final_mono.csv")
    bad = [r for r in rows if not r["ok"]]
    print(f"checked={len(rows)} mismatches={len(bad)}")
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--jobs", type=int, default=8)
    args = ap.parse_args()
    to_verify = build()
    if args.verify and to_verify:
        bad = verify(to_verify, args.jobs)
        return 1 if bad else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
