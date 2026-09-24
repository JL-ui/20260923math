#!/usr/bin/env bash
# 实验跑完后的一键收尾：图表 → 表格 → 正文数字 → 拼装 → Word → 方案导出
set -u
cd "$(dirname "$0")/.."

echo "== 1/5 生成图表、附录表格与正文数字 =="
python -u solution/make_report.py

echo "== 2/5 拼装完整论文 =="
python -u solution/assemble_paper.py

echo "== 3/5 注入实验数字 =="
python -u solution/fill_paper.py paper/论文_完整.md || true

echo "== 4/5 导出 Word =="
python -u solution/md2docx.py paper/论文_完整.md -o paper/论文.docx

echo "== 5/5 导出最终方案文件 =="
python -u solution/export_plans.py

echo "done. 交付物见 SOLUTION.md"
