# CHANGELOG — 实验综合改进清单 v3（分支 improve/checklist-v3）

规格：`TaskSpec.md`（2026-09-24）。每个任务一个提交，提交信息 `T<编号>: <任务名>`。

## 执行偏离（全局）

* **0.3 回归检查中的官方 CLI 调用加了 `--trace-output`、`--log-output`，指向 `%TEMP%`。**
  规格原命令未指定这两项，官方 `contest_io._common_paths` 会把
  `case_001_problem_{1,2}_{trace.json,log.txt}` 写进 `data/`：既违反 0.1 第 1 条（`data/` 只读），
  又会被 `paths.all_cases()`（glob `case_*.json`）当成用例读入，导致
  `check_traffic_model.py` 报 `KeyError: 'ops'`。首次运行产生的 4 个文件已由用户手工删除，
  用户确认“继续”后采用此重定向。T08、T22 调用官方 CLI 时同样处理。

## T00 环境与基线快照 — 完成

* 新建 `requirements.txt`：`numpy==2.4.4`、`scipy==1.17.1`、`matplotlib==3.10.8`、`python-docx==1.1.0`。
* `results/baseline_snapshot/`：`summary.json`、`main.csv`、`p3_compare.csv`、`manifest.csv`，与原文件逐字节相同（`filecmp` 输出 `True`）。
* 验收输出：`ok`。
* 回归：`r_p2_res.json makespan 58984`，`r_p1_res.json makespan 116868`，`逐位一致 90/90；最大相对误差 0.0000%`。
* 改动文件：`requirements.txt`（新）、`results/baseline_snapshot/*`（新）、`results/CHANGELOG_checklist_v3.md`（新）。

## T01 统计模块 — 完成

* 新建 `solution/npu/stats.py`：`amean`、`gmean`、`bootstrap_ci`（`random.Random(20260924)`，百分位区间）、`paired`（Wilcoxon，`zero_method='wilcox'`；全零差值时 p=1.0）、`holm`、`strata`、`describe`。
* 验收输出：
  * `{'amean': 2.5, 'gmean': 2.2134, 'median': 2.5, 'min': 1.0, 'max': 4.0, 'p90': 3.7, 'n': 4, 'ci_lo': 1.5, 'ci_hi': 3.5}`
  * `{'n': 2, 'win': 1, 'tie': 1, 'loss': 0, 'mean_a': 1.5, 'mean_b': 1.0, 'rel': 0.5, 'p': 1.0}`
  * `from solution.npu import stats` 与 `cd solution && from npu import stats` 两种导入均可用。
* 回归：P2 58984、P1 116868、搬运量 90/90 一致。
* 改动文件：`solution/npu/stats.py`（新）。
