#!/usr/bin/env bash
# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Sonnet 5（型号 claude-sonnet-5）、Claude Opus 5.5（型号 claude-opus-5-5）
# 开发机构：Anthropic 公司
# 版本发布日期：Claude Sonnet 5 为 2026-06-30，Claude Opus 5.5 为 2026-09-22
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
