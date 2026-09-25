#!/bin/bash
cd /c/Users/13985/Desktop/x
export PYTHONIOENCODING=utf-8
python -u solution/run_experiments.py --stage main --jobs 16 --problems 1 --out results/main_p1_sa.csv > results/logs/T14_main.log 2>&1 || { echo "MAIN FAILED rc=$?" >> results/logs/T14_main.log; exit 1; }
python -u solution/merge_main.py --p1 results/main_p1_sa.csv --p23 results/main_p23.csv > results/logs/T14_merge.log 2>&1 || exit 1
python -u solution/build_pool.py --jobs 16 > results/logs/T14_build_pool.log 2>&1 || exit 1
python -u solution/p1_anneal_report.py > results/logs/T14_report.log 2>&1
echo "T14 PIPELINE DONE" >> results/logs/T14_report.log
