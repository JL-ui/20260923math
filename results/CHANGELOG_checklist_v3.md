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

## T08 最终方案官方 CLI 复核 — 完成

* 新建 `solution/verify_final.py`：对 `results/final_plans/p<P>/n<N>/<case>_multicore_res.json`
  （N=1..5）逐个用 `subprocess` 调用官方 CLI（`code/multicore_cut_evaluate_problem_<P>.py`），
  trace/log 显式指定到系统临时目录（避免写入只读的 `data/`），按并发槽位复用临时文件；
  读取 makespan、`data_movement_bytes.added_copy_bytes`、（问题 3）`cache_stats.hit_rate`
  与 `results/final_plans/manifest.csv`（N≥2）/`results/n1.csv`（N=1）逐项比较，命中率
  比较到 1e-9。输出 `results/verify_final.csv` 与 `checked=<数量> mismatches=<数量>`。
* 命令：
  - `python solution/verify_final.py --problems 2 3 --jobs 16` → `checked=1000 mismatches=0`（130 s）。
  - `python solution/verify_final.py --problems 1 --jobs 16`（用户确认后执行）→
    `checked=500 mismatches=0`（1868 s ≈ 31 分钟；P1 官方 CLI 对大图较慢，最大用例
    单次可达数百秒）。
* 验收：两次 `mismatches=0`；`checked` 分别为 `2×100×5=1000` 与 `100×5=500`，与规格一致。
* 回归：P2 58984、P1 116868、搬运量 90/90 一致。
* 改动文件：`solution/verify_final.py`（新）、`results/verify_final.csv`（新）。

## T09 逐字节等价快速评估器 — 完成（范围经用户二次收窄）

* **范围变更**（用户明确指示，替换本任务开始前"完全跳过 T09"的建议）：不再对 pilot20
  全部候选做穷尽差分测试；改为先实测定位 P1 端到端耗时 > 600s（10 分钟）的用例
  （`results/p1_slow_cases.txt`：12 个用例、30 个 (用例,N) 组合，耗时来自 `main.csv`
  问题 1 候选行 `runtime_s+eval_s` 求和），只在这些大图上验证与优化；P1 中小图与全部
  P2/P3 维持直接用官方评估器 + 缓存，不接入 `evaluate_fast`。
* 新建 `solution/npu/fasteval/`：`code/` 下 9 个官方评估模块的原样复制（`fe_` 前缀 +
  相对导入，唯一允许的非性能改动），另加 `__init__.py`。
* 性能优化（class (c)：把"固定顺序线性全量扫描判断是否完成"换成单调指针，扫描顺序
  不变、判定结果逐位相同）：
  - `fe_multicore_cut_evaluate_problem_1.py`：Task 完成检测（原 `all(op_status[item]=='done' for item in task_items)`）；
  - `fe_schedule_step3.py`：全局完成检测（原 `all(status=='done' for status in op_status.values())`）。
  两处都只影响"何时判定已完成"的检测方式，不改变任何算子的发射顺序、时长或依赖判定。
* `solution/npu/evaluate.py` 新增 `evaluate_fast(problem, case, plan)`，返回结构与
  `evaluate_plan` 相同，内部调用 `fasteval` 副本。
* `solution/npu/experiment.py` `run_portfolio`：`problem==1` 且 `NPU_FASTEVAL=1` 时，
  新增 `_fasteval_portfolio`：全部候选先用 `evaluate_fast` 打分选冠军，只对冠军调用
  一次 `default_cache().evaluate`（官方）核实；官方值与快速值不等则记录到
  `results/fasteval_mismatch.csv` 并回退为官方评估全部候选；`NPU_FASTEVAL=1` 时同时
  取消 T06 保留的 P1 大图候选裁剪（跑满候选网格）。
