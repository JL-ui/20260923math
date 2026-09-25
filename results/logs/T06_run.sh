#!/bin/bash
cd /c/Users/13985/Desktop/x
export PYTHONIOENCODING=utf-8
python -u solution/run_experiments.py --stage main --jobs 16 --problems 2 3 --out results/main_p23.csv > results/logs/T06_main.log 2>&1 || echo "MAIN FAILED rc=$?" >> results/logs/T06_main.log
python -u solution/run_experiments.py --stage p3 --jobs 16 --out results/p3_compare.csv > results/logs/T06_p3.log 2>&1 || echo "P3 FAILED rc=$?" >> results/logs/T06_p3.log
python -u solution/merge_main.py > results/logs/T06_merge.log 2>&1
echo "T06 DONE" >> results/logs/T06_merge.log
