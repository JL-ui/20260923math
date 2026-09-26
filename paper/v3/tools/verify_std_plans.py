"""对“标准求解流程”口径的方案做官方 CLI 复核。

复用 solution/verify_final.py 的并发与比对逻辑，只把方案目录与期望值换成
export_std_plans.py 导出的目录（默认 results/final_plans_std/ 及其 manifest.csv）；
结果默认写 results/verify_final_std.csv，不覆盖 results/verify_final.csv。

    python paper/v3/tools/export_std_plans.py
    python paper/v3/tools/verify_std_plans.py --problems 2 3 --jobs 16
    python paper/v3/tools/verify_std_plans.py --problems 1 --jobs 16
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "solution"))

import verify_final as vf                # noqa: E402
from npu import paths, plots             # noqa: E402

PLANS = paths.RESULTS_DIR / "final_plans_std"


def expected_values():
    exp = {}
    with (PLANS / "manifest.csv").open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            hit = r.get("cache_hit_rate")
            exp[(r["case"], int(r["problem"]), int(r["num_cores"]))] = {
                "makespan": int(r["makespan"]),
                "added_copy_bytes": int(r["added_copy_bytes"]),
                "cache_hit_rate": float(hit) if hit not in (None, "", "None") else None}
    for r in plots.read_csv("n1.csv"):
        if r["feasible"]:
            exp[(r["case"], int(r["problem"]), 1)] = {
                "makespan": r["makespan"],
                "added_copy_bytes": r["added_copy_bytes"],
                "cache_hit_rate": r.get("cache_hit_rate")}
    return exp


def run_cli(problem, case, n, slot, tmpdir):
    plan = PLANS / f"p{problem}" / f"n{n}" / f"{case}_multicore_res.json"
    out = Path(tmpdir) / f"slot{slot}_res.json"
    cmd = [sys.executable, str(paths.CODE_DIR / f"multicore_cut_evaluate_problem_{problem}.py"),
           str(paths.case_path(case)), str(plan), "--config", str(paths.CONFIG_PATH),
           "-o", str(out),
           "--trace-output", str(Path(tmpdir) / f"slot{slot}_trace.json"),
           "--log-output", str(Path(tmpdir) / f"slot{slot}_log.txt")]
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    secs = time.perf_counter() - t0
    if proc.returncode != 0 or not out.is_file():
        return {"error": (proc.stderr or proc.stdout)[-300:], "cli_seconds": round(secs, 1)}
    res = json.loads(out.read_text(encoding="utf-8"))
    return {"makespan": int(res["makespan"]),
            "added_copy_bytes": int(res["data_movement_bytes"]["added_copy_bytes"]),
            "cache_hit_rate": (float(res["cache_stats"]["hit_rate"]) if problem == 3 else None),
            "cli_seconds": round(secs, 1), "error": ""}


def main():
    global PLANS
    argv = sys.argv[1:]
    if "--plans" in argv:                      # 可选：指定其他方案目录
        i = argv.index("--plans")
        PLANS = Path(argv[i + 1]).resolve()
        del argv[i:i + 2]
    if "--out" not in argv:
        argv += ["--out", str(paths.RESULTS_DIR / "verify_final_std.csv")]
    sys.argv = [sys.argv[0]] + argv
    vf.expected_values = expected_values
    vf.run_cli = run_cli
    return vf.main()


if __name__ == "__main__":
    raise SystemExit(main())