* 验证（8 个候选，覆盖 12 个慢用例中的 6 个、n_ops∈[10070,35705]、N∈{2,3,4,5}）：
  ```
  case_014 N=2: official(cached)=30.0s  fast=5.29s  speedup=5.7x   equal=True
  case_014 N=5: official(cached)=1588.0s fast=5.93s speedup=267.7x equal=True
  case_076 N=3: official(cached)=67.2s  fast=8.18s  speedup=8.2x   equal=True
  case_091 N=4: official(cached)=1150.3s fast=9.87s speedup=116.5x equal=True
  case_072 N=2: official(cached)=46.4s  fast=6.78s  speedup=6.8x   equal=True
  case_030 N=2: official(cached)=20.5s  fast=1.78s  speedup=11.5x  equal=True
  case_041 N=3: official(cached)=273.3s fast=4.22s  speedup=64.7x  equal=True
  case_092 N=2: official(cached)=22.4s  fast=3.11s  speedup=7.2x   equal=True
  ALL EQUAL；geomean speedup 21.9x
  ```
  完整记录见 `results/fasteval_slow_case_verification.json`。
* 端到端集成测试：`NPU_FASTEVAL=1` 下对 case_014（最大图、原 4-候选耗时 5757–6329s）
  跑满 12 候选的 `run_portfolio`，216.8 s 完成，无 mismatch，冠军 makespan 与原结果一致
  （3722693）——候选数增加 3 倍、总耗时仍缩短约 27 倍。
* 未触发"否则方案"（代理模型 Top-1 直选）：class (c) 优化已达到"分钟级压到秒级"的目标，
  未出现逐字节不一致，无需降级到代理直选。
* 回归：P2 58984、P1 116868、搬运量 90/90 一致。
* 改动文件：`solution/npu/fasteval/`（新，9 个模块 + `__init__.py`，2 个文件含 class (c) 优化）、
  `solution/npu/evaluate.py`（新增 `evaluate_fast`）、`solution/npu/experiment.py`
  （`run_portfolio` 接入 `NPU_FASTEVAL`）、`solution/check_fasteval.py`（新，通用差分测试工具，
  本次未做穷尽运行）、`results/p1_slow_cases.txt`（新）、
  `results/fasteval_slow_case_verification.json`（新）。

## T10 算子级事件模拟代理 — 完成

* 新建 `solution/npu/simproxy.py`：`estimate(g, plan, problem, cfg) -> float`。
  - 问题 1：子图即 Task，直接调用 `validate_model.estimate_scene_a_from_plan`（与旧代理共用同一 Task 激活规则，故 P1 指标与旧代理逐位一致）；
  - 问题 2/3：核内算子序列 = 方案核内子图顺序 + 子图内按 `g.topo` 位置排序；图输入张量每核首次使用前插入 MTE2，跨核边在生产核最后一次生产后插入 MTE3、消费核首次使用前插入 MTE2（就绪时间 = 对端完成 + `cross_core_copy_delay_cycles`）；四条流水各自串行，计算时长 = `cycles`，搬运时长 = 字节 /（带宽 / 开始时刻的在途 DDR 搬运数），问题 3 中命中 FIFO Cache（容量 `cache_capacity_bytes`）的搬入改用 `cache_bandwidth_bytes_per_cycle` 且不占 DDR 在途计数；核内按序发射（全局申请序，`last_start[k]` 单调不减）、各流水可乱序完成；返回 `max(全部完成时刻, DDR 总字节/带宽)`；不模拟 spill。
  - `validate_model.py` 的 `--proxy sim` 调用点已在 T04 预留提交，本任务不改该文件。
* 命令：`python solution/validate_model.py --all --proxy sim --jobs 16` → `results/model_validation_summary_sim.json`，`coverage=1.0`。
* 验收（写入 `results/simproxy_gate.json`）：
  ```
  P1: spearman_median=0.9429 (>=0.93 ✓，与旧代理 legacy 完全一致，因共用同一函数)
  P2: spearman_median=0.8000 (>=0.60 ✓)  recall3=0.8250 (>=60% ✓)
  P3: spearman_median=0.7970 (>=0.60 ✓)  recall3=0.8375 (>=60% ✓)
  pass_rank=true, pass_p1=true
  ```
  两条门槛均通过。下游规则：T13、T21 用 `simproxy` 排序；`TrafficState.cost` 保持不变；
  本任务未修改 `algorithms._local_search`。
* 回归：P2 58984、P1 116868、搬运量 90/90 一致。
* 改动文件：`solution/npu/simproxy.py`（新）、`results/model_validation_summary_sim.json`（新）、
  `results/model_validation_full_sim.csv`（新）、`results/simproxy_gate.json`（新）。

