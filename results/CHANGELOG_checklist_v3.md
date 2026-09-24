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

## T06 P2/P3 取消大图候选裁剪并重跑 — 完成

* `solution/npu/experiment.py` `run_portfolio`：`level == 'auto'` 只在 `problem == 1` 时按图规模降级为 `'fast'`，否则恒为 `'full'`；`n > 6000` 的候选裁剪只对 `problem == 1` 生效。
* `solution/solve.py`：`solve()` 同步只对 `problem == 1` 用 `fast`/`grid[:8]`。
* `solution/merge_main.py`（新）：取备份的 P1 行 + 新跑的 P2/P3 行，写回 `main.csv`。
* 运行：备份 `results/baseline_snapshot/main_before_T06.csv`；`run_experiments.py --stage main --problems 2 3`（10400 行）；`--stage p3`（首次 500 任务中 1 个因并发写临时文件冲突失败——`OSError [Errno 22]`，与本任务改动无关，属瞬时 I/O 竞争；完整重跑一次，500/500 全部成功，5800 行）；`merge_main.py`。
* 验收：
  * P2/P3 每配置候选数最小值 = 12（完整候选集长度）。
  * P2/P3 端到端最长时间（`runtime_s+eval_s`）= 273.3 s（case_091 P3 N=2），≤ 600 s。
  * 800 个 P2/P3 配置：0 个变差，69 个变好（新增大图候选带来的改进）。
  * P1 行数 4464 == 备份中的 4464（未受影响）。
* 回归：P2 58984、P1 116868、搬运量 90/90 一致。
* 改动文件：`solution/npu/experiment.py`、`solution/solve.py`、`solution/merge_main.py`（新）、`results/main.csv`、`results/main_p23.csv`（新）、`results/p3_compare.csv`、`results/baseline_snapshot/main_before_T06.csv`（新）。

## T04 代理检验改用用例内指标 — 完成

* 说明：因 T04 全量运行耗时较长（100 用例 × 4 核数 × 3 问题，大图 P1 官方评估单次可达 1800+ s），经用户确认与 T05/T06 并行执行；本节记录其结果，提交顺序落在 T05、T06 之后。
* `solution/validate_model.py`：
  - 新增 `--all`（全部 100 用例 × N=2,3,4,5）、`--proxy {legacy,sim}`；
  - `--proxy sim` 时 `_estimate` 调用 `npu.simproxy.estimate`（T10 模块，本任务只预留调用点，未随本次提交引入 `simproxy.py`）；
  - 新增 `within_case_report(rows)`：组内候选按 makespan 去重后计算 Spearman/Kendall（`scipy.stats.spearmanr/kendalltau`，组内候选 <3 跳过）、Top-K（1/3/5）减速比、Recall@K；`pooled_spearman` 作为混合秩相关附带输出；
  - 结果写 `results/model_validation_summary_<proxy>.json`，`--all` 时 CSV 默认改名为 `results/model_validation_full_<proxy>.csv`；
  - 任务队列按图规模降序提交，缩短大图 P1 长尾对总墙钟时间的影响；命中率 < 100% 时会在未命中处触发官方评估，评估后立即 `flush()`（原代码只在全部完成后统一 flush，大图 P1 单次评估耗时远超单进程崩溃/重启窗口，逐条落盘避免重算）。
* 命令：`python solution/validate_model.py --all --proxy legacy --jobs 16`。
* 验收：
  - `results/model_validation_summary_legacy.json` 存在，`coverage=1.0`（100 × 4 × 3 = 1200 组全部覆盖，≥95% 要求）；
  - N=4、前 40 个用例子集：P2 用例内 Spearman 中位数 = **0.4512**，落在 0.43–0.53 区间内（基底清单核实值 0.48）；
  - 全量指标：P1 Spearman 中位 0.9429／Recall@3 92.25%；P2 0.4555／58%；P3 0.4492／58%。
* 回归：P2 58984、P1 116868、搬运量 90/90 一致。
* 改动文件：`solution/validate_model.py`、`results/model_validation_summary_legacy.json`（新）、`results/model_validation_full_legacy.csv`（新）。

## 提交顺序说明

T04 全量运行与 T05/T06 的代码修改、实验重跑在时间上重叠（经用户确认并行执行以缩短总时长）。
实际提交顺序为 T00 → T01 → T02 → T03 → **T05 → T06** → **T04**，晚于规格 0.4 节列出的编号顺序，
但每个任务的验收与改动范围保持独立、互不依赖：T05 只依赖 T00，T06 只依赖 T05，T04 只依赖 T01、T03。
T06 提交后发现遗漏了 `run_experiments.py --stage main/p3` 重跑产生的 `results/plans/*_best.json`
更新（该阶段默认 `save_plan=True`），已用 `git commit --amend` 补入同一次 T06 提交，未产生额外提交记录。

## T07 保底池 — 完成（验收条件 4 经用户确认放宽为"至多 7 个已理解例外"）

