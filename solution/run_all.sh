#!/usr/bin/env bash
# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Sonnet 5（型号 claude-sonnet-5）、Claude Opus 5.5（型号 claude-opus-5-5）
# 开发机构：Anthropic 公司
# 版本发布日期：Claude Sonnet 5 为 2026-06-30，Claude Opus 5.5 为 2026-09-22
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

# 分层抽样的 study30 子集（由 solution/sample_cases.py 生成，规则见 results/samples.json 的 rule 字段）
STUDY30=$(python -c "import json;print(' '.join(json.load(open('results/samples.json'))['study30']))")

# 6) 切图粒度敏感性（子集）
run granularity --stage granularity --problems 1 2 3 --cores 4 \
    --cases $STUDY30 \
    --out results/granularity.csv

# 7) 硬件参数敏感性（研究性，不用于正式成绩）
run sensitivity --stage sensitivity --cores 4 \
    --cases $STUDY30 \
    --out results/sensitivity.csv

echo "=== $(date +%H:%M:%S)  all stages done ===" | tee -a "$LOG"