## T09-proxy 大图 P1 代理 top-1 兜底 — 完成（用户新增 Step 0，A 档执行计划）

* 背景：用户提供修订版执行计划（"只做 A 档"，约 6–10 h），本步骤为其"步骤 0"，
  在 T09（已完成、已验证有效的逐字节等价快速评估器）之上再加一层更激进的兜底：
  对 P1 端到端耗时中位数 > 600 s 的用例，官方候选评估完全跳过（不使用 fasteval，
  也不用 NPU_FASTEVAL），改用局部搜索内部已经计算的解析代价 `TrafficState.cost()`
  直接排序选 top-1，只对这一个候选调用一次官方评估器核实。
* `solution/npu/algorithms.py`：`cap_ls` 新增 `_return_cost=False` 参数，为 `True`
  时返回 `(plan, cost)` 而非仅 `plan`（`cost = state.cost(use_cache_aware)`，单核
  退化时为 0.0）；不改变默认行为（默认仍只返回 `plan`，兼容全部现有调用方）。
* `solution/npu/experiment.py`：
  - 新增 `_large_p1_cases()`：从 `results/main.csv` 问题 1 候选行按用例聚合
    `eval_s`，取中位数 > 600 的用例集合（进程内缓存一次）；
  - 新增 `_proxy_fallback_portfolio(...)`：对 `candidate_params(1, N, 'full')`
    的全部候选只做 `cap_ls(..., _return_cost=True)` 构造（不评估），取 cost 最小者，
    对它调用一次 `default_cache().evaluate`；记录的 `params` 字段加
    `"proxy_fallback": true`；
  - `run_portfolio` 开头新增判定：`problem == 1 and case in _large_p1_cases()`
    时优先于 `NPU_FASTEVAL` 与 T06 保留的候选裁剪，直接调用上述兜底并返回。
* 验证：`_large_p1_cases()` 命中 4 个用例（`case_014`、`case_072`、`case_076`、
  `case_091`；判定口径是"该用例全部候选 `eval_s` 的中位数"，比 T09 使用的
  "按 (用例,N) 求和 > 600s" 更严格，因此集合更小）。`case_014` N=5 在此路径下
  13.5 s 完成（此前同一 (用例,N) 官方逐候选评估需 5757–6329 s），选中 makespan
  3752694（与遍历全部候选官方评估选出的真实最优 3722693 相差 0.8%，属预期的
  代理近似损失）；非大图用例（`case_001` P1/P2）候选数与官方评估路径不受影响
  （仍为 12 个候选，逐一官方评估）。
* 回归：P2 58984、P1 116868、搬运量 90/90 一致。
* 改动文件：`solution/npu/algorithms.py`、`solution/npu/experiment.py`。

## T11 单算子子图 + 容量感知表调度 — 完成（用户 A 档执行计划步骤 2）

* `solution/npu/listsched.py`（已在前序会话写好，本次沿用）：`schedule(g, core_of_op,
  levels, problem, cfg, alpha, mu, nu, noise, seed, num_cores)`——HEFT 式上行秩
  + 片上驻留代价 `mu·Δlive/cap` + 流水互补奖励 `nu`，容量约束 `alpha×容量`，
  可行候选用 score 最大者、无可行候选退回 `Δlive` 最小者；核内按开始时刻最早提交
  （全局申请序）；最终按 `(levels[v], 追加位置)` 稳定重排。
* `solution/npu/algorithms.py`：
  - 新增 `_plan_op_mode(...)`：`core_of_op` 由块分配得到，层指派按 `level_mode`
    （复用 T12 的 `levels.assign_levels`）；调用 `listsched.schedule` 得到每核算子
    全序；子图 id 按 `(层次, 核编号, 核内位置)` 全局排序分配（保证每核 sid 升序
    即为调度序，满足 `stratify` 的性质 P1）；
  - `cap_ls` 新增 `subgraph_mode='op'` 分支及 `alpha=0.8, mu=0.0, nu=0.0, noise=0.0`
    四个参数；
  - `candidate_params` 新增 `n_ops=None` 参数与 `_op_max_n()`（读
    `results/pilot_op_gate.json` 的 `OP_MAX_N`，文件不存在时视为 `None`）；
    `problem in (2,3)` 且 `OP_MAX_N is None or n_ops is None or n_ops < OP_MAX_N`
    时追加 4 个固定顺序的 op 候选（`alpha=0.8,mu=1.0,nu=0.5`／`alpha=1.0,mu=1.0,nu=0.5`／
    `alpha=0.8,mu=0.0,nu=0.0`／`block_cap=0.15,alpha=0.8,mu=1.0,nu=0.5`）；P1 不追加。
  - `solution/npu/experiment.py`、`solution/solve.py` 的 `candidate_params(...)`
    调用处传入 `n_ops=g.n`。
