#!/bin/bash
cd /c/Users/13985/Desktop/x
export PYTHONIOENCODING=utf-8
python -u solution/build_pool.py --jobs 16 > results/logs/T24_build_pool.log 2>&1 || { echo "STEP FAILED build_pool" >> results/logs/T24_done.log; exit 1; }
python -u solution/check_pool.py > results/logs/T24_check_pool.log 2>&1
python -u solution/make_report.py > results/logs/T24_make_report.log 2>&1
python -u solution/export_plans.py > results/logs/T24_export.log 2>&1 || { echo "STEP FAILED export_plans" >> results/logs/T24_done.log; exit 1; }
python -u solution/verify_final.py --problems 1 2 3 --jobs 16 > results/logs/T24_verify.log 2>&1
bash solution/finalize.sh > results/logs/T24_finalize.log 2>&1
python -u solution/digest.py > results/digest_final.txt 2>&1
echo "T24 PIPELINE DONE" >> results/logs/T24_done.log
