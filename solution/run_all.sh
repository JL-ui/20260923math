#!/usr/bin/env bash
# 一键复现全部实验（顺序执行，避免超订 CPU）。
# 用法： bash solution/run_all.sh [jobs]
set -u
cd "$(dirname "$0")/.."
JOBS=${1:-16}
LOG=results/run_all.log
: > "$LOG"

run () {
  echo "=== $(date +%H:%M:%S)  stage=$1 ===" | tee -a "$LOG"
  shift
  python -u solution/run_experiments.py --jobs "$JOBS" "$@" 2>&1 | tee -a "$LOG"
}

# 0) 单核基准（若未算过）
python -u solution/run_singlecore.py --jobs "$JOBS" >> "$LOG" 2>&1

# 1) N=1 参考点（问题 1/2/3 下的整图单 Task 评估）
run n1        --stage n1

# 2) 主算法：3 个问题 × N=2..5 × 11 个候选
run main      --stage main --level auto

# 3) 问题 3 对照：同一方案在 无 L2 / 只读 Cache 下评估
run p3        --stage p3 --out results/p3_compare.csv

# 4) 基线算法
run baseline  --stage baseline

# 5) 消融
run ablation  --stage ablation

# 6) 切图粒度敏感性（子集）
run granularity --stage granularity --problems 1 2 3 --cores 4 \
    --cases case_001 case_003 case_005 case_007 case_009 case_012 case_014 \
            case_016 case_019 case_020 case_024 case_025 case_028 case_030 \
            case_040 case_047 case_050 case_062 case_071 case_080 case_085 \
            case_088 case_092 case_097 case_100 \
    --out results/granularity.csv

# 7) 硬件参数敏感性（研究性，不用于正式成绩）
run sensitivity --stage sensitivity --cores 4 \
    --cases case_001 case_003 case_005 case_007 case_009 case_012 case_016 \
            case_019 case_020 case_024 case_025 case_047 case_062 case_071 \
            case_085 case_088 case_097 case_100 \
    --out results/sensitivity.csv

echo "=== $(date +%H:%M:%S)  all stages done ===" | tee -a "$LOG"