* 试点：`run_experiments.py --stage main --problems 2 3 --cases <pilot20>` →
  `results/pilot_op.csv`（3040 行，299.5 s）。716 个 op 候选**全部可行**，
  `eval_s` 最大 28.46 s（远低于 120 s 阈值，pilot20 已含 3 个 P1 大图用例的
  P2/P3 op 候选）。判定：`OP_MAX_N = null`（不限制图规模），写入
  `results/pilot_op_gate.json`。
* 全量重跑（P2/P3）：`main`（15200 行，841 s）→ `merge_main`（P1 沿用 4464 行）→
  `p3`（8200 行，242.9 s）→ `build_pool.py --jobs 16`（1200 行，1149 s）。
* 验收（`solution/check_op_mode.py`，新建；输出 `results/op_mode_report.json`）：
  - `feasible = 3200/3200 = 100%`；
  - 各问题各 N 算术平均对比 T12：P1 不变（本步骤未重跑 P1）；
    P2 N=2..5：1.8882→2.0563、2.6746→2.8696、3.3899→3.6086、3.9965→4.2127；
    P3 N=2..5：1.8959→2.0581、2.6876→2.8768、3.4257→3.6523、4.0586→4.2785；
    全部提升 5%–9%，无一退步；
  - op 候选成为冠军的配置数：321 / 400（80.25%）；
  - 按 ρmax 分层的 P2 算术平均加速比：ρ<0.2 为 3.5528，0.2≤ρ<0.5 为 3.0437，
    ρ≥0.5 为 2.5014；
  - case_001–case_005 的 P2 N=4 算术平均：3.5064（外部参照，逐用例
    3.95/3.91/3.30/3.92/2.45）；
  - P2 N=4 冠军的 spill 字节总和：341,936,448；
  - `mu=1,nu=0.5` 对 `mu=0,nu=0` 的配对比较：n=800，胜 526／平 169／负 105，
    `rel=+3.21%`，`p≈6.0e-69`——`mu/nu` 惩罚项确有显著正贡献。
* 回归：P2 58984、P1 116868、搬运量 90/90 一致。
* 改动文件：`solution/npu/algorithms.py`、`solution/npu/experiment.py`、
  `solution/solve.py`、`solution/check_op_mode.py`（新）、`results/pilot_op.csv`（新）、
  `results/pilot_op_gate.json`（新）、`results/op_mode_report.json`（新）、
  `results/main.csv`、`results/main_p23.csv`、`results/p3_compare.csv`、
  `results/final.csv`、`results/pool.csv`、`results/plans_final/`、`results/final_plans/`、
  `results/summary.json`、`paper/tables/*`、`figures/*`、
  `results/baseline_snapshot/main_before_T11.csv`（新）。

## 补提交说明（T11/T12 漏提交的模块与计划文件）

* 发现：T12、T11 提交时漏加了新建模块 `solution/npu/levels.py`、`solution/npu/listsched.py`
  与验收脚本 `solution/check_levels.py`（`algorithms.py`、`stratify.py` 已在提交中引用它们），
  导致这两个提交在干净检出下无法导入。经对全部已跟踪 `solution/*.py` 的相对导入做一次
  "导入目标是否已跟踪"的扫描确认，缺口只有这三个文件（其余命中项是 `# noqa: E402` 注释、
  `levels_mod` 别名，以及 T14 进行中的 `p1_anneal`/`proxy_a`）。本次以独立补提交补入。
