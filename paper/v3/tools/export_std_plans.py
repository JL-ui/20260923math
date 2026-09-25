"""导出“标准求解流程”口径的方案文件（与修订稿正文、附录 A 的数字一一对应）。

与 solution/export_plans.py 的区别：方案取自 paper/v3/data/final_standard.csv
（即 results/main.csv 中每个配置由标准流程选出的方案），不含消融、基线、粒度等
检验实验产生的方案。默认写到 results/final_plans_std/，不覆盖现有的 results/final_plans/。

    python paper/v3/tools/export_std_plans.py [--out results/final_plans_std]
    # 逐个复核示例
    python code/multicore_cut_evaluate_problem_2.py data/case_001.json \
           results/final_plans_std/p2/n4/case_001_multicore_res.json --config data/config.txt
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "solution"))

from npu import evaluate, experiment, paths  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "results" / "final_plans_std"))
    args = ap.parse_args()
    out_root = Path(args.out).resolve()
    manifest = []
    with open(ROOT / "paper" / "v3" / "data" / "final_standard.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            p, n = int(float(r["problem"])), int(float(r["num_cores"]))
            src = ROOT / r["plan_path"].replace("\\", "/")
            dst = out_root / f"p{p}" / f"n{n}" / f"{r['case']}_multicore_res.json"
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            manifest.append({"case": r["case"], "problem": p, "num_cores": n,
                             "makespan": int(float(r["makespan"])), "speedup": r["speedup"],
                             "added_copy_bytes": r["added_copy_bytes"],
                             "cache_hit_rate": r["cache_hit_rate"], "variant": r["variant"],
                             "plan": str(dst.relative_to(ROOT) if dst.is_relative_to(ROOT) else dst)})
    for case in paths.all_cases():            # N=1：整图一个子图
        plan = evaluate.make_plan({v: 0 for v in experiment.get_graph(case).nodes}, [[0]])
        for p in (1, 2, 3):
            d = out_root / f"p{p}" / "n1"
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{case}_multicore_res.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    experiment.write_csv(manifest, out_root / "manifest.csv")
    print(f"exported {len(manifest)} plans -> {out_root}")


if __name__ == "__main__":
    main()
