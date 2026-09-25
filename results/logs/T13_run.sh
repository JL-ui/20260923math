#!/bin/bash
cd /c/Users/13985/Desktop/x
export PYTHONIOENCODING=utf-8
python -u solution/run_experiments.py --stage main --jobs 16 --problems 2 3 --out results/main_p23.csv > results/logs/T13_main.log 2>&1 || { echo "MAIN FAILED rc=$?" >> results/logs/T13_main.log; exit 1; }
python -u solution/run_experiments.py --stage p3 --jobs 16 --out results/p3_compare.csv > results/logs/T13_p3.log 2>&1 || { echo "P3 FAILED rc=$?" >> results/logs/T13_p3.log; exit 1; }
python -u solution/merge_main.py --p1 results/main_p1_sa.csv --p23 results/main_p23.csv > results/logs/T13_merge.log 2>&1 || exit 1
python -u solution/build_pool.py --jobs 16 > results/logs/T13_build_pool.log 2>&1 || exit 1
python -u solution/check_pool.py > results/logs/T13_check_pool.log 2>&1
python -u solution/sampling_report.py > results/logs/T13_report.log 2>&1
echo "T13 PIPELINE DONE" >> results/logs/T13_report.log