* 同源问题：T11/T12 的 `run_experiments.py --stage main/p3` 重跑会覆盖
  `results/plans/*_capls_best.json`（`save_plan=True`），两次提交都没有暂存这些文件（与 T06
  当时的遗漏相同）。已把 427 个 P2/P3 计划文件并入 T11 提交（`git commit --amend`，T11 哈希由
  `bc35d24` 变为 `ec5d069`）；它们对应 T11 重跑后的最终状态（T12 的同名文件已被 T11 覆盖）。
* 教训：此后每次提交前都用 `git status --short` 核对"本任务实际写出的文件"，而不是只按
  预想的清单 `git add`。

## T23-core 论文文本：八处不一致 + BSP 定位 — 完成（用户 A 档步骤 4，含超出规格的必要修正）

* 数据来源说明：规格引用的《实验综合改进清单_前沿增强版.md》不在仓库里（仓库根目录只有基底版
  `实验综合改进清单.md`，其 §2.8/A2 与本任务的"八处不一致"一致，已据此改写）。因此 T23.3 里
  "照录增强版 §3.2 表"的两段、"§5.1′ 问题分类与复杂度"、以及 B7 的 T23.4 相关工作与 T23.5 参考文献
  **没有可用的来源，本次没有做，也不会凭记忆编造文献条目**。BSP 定位段与推论 3 是按代码与已证事实
  自行写成的，没有引用文献编号。
* T23.1 八处（另加规格点名的两处弱化）：
  1. 统计口径改为算术平均（§10.1），全文"几何平均"只剩三处且都带"补充指标/比值型指标"标注；
  2. §7.2 P2-C 改为"`max_ops` 子图规模上限 + 单算子子图候选"，并注明代码里没有峰值驻留估计；
  3. §8.2 删去"θ 可以取得更小"（θ 候选序列与问题无关；没做 P3 的 θ 扫描，T17.4 不在计划内）；
  4. §8.3 的 `cachemodel.py` 改为"仅用于分析、无预测-实测对照"（T17.4 不在计划内，没有图 27 可引）；
  5. §10.3 case_016 改为"单兜底候选保证不低于 1.00（最小加速比 @@MIN_SPEEDUP_ALL@@）"，并把
     case_016 当前 N=4 加速比改成占位符（T11 之后为 1.26，旧文字写的是 1.00）；
  6. §10.4 Pareto：**没有照规格写"与基线持平"**——T11 之后 N=4 问题 2 的额外搬运总量
     7.39×10⁸ 对 B3 的 1.42×10⁹，已明显更低，写"额外搬运量也更低（总量 X 对 Y）"；
  7. §10.2 改为"平均加速比单调上升，逐用例单调不降（保底池保证）"；
  8. §11.3：spill 那句改为"仍占额外搬运的 46.3%，核内全序调度使其相对此前降低 64%"，删去无实验
     支撑的 `no_level` 延迟敏感性对照句；另弱化 §10.7 "F 足以驱动局部搜索"与下界段的因果断言。
* T23.3：§5.5 标题改为"BSP 超步性质在本题约束下的推论"；引理前加"与 BSP 模型的关系"；引理后加
  推论 3（单调层指派，含逐点最小性证明，对应 `levels.py`）；§5.4 加场景 B 切分搬运量的
  (λ−1) 连通度写法，并新增 `solution/check_lambda_form.py` 在 4 个最终方案上与
  `graphlib.scene_b_copy_bytes − original_copy_bytes` 逐位核对（LAMBDA FORM OK）；§2.2 增补
  事实 4（Belady 换出）与事实 5（Cache 命中在发射时判定、写入在完成时发生）；摘要"提出"改
  "引入…（BSP 超步结构的对应物）"。事实 5 里如实写入了 T07 发现的"同一方案在问题 3 下可能略慢于
  问题 2"（占位符 COND4_COUNT / COND4_MAXREL，来自 `pool_condition4_exceptions.json`）。
* 超出规格、但为避免正文出现已知错误数字而做的改动（这些数字在 T11/T12 之后都变了）：
  额外搬运量段（原写"多 11.5%"，现为 −40%）、最难用例列表、超线性用例数（9→27、30→52）、
  §10.4 的基线数字与"24%–42%"、§10.5 的 L2 数字、§10.7(b) 整段改为**用例内**指标
  （T04/T10 的输出，`@@TABLE_PROXY@@`）、下界表与结论、§11.1 消融百分比、§11.2 粒度表与文字
  （算术平均下最优点仍全是 β=0.25、单峰，结论不变）、图特征相关系数、求解时间样本数。
  S4 段落（§7）补写了当前候选数（14/18）与**大图 P1 代理兜底的披露**：case_014/072/076/091
  的问题 1 成绩是"代理择优 + 一次官方核实"，不是"全部候选官方择优"。
