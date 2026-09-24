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

## T02 口径改为算术平均 — 完成

* `plots.py`：新增 `amean`；图 5/6/8/10/11/13/14 的聚合改为算术平均，图题/轴标签同步；第 764/834 行附近（敏感性倍数、下界比值）保留几何平均，图 17 轴标签改为“几何平均，比值型指标”。
* `make_report.summary`：`baseline_speedup`、`ablation`、`l2_gain` 改为算术平均，另存 `*_geomean`；每个问题新增 `speedup_ci`（bootstrap 算术平均 95% 区间）、`speedup_by_strata`；新增 `paired`（N=4，CAP-LS 冠军 vs random/topo/balance/comm，完整 vs 各消融变体；a 为本文方法，每个问题内 Holm 校正，字段 `p_holm`）。
* `fill_paper.py`：主曲线改读 `speedup_mean`；新增 `P{p}_GEO_N{n}`、`P{p}_CI_N4`、`P{p}_SU_N4_STRATA`、`TABLE_PAIRED`（单元格用 Holm 校正后的 p）。
* `digest.py`：第 1 节标题与打印改为先 `mean=` 后 `geo=`。
* `SOLUTION.md`：主要结果表三行改为 `summary.json` 的 `speedup_mean`（原样 4 位小数）。L2 两行未在规格范围内，未改。
* 验收输出：
  * `problem2.speedup_mean = {'2': 1.8279, '3': 2.5975, '4': 3.2623, '5': 3.7943}`，与快照逐项相等（P1/P3 同样相等）。
  * `problem2.speedup_ci = {'2': [1.7569, 1.8957], '3': [2.4908, 2.6944], '4': [3.0888, 3.4231], '5': [3.5544, 4.0194]}`，全部包含均值。
  * `l2_gain = {'1': 1.0086, '2': 1.0058, '3': 1.0075, '4': 1.0255, '5': 1.0455}`；`'paired' in s` → `True`。
  * `fill_paper.py`：`filled 62 placeholders`，无未替换占位符。
  * `grep -n "geomean(" plots.py` → 第 93（def）、771（敏感性）、841（下界）行。
* 回归：P2 58984、P1 116868、搬运量 90/90 一致。
* 改动文件：`solution/npu/plots.py`、`solution/make_report.py`、`solution/fill_paper.py`、`solution/digest.py`、`SOLUTION.md`、`results/summary.json`、`figures/*.png`（12 张重绘）、`paper/论文_完整.md`（重新装配）。

## T03 分层抽样规则 — 完成

* 新建 `solution/sample_cases.py`，输出 `results/samples.json`（`pilot20`、`study30`、`l2_strata=[]`、`rule`）。样本内按用例名升序存储；JSON 以 ASCII 转义写出，使规格中不带 `encoding` 的 `json.load(open(...))` 在 Windows（GBK 默认编码）下也能读取。
* `solution/run_all.sh`：粒度与敏感性阶段的 `--cases` 改为 `$STUDY30`（一行 `python -c` 从 `samples.json` 读取）。
* 验收输出：`20 30 分层：按最大连通分量占比 ρmax 分为 rho<0.2 / 0.2<=rho<`；两次运行 md5 均为 `bae9323933e0bce56d31ea169fd0e184`。
* 分层核对：pilot20 = 12/2/6，study30 = 18/4/8；n_ops 最大的 `case_014`(35705)、`case_076`(32528)、`case_091`(31554) 均在 pilot20 中。
* pilot20：case_006 case_007 case_014 case_015 case_020 case_021 case_034 case_043 case_053 case_065 case_066 case_071 case_074 case_076 case_086 case_088 case_091 case_093 case_094 case_096。
* 回归：P2 58984、P1 116868、搬运量 90/90 一致。
* 改动文件：`solution/sample_cases.py`（新）、`results/samples.json`（新）、`solution/run_all.sh`。

## T05 变体方案生成器统一化 — 完成（提交顺序先于 T04）

* 说明：T05 仅依赖 T00；经用户确认，在 T04 全量运行（大图 P1 官方评估耗时数小时）期间先行提交 T05，T04 在运行结束后补提交。
* 新建 `solution/npu/variants.py`：`LABELS(problem, N)`（c0…c{k-1}、b_random/topo/balance/comm、a_full…a_no_level、g_0.03…g_2.0、single，顺序固定）、`label_params`、`ablation_plan`（原 `run_experiments.task_ablation` 第 157–180 行的构造逻辑原样迁入，含 `ABLATIONS` 表）、`build`（一律返回 `canonical_plan`）。
* `solution/run_experiments.py`：`ABLATIONS = variants.ABLATIONS`；`task_ablation` 改为调用 `variants.ablation_plan`，评估由 `evaluate.evaluate_plan(...)` 改为 `evaluate.default_cache().evaluate(...)`（0.1 第 4 条）。
* 新建 `solution/check_variants.py`（保留在仓库）。
* 验收输出：
  ```
  case_001: 31 labels, 12 portfolio candidates compared
  case_016: 31 labels, 8 portfolio candidates compared
  case_044: 31 labels, 12 portfolio candidates compared
  ALL OK
  ```
  （case_016 有 17995 个算子，现行 run_portfolio 对 n>6000 只保留前 8 个候选，故比较 8 个。）
* 回归：P2 58984、P1 116868、搬运量 90/90 一致。
* 改动文件：`solution/npu/variants.py`（新）、`solution/check_variants.py`（新）、`solution/run_experiments.py`。