* 新建 `solution/build_pool.py`：对每个 (用例, 问题, N) 按 T05 的 `variants.LABELS` 重建全部标签
  （问题 2 另加 `x3_c*`：问题 3 候选参数、问题 2 评估），问题 2/3 一律走 `default_cache().evaluate`；
  问题 1 缓存未命中时按"是否在 main/baseline/ablation/granularity 中有同配置记录且优于当前
  main.csv 冠军"剪枝（`p1_pruned_labels`），命中记录一律与 CSV 逐位核对，不等写入
  `results/pool_mismatch.csv` 且不入池；N≥3 做 N−1 嵌入（`embed_n{N-1}`）；单核兜底仅在当前最优
  加速比 < 1.0 时评估；同一 N 内 P2/P3 完成后做跨问题互投（`cross_from_p2`/`cross_from_p3`）。
  输出 `results/final.csv`（冠军）、`results/pool.csv`（全部候选）、
  `results/plans_final/<case>_p<problem>_n<N>.json`。
* 新建 `solution/check_pool.py`：5 条验收，全部满足打印 `POOL OK`。
* `solution/make_report.py`：新增 `_champion_csv()`（`final.csv` 存在则用它，否则回退 `main.csv`）；
  `appendix_tables` 新增 `final_mode` 参数（`final.csv` 存在时问题 3 也从冠军表取，不再依赖
  `p3_compare.csv`）；`summary` 增加 `run_rows` 参数，运行时间统计固定读原始 `main.csv`；
  `main()` 中表格/正文数字改读 `final.csv`（存在时），图表调用改传 `main_csv=champ_csv`。
* `solution/export_plans.py`：`results/final.csv` 存在时只读它（`plan_path` 已指向
  `results/plans_final/...`），不再合并 `main.csv`+`p3_compare.csv`。
* `solution/digest.py`：`main_rows` 优先读 `final.csv`。
* **验收条件 4 的表述变更**（用户明确指示）：原表述"每个用例、每个 N：问题 3 冠军
  makespan ≤ 问题 2 冠军 makespan"（无例外）改为"……，至多 7 个已理解例外，每个例外
  必须附物理机制说明且相对偏差 ≤ 1%"。变更原因：直接用官方评估器复核发现，
  同一方案在问题 3（带只读 L2）下的 Makespan 有极小概率高于同一方案在问题 2（无 L2）
  下的 Makespan——问题 3 的 FIFO 淘汰顺序取决于 COPY_IN 完成时刻，而命中比未命中更快
  且不占 DDR 带宽池，会改变后续 COPY_IN 的相对完成顺序，个别情况下让一次本可命中的
  读取因张量被提前淘汰而变成未命中；若该算子在关键路径上，问题 3 Makespan 会略高于
  问题 2。已用 `evaluate_plan(2,...)`/`evaluate_plan(3,...)` 直接复核同一方案确认
  （例：case_002 N=5 某方案 P2=55382、P3=55399），排除了本项目 `cross_from_p2` 互投构造
  或代码逻辑的问题——`cross_from_p2` 本身就是"用问题 3 评估问题 2 冠军的原始方案"，
  已是这一比较能达到的最优形式，无法通过增加候选来消除。
  实际结果：400 个 (用例, N) 配置中 7 个违反，相对偏差 0.001%–0.31%（见
  `results/pool_condition4_exceptions.json`，含逐条机制说明与数值）。
* 验收输出：
  ```
  condition 4: 7 known exception(s) (max rel 0.3136%) -> results/pool_condition4_exceptions.json
  summary problem2 speedup_mean N=5 = 3.9885 (OK)
  POOL OK
  ```
  其余 4 条（1200 行全可行、加速比≥1.0、N 单调不增、冠军不劣于五张参照 CSV 的已知最优）
  全部无例外通过。
* 运行：`python solution/build_pool.py --jobs 16`（100 用例，2715 s ≈ 45 分钟；最大用例 case_014
  单案例 2714 s，主要花在 N−1 嵌入与跨问题互投对大图 P1 的官方评估）；
  `make_report.py --tables --figures`；`export_plans.py`（导出 1500 个方案文件：
  100×3 问题×N=2..5 的 1200 个冠军 + 100×3 问题×N=1 的 300 个单核方案）。
* 回归：P2 58984、P1 116868、搬运量 90/90 一致。
* 改动文件：`solution/build_pool.py`（新）、`solution/check_pool.py`（新）、
  `solution/make_report.py`、`solution/export_plans.py`、`solution/digest.py`、
  `results/final.csv`（新）、`results/pool.csv`（新）、`results/pool_mismatch.csv`（新，空表）、
  `results/pool_condition4_exceptions.json`（新）、`results/plans_final/`（新，1200 个方案）、
  `results/final_plans/`（更新为 1500 个方案 + `manifest.csv`）、`results/summary.json`、
  `paper/tables/*`、`figures/*`（12 张重绘）。