* 代码：`fill_paper.py` 新增约 100 个占位符（`_extra_values`），并修正未替换检测的正则
  （原 `[A-Z0-9_]+` 检测不到含小写字母的键）；`make_report.summary` 新增 `spill_added_total`、
  `partition_added_total`、`baseline_added_total`、`l2_gain_gt1pct`、`l2_gain_maxcase`、
  `l2_hit_nonzero`、`l2_hit_max`；`check_op_mode.py` 新增 T11 前后 spill 对比（
  962,520,976 → 342,293,926，−64.4%）；`bounds.py --skip-empirical`（T19 第 1–3 项，
  第 4 项按计划跳过）产出 `bounds.json`、`bounds_cdf.csv`。
* 发现并修正的自身缺陷：T14 代码里退火行与代理兜底行的 `runtime_s` 误记成了官方评估耗时
  （该列口径是单候选构造时间）。已在 `experiment.py` 改正口径，并让 `make_report` 的运行时间统计
  排除这两类行（当时后台的 T14 仍在用旧代码，故双保险）。
* 验收：`fill_paper.py` 无 WARNING（150 个占位符全部替换）；`md2docx.py` 无 XML 错误；
  `grep 几何平均` 三处都带标注；回归 P2 58984 / P1 116868 / 搬运量 90/90。
* 仍然过时、留给 B7（T23.2/T23.6）的部分：附录/§2.3 的结构统计未重算（数据没变，不受影响）；
  T14 完成后 P1 相关数字会再变一次（占位符自动更新，但 §7 里需补一句退火的描述）。

## T14: P1 代理驱动模拟退火

- 新增 `npu/proxy_a.py`（`estimate_scene_a_from_plan` 自 validate_model 迁出）与 `npu/p1_anneal.py`（迭代数 3000→1500，seed=20260924）。
- `run_portfolio`：P1 网格冠军为起点退火，产出 `sa1..sa3`（方案落盘 `results/plans/*_p1_n*_sa*.json`，`variants.build` 从盘加载），参与冠军选择；`build_pool._label_of` 与 `variants.LABELS` 同步。
- 大图 P1（case_014/072/076/091）走代理兜底：代理 top-1 + 1 次官方验证，不评估全网格。
- 修正 `runtime_s` 语义：兜底/退火行记录构造耗时，`make_report` 的运行时统计排除这些行。
- 结果（final.csv，P1 各 N 算术平均）：T14 前 1.7808/2.4957/3.1558/3.7144 → 后 1.8106/2.5423/3.1808/3.7349，无回退。
- `p1_anneal_report.json` 的 `no_regression=false`：主阶段冠军口径 N=3 由 2.4610 降至 2.4499。已核实变差配置全部落在四个大图上（N=2/3/4 各 4 个，N=5 共 2 个），其余 96 个用例无一变差，属代理兜底相对完整网格的基准偏移；pool 层面已由其他候选补回。
- 退火耗时未达标：中位数 4.92 s，最大 2015.12 s，42 个配置 >60 s（最慢 case_014/076/091 的 N=2、3）。规格只允许把迭代数降到 1500 重跑一次，已是 1500，故不再调参，如实记录。
- 0.3 回归：P2 58984、P1 116868、搬运量模型 90/90；`check_pool` POOL OK。

## T13: 优先级采样组合

- `experiment.run_portfolio`（P2/P3）：取最优 op 候选的参数为基础，`noise=0.05`、`seed=1..K` 采样。`simproxy_gate.json` 的 `pass_rank=true`，故 K=16，用 `simproxy.estimate` 排序后取 top-3 官方评估（`pass_rank=false` 时 K=4 全评估）。`s*` 变体参与冠军选择，冠军来自采样时 `_best` 记录写入基础参数 + noise。
- 采样方案不落盘（约 2400 个大文件），由 `variants.build` 用 `results/plans/<case>_p<P>_n<N>_s_base.json`（基础参数 + 被官方评估的标签）确定性重建；`LABELS` 增加 `s1..s16`，`build_pool` 对未评估的样本静默跳过。
- 重跑 P2/P3 主阶段（800 任务）、p3 阶段、`merge_main`、`build_pool`（mismatches=0）；`check_pool` POOL OK，条件 4 例外 7→2 个（最大相对差 0.0067%）。
- 结果（final.csv 算术平均）：P2 2.0563/2.8696/3.6086/4.2127 → 2.0608/2.8809/3.6309/4.2405；P3 2.0581/2.8768/3.6523/4.2785 → 2.0626/2.8897/3.6741/4.3122。
- `sampling_report.json`：新增官方评估 2400 次；165/800 个配置冠军来自 `s*`；主阶段口径 P2 N=4 均值 K=0/1/4/16 = 3.5359/3.5400/3.5558/3.5766。
- 0.3 回归：P2 58984、P1 116868、搬运量模型 90/90。

## T17: L2 分层样本 + 命中来源拆分

- T17.1：`sample_cases.py` 新增 `l2_gain_n4` / `l2_strata`，用 `p3_compare.csv` 的 N=4 `_best` 方案在 P2/P3 评估下的 makespan 之比作 L2 收益。分层大小：>1.05 共 16 个（全取），1.01–1.05 共 16 个（`Random(20260926)` 抽 10），≤1.01 共 68 个（`Random(20260927)` 抽 10），`l2_strata` 共 36 个；`pilot20`/`study30` 不变，连续运行 md5 一致。
- T17.2：`l2_sources.py --jobs 16`，对 400 个 P3 冠军用 `evaluate_plan(3, ..., full=True)` 重跑事件流（0.1 第 4 条第二个例外）；命中拆为 input_reuse / spill_reload / cross_core_mid，未命中拆为 first_miss / oversize / concurrent_first_read / fifo_evicted。输出 `l2_sources.csv`、`l2_sources.json`。
- 验收：400 配置无错误，各 N 的命中字节之和与未命中字节之和均等于官方 `cache_hit_bytes` / `cache_miss_bytes`。
- 0.3 回归：P2 58984、P1 116868、搬运量模型 90/90。
- 未做：T17.3（l2study 扫描）、T17.4，按 B 档计划跳过。

## T16: 消融体系重建 + 组合分析

- `run_experiments.py` 新增 `ablation2` 阶段（13 个变体，基准 = c2 参数 `dict(block_cap=0.35, init='rr')`；op_* 仅 P2/P3），变体定义在 `variants.ABLATION2`。
- 运行：P2/P3 全 100 case（10400 行，1004 s）；P1 排除 case_014/072/076/091（单次官方评估 >10 min），96 case（3456 行，1120 s）；合并为 `results/ablation2.csv`（13856 行）。论文须注明 P1 消融样本为 96 case。
- `portfolio_analysis.py`（只读 pool.csv）：贪心前向选择曲线、留一消融、择优层（simproxy，`pass_rank=true`，N=4）。N=4 算术平均：代理择优 P1/P2/P3 = 3.066/3.343/3.422，官方在主候选内择优 3.141/3.577/3.654，池冠军 3.181/3.631/3.674；P2 N=4 代理损失 0.2332，已存入 `portfolio_analysis.json`。
- `make_report.summary` 新增 `ablation2`（describe + 相对 full_c2 的 paired，Holm 校正）、并带出 `portfolio_analysis` 与 `cv_select`；`fill_paper` 新增 `TABLE_ABLATION2`、`TABLE_GREEDY`、`PROXY_ONLY_P2_N4`（及 `PROXY_LOSS_*`、`OFFICIAL_MAIN_P2_N4`、`CV_LOSS` 的读取钩子，后者随 T20 生效）。
- 主要结论（相对 full_c2 的均值变化，P1/P2/P3）：去分层 −19.8%/−8.3%/−9.2%；去通信感知 −6.1%/−6.6%/−6.7%；去分层且去通信 −58.0%/−39.7%/−39.9%；去同步深度代价、去局部搜索不显著；lvl_alap 与 lvl_compress 结果一致（+0.6%/+2.5%/+2.4%）。
- 0.3 回归：P2 58984、P1 116868、搬运量模型 90/90。
