# Task Spec：实验综合改进清单落地执行规格

> 版本 2026-09-24。依据：《实验综合改进清单.md》（基底）与《实验综合改进清单_前沿增强版.md》（增强版）。
> 对象：在仓库 `JL-ui/20260923math` 中执行的 Claude Code。本文件只给执行规格，不含实现代码。
> 行号全部对应提交 `9eb5ec4`。如果行号已偏移，按每处给出的**锚点文本**定位，锚点文本优先于行号。

---

## 0. 全局规则（每个任务都适用，冲突时以本节为准）

### 0.1 绝对禁止
1. 不得修改 `code/`、`data/`、`docs/`、`README.md`、`通用神经网络处理器下的多核调度问题.docx` 中的任何文件（包括 `data/config.txt`）。
2. 不得修改 `/mnt/project-files/论文终稿/` 下的任何文件（另一个讨论串在用）。
3. 不得手工填写论文里的实验数字；正文数字一律通过 `@@KEY@@` 占位符由 `solution/fill_paper.py` 注入。
4. 不得在任何批量实验里直接调用 `evaluate.evaluate_plan(...)`；一律走 `evaluate.default_cache().evaluate(...)`。唯一例外见 T09（快速评估器差分测试）。
5. 不得删除 `results/cache/`。
6. 不得跳过、放宽任何验收条件；验收失败时只能执行该任务写明的"失败处理"，没有写明的就**停止并报告**，不得自行变通。

### 0.2 通用约定
- 分支：从 `main` 新建 `improve/checklist-v3`，每个任务一个提交，提交信息格式 `T<编号>: <任务名>`。
- 运行 Python 一律加 `PYTHONIOENCODING=utf-8` 前缀（Windows 终端中文输出）。下文命令省略该前缀，执行时必须加上。
- 并行度变量：`JOBS=16`（与 `run_all.sh` 默认一致）。
- 所有新模块放在 `solution/npu/`，所有新脚本放在 `solution/`，所有新结果放在 `results/`。
- 新增的随机性一律用 `random.Random(seed)`，默认种子 `20260924`，写死在代码常量里。
- 加速比口径：**算术平均**为主口径；几何平均、中位数只作为补充字段。
- 张量大小、周期数一律用整数；比值保留 4 位小数写入 JSON/CSV。
- 每个任务完成后运行 0.3 的回归检查。

### 0.3 回归检查（每个任务提交前必跑，全部通过才能提交）
```bash
python solution/solve.py data/case_001.json --problem 2 --cores 4 -o /tmp/r_p2.json
python code/multicore_cut_evaluate_problem_2.py data/case_001.json /tmp/r_p2.json --config data/config.txt -o /tmp/r_p2_res.json
python solution/solve.py data/case_001.json --problem 1 --cores 2 --fast -o /tmp/r_p1.json
python code/multicore_cut_evaluate_problem_1.py data/case_001.json /tmp/r_p1.json --config data/config.txt -o /tmp/r_p1_res.json
python solution/check_traffic_model.py
```
通过标准：四条命令退出码为 0；两个 `*_res.json` 中 `makespan` 为正整数；`check_traffic_model.py` 输出中不一致数为 0。
Windows 下把 `/tmp/` 换成 `%TEMP%\`。

### 0.4 任务总览与依赖

| 编号 | 任务 | 对应清单项 | 依赖 | 需新评估 |
|---|---|---|---|---|
| T00 | 环境与基线快照 | D7.3 | — | 否 |
| T01 | 统计模块 | D3 | T00 | 否 |
| T02 | 口径改算术平均 | A1、A4 | T01 | 否 |
| T03 | 分层抽样规则 | D4 | T00 | 否 |
| T04 | 代理检验改用用例内指标 | A3、D4.1 | T01、T03 | 否（命中缓存） |
| T05 | 变体方案生成器统一化 | B1 前置 | T00 | 否 |
| T06 | P2/P3 取消大图候选裁剪并重跑 | B5 | T05 | 是，P2/P3 约 5 CPU·h |
| T07 | 保底池 | B1–B4 | T05、T06 | 少量 |
| T08 | 最终方案官方 CLI 复核脚本 | D7.4 | T07 | 是（CLI 复核） |
| T09 | 逐字节等价快速评估器 | C3 | T00 | 差分测试 |
| T10 | 算子级事件模拟代理 | C2 | T04 | 否（离线） |
| T11 | 单算子子图 + 容量感知表调度 | C1 | T10 | 是 |
| T12 | 单调层指派（ALAP 填充、层压缩） | C8 | T05 | 是 |
| T13 | 优先级采样组合 | C9 | T11 | 是 |
| T14 | P1 代理驱动模拟退火 | C5（替换版） | T07 | 是，每配置 ≤3 次 |
| T15 | 外部基线与预算对等基线 | D1 | T11 | 是 |
| T16 | 消融体系重建 | D2 | T11–T13 | 是 |
| T17 | P3 的 L2 专项与命中来源拆分 | D8、C10 前置 | T03、T07 | 是 |
| T18 | 领读—跟读排序 | C10 | T11、T17 | 是 |
| T19 | 界与参照 | D6 | T07 | 部分 |
| T20 | 超参数过拟合检验 | D5 | T07 | 否 |
| T21 | 冠军邻域精修 | C4 | T10、T12 | 是 |
| T22 | 图表增补与 trace 剖析 | E1、E4 | T07–T19 | 少量 |
| T23 | 论文文本修改 | A2、A5、A6、相关工作 | T02–T22 | 否 |
| T24 | 收尾：全量重建与复核 | — | 全部 | 是 |

**时间只有 2–3 天时**，只做：T00 → T01 → T02 → T03 → T04 → T05 → T06 → T07 → T08 → T11（只 P2/P3）→ T23 中的 A2/A5/A6/相关工作 → T24。

---

## T00　环境与基线快照

**目的**：固定依赖、保存改动前的结果，后面所有"不退步"的验收都和这份快照比。

**新建文件**
1. `requirements.txt`（仓库根目录）。内容为以下包及当前环境里的精确版本，版本用 `python -m pip show <pkg>` 读取后写 `==`：`numpy`、`scipy`、`matplotlib`、`python-docx`。如果 `scipy` 未安装，先 `python -m pip install scipy`。
2. `results/baseline_snapshot/`：复制以下文件进去（只复制，不改名）：`results/summary.json`、`results/main.csv`、`results/p3_compare.csv`、`results/final_plans/manifest.csv`。

**命令**
```bash
python -m pip install -r requirements.txt
python -c "import numpy, scipy, matplotlib, docx; print('ok')"
```

**验收**：输出 `ok`；`results/baseline_snapshot/` 下 4 个文件存在，且与原文件逐字节相同（`python -c "import filecmp,sys; ..."` 或 `fc /b`）。

---

## T01　统计模块（D3）

**新建** `solution/npu/stats.py`，只包含以下函数（签名固定）：

| 函数 | 行为 |
|---|---|
| `amean(xs) -> float` | 算术平均，忽略 `None` 与非正数 |
| `gmean(xs) -> float` | 几何平均，规则同上（行为与 `plots.geomean` 一致） |
| `bootstrap_ci(xs, stat='amean', n_boot=10000, alpha=0.05, seed=20260924) -> (lo, hi)` | 对"用例"做有放回重采样，统计量取 `amean` 或 `gmean`，返回百分位区间 |
| `paired(a: dict, b: dict, tie=0.001) -> dict` | `a`、`b` 都是 `{(case, n): speedup}`；只用两者共有的键；返回 `{'n', 'win', 'tie', 'loss', 'mean_a', 'mean_b', 'rel', 'p'}`。胜负按 `a/b - 1` 与 `±tie` 比较；`p` 用 `scipy.stats.wilcoxon(log(a) - log(b), zero_method='wilcox')`，所有差值为 0 时 `p = 1.0` |
| `holm(pvals: dict) -> dict` | Holm–Bonferroni 校正，输入输出都是 `{name: p}` |
| `strata(case) -> str` | 读 `results/features.json` 的 `largest_component_frac`，返回 `'rho<0.2'`、`'0.2<=rho<0.5'`、`'rho>=0.5'` 三者之一（阈值与论文表 10-2 一致） |
| `describe(xs) -> dict` | 返回 `{'amean', 'gmean', 'median', 'min', 'max', 'p90', 'n', 'ci_lo', 'ci_hi'}`，CI 为算术平均的 bootstrap 区间 |

**验收**
```bash
python -c "from solution.npu import stats; print(stats.describe([1,2,3,4]))"
```
如果包导入路径不通，改用 `cd solution && python -c "from npu import stats; ..."`。通过标准：`amean=2.5`、`median=2.5`、`min=1`、`max=4`、`n=4`，且 `ci_lo ≤ 2.5 ≤ ci_hi`。
再运行 `python -c "from npu import stats; print(stats.paired({('a',2):2.0,('b',2):1.0},{('a',2):1.0,('b',2):1.0}))"`（在 `solution/` 下），通过标准：`win=1, tie=1, loss=0`。

---

## T02　口径改为算术平均（A1、A4）

### T02.1 `solution/npu/plots.py`
在 `def geomean(values):`（第 93 行）之后新增 `def amean(values):`，规则与 `geomean` 相同：过滤 `None` 与非正数，空列表返回 `nan`。

按下表逐处替换（只改列出的位置，其余 `geomean` 保持不变）：

| 行 | 锚点文本 | 改为 |
|---|---|---|
| 338 | `ys = [geomean(table[problem][n]) for n in xs]` | `amean` |
| 351 | `'平均加速比（{} 个用例的几何平均）'` | `'平均加速比（{} 个用例的算术平均）'` |
| 421 | `ax.scatter([i + 1], [geomean(v)], ...` | `amean` |
| 424 | `（◆ 为几何平均）` | `（◆ 为算术平均）` |
| 511、514、515 | `geomean(byn2[x])`（三处） | `amean` |
| 561 | `ys = [geomean(byn[p][x]) for x in xs]` | `amean` |
| 570 | `[geomean(e2e[x]) for x in xs3]` | `amean` |
| 573 | `'平均加速比（相对官方单核基准，几何平均）'` | `'平均加速比（相对官方单核基准，算术平均）'` |
| 607 | `vals = [geomean(data[p][v]) for v in names]` | `amean` |
| 687、688 | `gx = geomean(...)`、`gy = geomean(...)` | `amean` |
| 696 | `'（★ 为几何平均）'` | `'（★ 为算术平均）'` |
| 711 | `ys = [geomean(data[p][v]) for v in variants]` | `amean` |

**不改**：第 764 行（敏感性"相对默认配置的倍数"）和第 834/838 行（Makespan/下界比值）保持几何平均，这两处是比值型指标、不是赛题定义的加速比；但把第 838 行 y 轴文字改为 `'Makespan / 理论下界（几何平均，比值型指标）'`。

### T02.2 `solution/make_report.py`（`summary` 函数）
1. 第 198 行 `{a: round(plots.geomean(v), 4) ...}`：改为输出两个键。把 `out['baseline_speedup']` 的值改成算术平均，另增 `out['baseline_speedup_geomean']` 保存原几何平均。
2. 第 211 行 `'capls'] = round(plots.geomean(v), 4)`：同步改为算术平均，并在 `baseline_speedup_geomean` 中写几何平均。
3. 第 217–219 行 `out['ablation']`：改为算术平均；另增 `out['ablation_geomean']`。
4. 第 241 行 `out['l2_gain']`：改为算术平均；另增 `out['l2_gain_geomean']`。
5. 第 170–184 行 `out[f'problem{problem}']`：在字典中增加 `'speedup_ci'`：`{n: [ci_lo, ci_hi]}`，用 `stats.bootstrap_ci(v, 'amean')`；再增加 `'speedup_by_strata'`：`{n: {stratum: stats.describe(...)}}`。
6. 在 `summary` 末尾增加 `out['paired']`：对每个问题、`N=4`，用 `stats.paired` 比较 CAP-LS 冠军与 `baseline.csv` 中的每个算法（`random`、`topo`、`balance`、`comm`），以及 `ablation.csv` 中每个变体与 `full`；p 值经 `stats.holm` 校正后一并写入。

### T02.3 `solution/fill_paper.py`
1. 第 40 行 `g = s.get(key, {}).get('speedup_geomean', {})` → 改读 `'speedup_mean'`。
2. 在 `build_values` 中新增占位符（值来自 `summary.json`，格式与相邻占位符一致）：
   - `P{p}_GEO_N{n}`：几何平均（p=1..3，n=2..5），供正文"补充指标"引用；
   - `P{p}_CI_N4`：格式 `[lo, hi]`，两位小数；
   - `P{p}_SU_N4_STRATA`：三层各自的算术平均，格式 `3.68 / 3.04 / 2.27`；
   - `TABLE_PAIRED`：Markdown 表，列为"比较对象 | 问题 1 | 问题 2 | 问题 3"，单元格格式 `+7.6%（p=0.001，胜/平/负 60/10/30）`。
3. `TABLE_BASELINE`、`TABLE_ABLATION` 的数据源因 T02.2 自动变成算术平均，不需要另改。

### T02.4 `solution/digest.py`
第 32 行标题中"几何平均"改为"算术平均"；第 55–57 行打印 `geo=` 改为先打印 `mean=`（算术平均），再打印 `geo=`。

### T02.5 `SOLUTION.md`
第 27 行及同表其他行：把表头"平均加速比（几何平均）"改为"平均加速比（算术平均）"，数值改为 `results/summary.json` 中 `speedup_mean` 的值（这是 SOLUTION.md，不在论文占位符体系内，允许写数字，但必须从 `summary.json` 逐字复制）。

**验收**
```bash
python solution/make_report.py --summary
python -c "import json;s=json.load(open('results/summary.json',encoding='utf-8'));print(s['problem2']['speedup_mean'], s['problem2']['speedup_ci'], s['l2_gain'], 'paired' in s)"
python solution/make_report.py --figures
python solution/assemble_paper.py && python solution/fill_paper.py paper/论文_完整.md
```
通过标准：
- `problem2.speedup_mean` 等于快照 `results/baseline_snapshot/summary.json` 中的同名字段（本任务只改口径不改方案，数字不能变）；
- `speedup_ci` 四个 N 都有，且每个区间包含对应的 `speedup_mean`；
- `fill_paper.py` 输出中除 T23 才会引入的占位符外，没有 `WARNING unresolved placeholders`；
- `grep -n "geomean(" solution/npu/plots.py` 只剩第 764、834 行附近两处与 `def geomean` 本身。

---

## T03　分层抽样规则（D4）

**新建** `solution/sample_cases.py`。行为：
1. 读 `results/features.json`，按 `stats.strata(case)` 分三层；每层内按 `n_ops` 升序排序后等分为三档（档大小不整除时，余数分给最大档）。
2. 生成三个样本，写入 `results/samples.json`，键与规则如下（种子统一 `20260924`，每个样本用独立的 `random.Random(20260924 + i)`，i 为下表序号）：

| i | 键 | 大小 | 规则 |
|---|---|---|---|
| 0 | `pilot20` | 20 | 三层按 12/2/6 分配；层内在三档间轮流抽取；最后强制包含 `n_ops` 最大的 3 个用例（若不在样本内，替换同层中 `n_ops` 最小的已抽用例） |
| 1 | `study30` | 30 | 三层按 18/4/8 分配，规则同上，不强制大图 |
| 2 | `l2_strata` | 28 | 按 T17 的定义分层，见 T17.1；本任务只写占位空列表 `[]`，T17 负责填充 |

3. `samples.json` 同时写入 `'rule'` 字段，原样记录上表规则文字与种子，论文附录引用它。

**修改** `solution/run_all.sh`：第 31–35 行（粒度实验的 `--cases` 列表）与第 40–44 行（敏感性实验的 `--cases` 列表）改为从 `results/samples.json` 读取 `study30`：在脚本中用一行 `python -c` 读出空格分隔的用例名，赋给变量 `STUDY30`，两处都改为 `--cases $STUDY30`。

**验收**
```bash
python solution/sample_cases.py
python -c "import json;s=json.load(open('results/samples.json'));print(len(s['pilot20']),len(s['study30']),s['rule'][:40])"
python solution/sample_cases.py && python -c "import json,hashlib;print(hashlib.md5(open('results/samples.json','rb').read()).hexdigest())"
```
通过标准：输出 `20 30`；连续运行两次 md5 相同（确定性）。

---

## T04　代理检验改用用例内指标（A3、D4.1）

**修改** `solution/validate_model.py`
1. 第 186–189 行参数：新增 `--all`（布尔）、`--proxy`（取值 `legacy`、`sim`，默认 `legacy`）。
2. 第 190 行 `cases = args.cases or paths.all_cases()[:40]`：`--all` 时改为全部 100 个用例；并把 `tasks` 的核数从单一 `args.cores` 改为 `--all` 时遍历 `(2, 3, 4, 5)`。
3. 第 99–106 行 `_estimate`：`--proxy sim` 时，三个问题都调用 T10 的 `simproxy.estimate(g, plan, problem, cfg)`；`legacy` 保持原逻辑。给 `task()` 增加 `proxy` 参数传入。
4. 第 200–224 行（`main` 的统计打印）整段替换为调用新函数 `within_case_report(rows) -> dict`，它对每个 `(case, num_cores)` 组内（组内候选按 `makespan` 去重，重复值保留一个）计算：
   - 用例内 Spearman 与 Kendall τ（`scipy.stats.spearmanr`、`kendalltau`；组内候选少于 3 个时跳过该组）；
   - Top-K 减速比（K=1,3,5）：`min(按代理排序前 K 个的真实 makespan) / 组内真实最小 − 1`；
   - Recall@K：真实最优是否落在代理前 K 个中；
   然后按问题汇总：Spearman/Kendall 的中位数和均值，Top-K 减速比的中位数、90 分位、最大值，Recall@1/3/5。混合秩相关只作为 `'pooled_spearman'` 附带输出。
5. 结果写 `results/model_validation_summary_<proxy>.json`；CSV 输出路径 `--all` 时默认改为 `results/model_validation_full_<proxy>.csv`。

**命令**
```bash
python solution/validate_model.py --all --proxy legacy --jobs 16
```
（候选方案是确定性重建，绝大多数命中 `results/cache`；未命中的会触发官方评估，属于正常情况。）

**验收**：`results/model_validation_summary_legacy.json` 存在；`--all` 覆盖 `100 × 4 × 3` 组中至少 95% 的组；对 N=4、前 40 个用例的子集再算一次，P2 用例内 Spearman 中位数应在 0.43–0.53 之间（基底清单核实值 0.48）。不在区间内时停止并报告，不要继续 T10。

---

## T05　变体方案生成器统一化（B1 前置）

**目的**：让主候选、基线、消融、粒度扫描的方案都能用同一个函数按"标签"确定性重建，供 T07 保底池和后续所有任务使用。

**新建** `solution/npu/variants.py`，提供：
- `LABELS(problem, num_cores) -> list[str]`：返回下列全部标签（顺序固定）：
  - 主候选：`c0` … `c{k-1}`，k 为 `algorithms.candidate_params(problem, num_cores, 'full')` 的长度，参数按下标对应；
  - 基线：`b_random`、`b_topo`、`b_balance`、`b_comm`；
  - 消融：`a_full`、`a_no_comm`、`a_no_balance`、`a_no_sync`、`a_no_localsearch`、`a_no_cache_aware`、`a_no_level`；
  - 粒度：`g_0.03`、`g_0.06`、`g_0.12`、`g_0.25`、`g_0.5`、`g_1.0`、`g_2.0`；
  - 单核：`single`。
- `build(g, label, problem, num_cores, seed=0) -> plan`：
  - `c*` 调用 `algorithms.cap_ls(g, num_cores, problem, seed=seed, **params)`；
  - `b_*` 调用 `algorithms.ALGORITHMS[name](g, num_cores, problem, seed=seed)`；
  - `a_*`：把 `solution/run_experiments.py` 第 147–180 行（`task_ablation` 中从 `if rr or no_level:` 到 `plan = algorithms.cap_ls(g, ncores, problem, **params)`）的方案构造逻辑**原样搬到** `variants.ablation_plan(g, name, problem, num_cores)`，`build` 调用它；
  - `g_*` 调用 `cap_ls(g, num_cores, problem, block_cap=beta)`；
  - `single` 返回整图一个子图、放在 0 号核、其余 `num_cores-1` 个核为空列表的方案。
  - 返回值一律经过 `evaluate.canonical_plan`。

**修改** `solution/run_experiments.py`
1. 第 146–203 行 `task_ablation`：方案构造改为调用 `variants.ablation_plan`；第 182 行 `res = evaluate.evaluate_plan(problem, case, evaluate.canonical_plan(plan))` 改为 `res = evaluate.default_cache().evaluate(problem, case, plan)`（这是 0.1 第 4 条要求，原代码漏了缓存）。其余记录字段不变。

**验收**：写并运行一次性检查脚本 `solution/check_variants.py`（保留在仓库）：对 `case_001`、`case_016`、`case_044` × P2 × N=4，逐个标签 `build` 两次，断言两次 `plan_hash` 相同；对 `c*` 标签，断言 `plan_hash` 与 `run_portfolio` 生成的同名候选相同；对 `a_*` 标签，断言 `default_cache().evaluate` 的 makespan 与 `results/ablation.csv` 中同 `(case, problem, num_cores, variant)` 的 makespan 完全相等。
```bash
python solution/check_variants.py
```
通过标准：打印 `ALL OK`，退出码 0。任一不等时停止并报告不等的标签，不要继续 T07。

---

## T06　P2/P3 取消大图候选裁剪并重跑（B5）

**修改**
1. `solution/npu/experiment.py` 第 102–106 行：
   - `if level == 'auto':` 分支的条件改为 `if level == 'auto' and problem == 1:`，否则 `level = 'full'`；
   - `if level == 'full' and n > 6000:` 改为 `if level == 'full' and n > 6000 and problem == 1:`。
2. `solution/solve.py` 第 35–38 行：同样只对 `problem == 1` 使用 `fast` 与 `grid[:8]`。

**命令**（只重跑 P2、P3 的主阶段与 P3 对照阶段，覆盖原 CSV 之前先备份）
```bash
copy results\main.csv results\baseline_snapshot\main_before_T06.csv     # Linux 用 cp
python solution/run_experiments.py --stage main --jobs 16 --problems 2 3 --out results/main_p23.csv
python solution/run_experiments.py --stage p3 --jobs 16 --out results/p3_compare.csv
```
然后写一次性合并脚本 `solution/merge_main.py`：取 `main_before_T06.csv` 中 `problem == 1` 的行，加上 `main_p23.csv` 的全部行，写回 `results/main.csv`。

**验收**
```bash
python solution/merge_main.py
python -c "import csv;r=list(csv.DictReader(open('results/main.csv',encoding='utf-8')));import collections;c=collections.Counter((x['case'],x['problem'],x['num_cores']) for x in r if x['variant'].startswith('c'));print(min(v for k,v in c.items() if k[1]!='1'))"
```
通过标准：P2/P3 每个配置的候选数最小值等于完整候选集长度（P2/P3 为 12）；P2/P3 端到端最长时间（`runtime_s + eval_s` 按配置求和）≤ 600 s；每个配置的 P2/P3 冠军 makespan ≤ 快照中的冠军（新增候选只会让结果不变或更好，出现变差说明合并错误，停止并报告）。

---

## T07　保底池（B1–B4）

**新建** `solution/build_pool.py`（阶段脚本）与 `results/final.csv`（输出）。

**算法（按此顺序，对每个用例串行执行，用例之间 `ProcessPoolExecutor` 并行）**
1. 对 `N = 2, 3, 4, 5` 递增、对 `problem = 1, 2, 3`：
   1. 候选集合 = `variants.LABELS(problem, N)` 的全部标签。`problem == 2` 时，另加 `x3_c0 … x3_c{k-1}`：用 `problem=3` 的候选参数构造（`cap_ls(g, N, 3, **params)`），但用 `problem=2` 评估（这些方案已在 `p3_compare` 阶段以 P2 评估过，命中缓存）。
   2. 对每个标签，`build` 出方案，然后决定是否评估：
      - `problem ∈ {2, 3}`：一律 `default_cache().evaluate(problem, case, plan)`；
      - `problem == 1`：若缓存命中则直接用；若未命中，只有当该标签在 `results/{main,baseline,ablation,granularity}.csv` 中有同配置记录、且记录的 makespan 小于当前 `main.csv` 冠军时才评估；否则跳过该标签（它不可能成为冠军，跳过不改变最终结果）。在 `final.csv` 的 `params` 列记录 `p1_pruned_labels` 数量。
      - 对所有被评估且在 CSV 中有记录的标签，断言评估值与记录值完全相等；不等时把该标签写进 `results/pool_mismatch.csv` 并**不**纳入池（不要停止）。
   3. **N−1 嵌入**（N ≥ 3）：取本用例同问题 N−1 的冠军方案，在 `core_schedules` 末尾追加一个空列表 `[]`，经 `canonical_plan` 后评估，标签 `embed_n{N-1}`。N=2 时嵌入 `single`（已在候选中）。
   4. **单核兜底**：`single` 标签只在"当前最优 speedup < 1.0"时才评估（P1 整图评估很贵）；否则跳过。
   5. 冠军 = 按 `(makespan, added_copy_bytes, 标签字典序)` 取最小。
2. **跨问题互投**（在某个 N 的 P2、P3 都算完后）：P2 冠军用 `problem=3` 评估，标签 `cross_from_p2`，并入 P3 池；P3 冠军用 `problem=2` 评估，标签 `cross_from_p3`，并入 P2 池；重新取冠军。
3. 冠军方案写入 `results/plans_final/<case>_p<problem>_n<N>.json`。
4. 每个冠军写一行到 `results/final.csv`，字段与 `main.csv` 相同，另外：`algorithm='capls'`、`variant='pool:<标签>'`、`is_best=True`、`eval_problem=problem`、`plan_path` 指向第 3 步文件、`params` 为该标签的参数 JSON（`single`、`embed_*`、`cross_*` 写标签名）。
5. 另写 `results/pool.csv`：所有被评估的候选一行，含标签、makespan、added_copy_bytes、是否冠军，供 T20、T22 使用。

**修改下游读取**
1. `solution/make_report.py` `main()` 第 275 行：新增 `final_rows = plots.read_csv('final.csv') or main_rows`；`appendix_tables`（第 282 行）与 `summary`（第 285 行）的 `main_rows` 实参改为 `final_rows`；`summary` 内第 157、204 行 `rows = p3_rows if (problem == 3 and p3_rows) else main_rows` 改为 `rows = main_rows`（此时 `main_rows` 已是 `final_rows`，P3 冠军在其中）；第 252–262 行运行时间统计必须仍用原始 `main.csv`，给 `summary` 增加参数 `run_rows` 专门传原始 `main.csv`。
2. `make_report.py` 第 297–314 行调用的图函数：`fig_speedup`、`fig_speedup_box`、`fig_makespan_compare`、`fig_addedcopy_compare`、`fig_pareto`、`fig_feature_effect`、`fig_subgraph_count`、`fig_lower_bound` 传入 `main_csv='final.csv'`（文件存在时）；`fig_runtime` 仍用 `main.csv`。第 248 行 `plots.bound_gap('main.csv', problem)` 同样改为 `final.csv`。
3. `solution/export_plans.py` 第 26 行：若 `results/final.csv` 存在，改为只读 `final.csv`，第 31–33 行的 `ep != problem` 过滤保持。
4. `solution/digest.py` 第 27–28 行：`main_rows` 优先读 `final.csv`。

**命令**
```bash
python solution/build_pool.py --jobs 16
python solution/make_report.py --summary --tables
python solution/export_plans.py
```

**验收**（新建 `solution/check_pool.py` 自动检查以下 5 条，全部满足打印 `POOL OK`）
1. `final.csv` 恰好 1200 行（100 用例 × 3 问题 × 4 个 N），全部 `feasible=True`；
2. 所有 `speedup ≥ 1.0`；
3. 每个用例、每个问题：`makespan(N) ≤ makespan(N−1)`，N=2 与单核基准比；
4. 每个用例、每个 N：P3 冠军 makespan ≤ P2 冠军 makespan；
5. 每个配置的冠军 makespan ≤ 该配置在 `main/baseline/ablation/granularity/p3_compare` 五个 CSV 中的最小值（已知最优；按 `(case, eval_problem, num_cores)` 分组，`eval_problem` 为空时取 `problem`）。
另外：`summary.json` 中 P2 N=5 的 `speedup_mean` ≥ 3.92（基底清单估算 3.928，只会更好）。若第 5 条不满足，打开 `pool_mismatch.csv` 报告，不要改规则。

---

## T08　最终方案官方 CLI 复核（D7.4）

**新建** `solution/verify_final.py`：
- 参数：`--problems`（默认 `1 2 3`）、`--jobs`（默认 8）、`--cases`（默认全部）。
- 对 `results/final_plans/p<P>/n<N>/<case>_multicore_res.json`（N=1..5），用 `subprocess` 调用官方 CLI：
  `python code/multicore_cut_evaluate_problem_<P>.py data/<case>.json <plan> --config data/config.txt -o <tmp>/<case>_p<P>_n<N>.json`
- 读取输出 JSON 的 `makespan`、`data_movement_bytes.added_copy_bytes`、（P3）`cache_stats.hit_rate`，与 `results/final_plans/manifest.csv`（N=1 与 `results/singlecore_baseline.json`/`n1.csv`）比较，要求**完全相等**（命中率比较到 1e-9）。
- 输出 `results/verify_final.csv` 与一行总结：`checked=<数量> mismatches=<数量>`。

**命令**
```bash
python solution/verify_final.py --problems 2 3 --jobs 16
python solution/verify_final.py --problems 1 --jobs 16
```
（P1 的 CLI 复核很慢，T09 完成后也不能用快速评估器代替，本任务必须用官方 CLI。）

**验收**：两次输出都是 `mismatches=0`，且 `checked` 分别为 `2×100×5` 与 `100×5`。

---

## T09　逐字节等价的快速评估器（C3）

**步骤**
1. 新建目录 `solution/npu/fasteval/`，把 `code/` 下这 9 个文件复制进去并加前缀 `fe_`：`contest_io.py`、`evaluation_validation.py`、`schedule_step1.py`、`schedule_step2.py`、`schedule_step3.py`、`singlecore_evaluate.py`、`multicore_cut_evaluate_problem_1.py`、`multicore_cut_evaluate_problem_2.py`、`multicore_cut_evaluate_problem_3.py`。新增空的 `__init__.py`。
2. 把副本中所有 `from <模块名> import` / `import <模块名>`（模块名为上面 9 个之一）改成相对导入 `from .fe_<模块名> import`。这是唯一允许的非性能修改。
3. 提交一次（`T09a: 原样复制`），然后运行差分测试（第 6 步）确认副本与官方完全一致，再开始优化。
4. 性能分析：对 `case_014`、P1、N=5 的最终方案运行 `python -m cProfile -s cumtime`，记录累计时间前 10 的函数到 `results/fasteval_profile_before.txt`。
5. 只对前 10 名中的函数做优化，只允许以下四类变换，每做一类单独提交一次并重跑第 6 步：
   - (a) 把列表上的 `in`、`.index()`、`.remove()` 换成 dict/set 查找，**不改变任何迭代顺序**；
   - (b) 在集合内容不变期间缓存 `sorted(...)` 的结果；
   - (c) 把"按 `seq` 顺序线性扫描、取第一个满足条件的元素"换成以 `seq` 位置为键的最小堆或指针，保证选中的元素与原扫描完全相同；
   - (d) 在只影响日志、trace、异常信息的代码路径上加 `collect_debug=False` 开关并在快速路径中关闭，不影响任何数值输出。
   **禁止**：改变浮点运算的顺序或表达式、改变任何并列打破规则、删除任何校验分支。
6. **差分测试**：新建 `solution/check_fasteval.py`。测试集 =
   - `results/plans/` 与 `results/plans_final/` 下全部方案文件；
   - `results/samples.json` 中 `pilot20` 的 20 个用例 × N=2..5 × P1..3 × `variants.LABELS` 的全部标签。
   对每个方案，官方结果**只取缓存**（`default_cache().get`），缓存未命中的方案跳过、不做官方评估；对命中的方案调用快速副本，比较 `evaluate._summarise` 产出的全部字段（除 `eval_seconds`）。要求完全相等。
7. **接入**：`solution/npu/evaluate.py` 新增 `evaluate_fast(problem, case, plan) -> dict`，内部调用 `fasteval` 副本，返回结构与 `evaluate_plan` 相同。`solution/npu/experiment.py` 的 `run_portfolio` 在 `problem == 1` 且环境变量 `NPU_FASTEVAL=1` 时：先用 `evaluate_fast` 评出全部候选并选出冠军，再对冠军调用 `default_cache().evaluate`（官方）一次；若官方值与快速值不等，记录到 `results/fasteval_mismatch.csv` 并回退为官方评估全部候选。同时去掉 T06 保留的 P1 裁剪（`NPU_FASTEVAL=1` 时 P1 也跑满候选）。

**验收**
```bash
python solution/check_fasteval.py --jobs 16
set NPU_FASTEVAL=1 && python solution/solve.py data/case_014.json --problem 1 --cores 5 -o %TEMP%\c14.json
```
通过标准：`check_fasteval.py` 打印 `mismatches=0` 且实际比较的方案数 ≥ 3000，其中 P1 ≥ 1000；`case_014` P1 N=5 端到端 ≤ 600 s，且官方复核的 makespan ≤ 快照中该配置的冠军值。
**失败处理**：差分测试不为 0 时，回退到上一个通过的提交，放弃引起不等的那一类变换，继续下一类。若四类都做完后 `case_014` 仍 > 600 s，保留已有提速，在 `results/fasteval_report.md` 写明实测时间，不再继续优化。

---

## T10　算子级事件模拟代理（C2）

**新建** `solution/npu/simproxy.py`，提供 `estimate(g, plan, problem, cfg) -> float`。模型规则（全部写死，不加开关）：
1. **核内算子序列**：按方案的核内子图顺序排列子图；子图内算子按 `g.topo` 中的位置排序（评估器 step1 的顺序无法廉价复现，这里用拓扑序近似）。
2. **搬运算子**：
   - 图输入张量：在每个核上第一次被使用前插入一个 MTE2 搬运，字节 = 张量大小；
   - 跨核边：生产核在生产算子之后插入 MTE3 搬出，消费核在第一次使用前插入 MTE2 搬入；消费核的搬入就绪时间 = 生产核搬出完成时间 + `cross_core_copy_delay_cycles`（P2/P3）；
   - P1：子图即 Task，按 `estimate_scene_a_from_plan` 的 Task 激活规则处理（直接调用它，见 T14 的迁移），不走下面的流水模拟；
   - 不模拟 spill。
3. **流水**：每核四条流水 `PIPE_M`、`PIPE_V`、`PIPE_MTE2`、`PIPE_MTE3` 各自串行。计算算子时长 = `g.cycles(v)`；搬运时长 = 字节 / (`bandwidth` / 当前在途 DDR 搬运数)，在途数在搬运开始时刻计算并在其执行期间视为常数（这是对评估器公平共享的简化）。P3 中若张量此前已被任一核搬入过且在一个大小为 `cache_capacity_bytes` 的 FIFO 中仍在，则时长 = 字节 / `cache_bandwidth_bytes_per_cycle`，且不计入 DDR 在途数。
4. **全局申请序**（不变量 3，必须实现）：每核维护一个指针 `alloc_ptr`，序列中第 i 个算子的开始时间 ≥ 第 i−1 个算子的开始时间。即核内按序发射、各流水可乱序完成。
5. 返回值 = `max(所有算子完成时间, DDR 总字节 / bandwidth)`。

**修改** `solution/validate_model.py`：`--proxy sim` 使用本模块（T04 已预留）。

**命令**
```bash
python solution/validate_model.py --all --proxy sim --jobs 16
```

**验收（决定后续是否接入，结论写入 `results/simproxy_gate.json`）**
- `pass_rank`：P2 与 P3 的用例内 Spearman 中位数都 ≥ 0.60，且 Recall@3 都 ≥ 60%；
- `pass_p1`：P1 用例内 Spearman 中位数 ≥ 0.93（不低于旧代理）。
写入 `{"pass_rank": bool, "pass_p1": bool, "metrics": {...}}`。
**后续规则**（其他任务读取此文件，不再判断）：
- `pass_rank=true`：T13、T21 用 `simproxy` 排序；`TrafficState.cost` 不改。
- `pass_rank=false`：T13 改用"全部候选交官方评估、K=4"，T21 取消。
- 本任务**不**修改 `algorithms._local_search`（局部搜索是否换代理，放到 T16 消融后再说，不在本规格范围内）。

---

## T11　单算子子图 + 容量感知表调度（C1）

**新建** `solution/npu/listsched.py`，提供 `schedule(g, core_of_op, levels, problem, cfg, alpha, mu, nu, noise=0.0, seed=0) -> (orders: list[list[op]])`。

**预计算**
1. 边通信代价：`c(u, v) = 0`（同核）；否则 `delay + bytes(u, v) / bandwidth`，`delay` 为 P1 的 `task_cross_core_wait_cycles` 或 P2/P3 的 `cross_core_copy_delay_cycles`，`bytes(u, v)` = `u` 的输出张量中被 `v` 消费的张量大小之和（用 `g.op_out[u]` 与 `g.consumers`；经 COPY 收缩的边若找不到共享张量，`bytes = 0`）。
2. 上行秩：`rank_u(v) = cycles(v) + max over s in g.succs[v] of (c(v, s) + rank_u(s))`，汇点为 `cycles(v)`，按 `g.topo` 逆序计算；再除以全图最大值归一化到 [0, 1]。
3. 张量所在缓冲：张量 `pos` 为 `L1` 记入 L1，`UB` 记入 UB，`DDR` 不计；容量取 `cfg['L1']`、`cfg['UB']`。

**模拟（确定性）**
- 状态：每核四条流水的空闲时刻、每核 L1/UB 驻留字节、每个 (张量, 核) 的剩余本地消费者数、每个算子的完成时刻。
- 就绪：一个算子的全部前驱都已调度。就绪时刻 = `max(前驱完成 + c(前驱, v))`。
- 每一步：对每个核 k，从该核就绪集合中取 `rank_u` 最大的 64 个（不足则全取），对每个候选计算
  `score = rank_u(v) − mu · Δlive(v) / cap + nu · [pipe(v) ≠ 该核当前最晚空闲的流水] + noise · G`
  其中 `Δlive(v)` = v 新分配的输出字节（L1/UB）− v 执行后可释放的输入字节（v 是该张量在本核的最后一个剩余消费者时），`cap` 为该张量所属缓冲容量（多个缓冲时取 L1），`G` 为 `random.Random(seed)` 产生的标准 Gumbel 噪声。
  可行条件：分配后驻留 ≤ `alpha × 容量`（L1、UB 分别判断）。有可行候选时取 `score` 最大者；没有时取 `Δlive` 最小者（并列按 op id 升序）。
  该候选的开始时刻 = `max(就绪时刻, 对应流水空闲时刻)`。
- 在所有核的候选中，提交开始时刻最早者（并列取核编号小者），更新状态，把算子追加到 `orders[k]`。
- 所有算子调度完后，对每个 `orders[k]` 按 `(levels[v], 追加位置)` 做稳定排序。

**方案成形**（在 `solution/npu/algorithms.py` 中）
1. `cap_ls` 第 262–265 行签名新增参数 `alpha=0.8, mu=0.0, nu=0.0, noise=0.0`，`subgraph_mode` 增加取值 `'op'`。
2. 第 297 行 `if subgraph_mode == 'block':` 之后新增 `'op'` 分支：`core_of_op` 由 S2 的 `core` 得到（同 `_plan_from_core_map` 第 159 行的写法），`levels = stratify.cross_core_levels(g, core_of_op)`（T12 完成后改为按 `level_mode` 取），调用 `listsched.schedule`，然后每个算子一个子图，子图 id 按 `(levels[v], 核编号, 核内位置)` 递增分配，`core_schedules[k]` 为 `orders[k]` 对应的子图 id 序列，最后 `evaluate.make_plan`。
3. 第 307–333 行 `candidate_params`：当 `problem in (2, 3)` 且 `level == 'full'` 时，在列表末尾追加 4 个候选（顺序固定）：
   - `dict(block_cap=0.35, init='rr', subgraph_mode='op', alpha=0.8, mu=1.0, nu=0.5)`
   - `dict(block_cap=0.35, init='rr', subgraph_mode='op', alpha=1.0, mu=1.0, nu=0.5)`
   - `dict(block_cap=0.35, init='rr', subgraph_mode='op', alpha=0.8, mu=0.0, nu=0.0)`
   - `dict(block_cap=0.15, init='rr', subgraph_mode='op', alpha=0.8, mu=1.0, nu=0.5)`
   P1 不追加（P1 每个子图是一个 Task，单算子子图会产生上万个 Task）。

**试点（必须先做）**
```bash
python solution/run_experiments.py --stage main --jobs 16 --problems 2 3 --cases <pilot20 列表> --out results/pilot_op.csv
```
`<pilot20 列表>` 从 `results/samples.json` 读取。
试点判定（写入 `results/pilot_op_gate.json`）：
- 记录每个 op 候选的 `eval_s`。若有候选 `eval_s > 120`，令 `OP_MAX_N` = 这些用例中最小的 `n_ops`；否则 `OP_MAX_N = null`。
- 在 `candidate_params` 中，只有当 `OP_MAX_N` 为空或 `g.n < OP_MAX_N` 时才追加 op 候选。`candidate_params` 目前拿不到图规模，因此给它增加可选参数 `n_ops=None`，并在 `experiment.run_portfolio`（第 104 行）与 `solve.py`（第 36 行）调用处传入 `g.n`；`OP_MAX_N` 从 `results/pilot_op_gate.json` 读取，文件不存在时视为 `null`。

**全量**
```bash
python solution/run_experiments.py --stage main --jobs 16 --problems 2 3 --out results/main_p23.csv
python solution/merge_main.py
python solution/run_experiments.py --stage p3 --jobs 16 --out results/p3_compare.csv
python solution/build_pool.py --jobs 16
```

**验收**（新建 `solution/check_op_mode.py`，输出写 `results/op_mode_report.json`）
1. 所有 op 候选方案都被官方评估器判为可行（`feasible=True` 比例 = 100%）；有不可行的，停止并报告，不要继续。
2. `final.csv` 中 P2、P3 每个 N 的算术平均加速比 ≥ T07 结束时的值（不能退步）。
3. 报告：op 候选成为冠军的配置数；按三层 ρmax 分层的平均加速比变化；40 个 spill 用例（`spill_added_copy_bytes > 0` 的 P2 N=4 冠军所在用例，以快照为准）的 spill 字节总和变化；`case_001`–`case_005` 的 P2 算术平均（外部参照，与同学论文 2.26/3.26/3.98/4.75 并列输出）。
4. `mu=0, nu=0` 候选相对 `mu=1, nu=0.5` 候选的配对比较（`stats.paired`），写入报告。

---

## T12　单调层指派（C8）

**新建** `solution/npu/levels.py`：
- `asap(g, core_of_op)`：等同 `stratify.cross_core_levels`。
- `check_monotone(g, core_of_op, l) -> None`：对每条边 u→v，同核要求 `l[v] ≥ l[u]`，跨核要求 `l[v] ≥ l[u] + 1`，违反则抛 `ValueError`。
- `alap_fill(g, core_of_op)`：
  1. `l = asap(...)`，`L = max(l)`；
  2. 按 `g.topo` 逆序处理每个 v：`upper(v) = min over s in succs of (l[s] − [core(s) ≠ core(v)])`，无后继时 `upper = L`；候选层区间 `[l[v], upper(v)]`；
  3. 维护 `load[(k, ℓ)]` = 核 k 在层 ℓ 的算子周期和；在区间内选 `load[(core(v), ℓ)]` 最小的 ℓ，并列取最小 ℓ；更新 `l[v]` 与 `load`；
  4. 返回 `l`。
- `compress(g, core_of_op, l, frac=0.05)`：
  1. 计算每层总周期 `W[ℓ]` 与均值 `W̄`；
  2. 对 ℓ = 1..L 递增：若 `W[ℓ] < frac × W̄`，对该层每个 v，若 `max over u in preds of (l[u] + [core(u) ≠ core(v)]) ≤ ℓ − 1` 则 `l[v] = ℓ − 1`；
  3. 把出现的层号按升序重新编号为 0, 1, 2, …（去掉空层）；
  4. 返回 `l`。
- 所有函数返回前都调用 `check_monotone`。

**修改**
1. `solution/npu/stratify.py` 第 59–61 行 `build_subgraphs` 签名新增 `levels=None`；第 68 行改为 `levels = levels if levels is not None else cross_core_levels(g, core_of_op)`，并在其后调用 `levels_mod.check_monotone(g, core_of_op, levels)`（`from . import levels as levels_mod`，避免与参数重名）。
2. `solution/npu/algorithms.py`：`cap_ls` 新增参数 `level_mode='asap'`（取值 `asap`、`alap_fill`、`compress`、`alap_compress`）；`_plan_from_core_map`（第 157–163 行）新增同名参数，按模式计算 levels 后传给 `build_subgraphs`；T11 的 op 分支同样按 `level_mode` 取 levels。
3. `candidate_params`：对所有问题在 `level == 'full'` 时末尾追加
   `dict(block_cap=0.35, init='rr', level_mode='alap_fill')`、`dict(block_cap=0.35, init='rr', level_mode='alap_compress')`。

**验收**
1. 新建 `solution/check_levels.py`：对全部 100 个用例、N=2..5、随机 3 种核分配（`assign.random_assign`，种子 0/1/2），三种非 ASAP 模式都能通过 `check_monotone`，且生成的方案经 `default_cache().evaluate(2, ...)` 可行。先只跑 P2（便宜），打印 `LEVELS OK`。
2. 按 T11 的"全量"命令（P1 在 T09 通过后同样重跑）重跑并重建池；`final.csv` 各问题各 N 算术平均不退步。
3. 报告写入 `results/levels_report.json`：新候选成为冠军的配置数、平均层数（`max(l)+1`）在三种模式下的均值。

---

## T13　优先级采样组合（C9）

**修改** `solution/npu/experiment.py` 的 `run_portfolio`：在候选循环结束后，若 `problem in (2, 3)` 且已评估的候选中存在 op 候选，则取 makespan 最好的 op 候选的参数，令 `noise=0.05`，`seed = 1..K`：
- 若 `results/simproxy_gate.json` 中 `pass_rank=true`：K=16，全部用 `simproxy.estimate` 排序，取前 3 交官方评估；
- 否则：K=4，全部交官方评估。
这些方案的 `variant` 记为 `s1`…`sK`，参与冠军选择。T05 的 `variants.LABELS` 同步增加 `s1..s16`（`build` 时需要知道基准参数，从同配置的 op 冠军参数读取；为此 `run_portfolio` 把所选基准参数写进记录的 `params` 字段）。

**验收**：重跑 P2/P3 主阶段与池；报告写入 `results/sampling_report.json`：`s*` 成为冠军的配置数、K 与算术平均加速比的关系（K 取 1、4、16 时的平均值，K=1 指不采样）、新增官方评估次数。`final.csv` 不退步。

---

## T14　P1 代理驱动模拟退火（C5 替换版）

**迁移**：把 `solution/validate_model.py` 第 26–96 行 `estimate_scene_a_from_plan` 原样移到新文件 `solution/npu/proxy_a.py`，`validate_model.py` 改为从该模块导入（行为不变）。

**新建** `solution/npu/p1_anneal.py`，提供 `anneal(g, plan, cfg, iters=3000, seed=20260924) -> list[plan]`（返回代理最好的前 3 个不同方案）。
- 表示：`mapping`（op → Task）与 `schedules`（每核 Task 序列）。
- 邻域（每次等概率选一种）：
  1. **合并**：随机选一个核上相邻的两个 Task A、B；若 Task 商图中不存在经其他 Task 的 A→…→B 路径（用可达性检查），把 B 的算子并入 A；
  2. **拆分**：随机选一个算子数 ≥ 2 的 Task，按成员在 `g.topo` 中的位置排序，从中点切成前后两个 Task，后者紧跟前者放在同一核；
  3. **换核**：随机选一个 Task，移到另一个随机核，并把该核的 Task 顺序按"Task 内最小拓扑位置"重新升序排列。
- 每个邻居生成后检查合法性：Task 商图无环、每核顺序与商图依赖一致；不合法直接丢弃（不计入迭代次数，最多重试 20 次）。
- 适应度：`proxy_a.estimate_scene_a_from_plan`。
- 退火：初温 `T0 = 0.02 × 初始适应度`，每次迭代 `T ← T × (1e-3)^(1/iters)`，按 Metropolis 准则接受。
- 记录全过程中适应度最小的 3 个不同方案（按 `plan_hash` 去重）。

**接入**：`experiment.run_portfolio` 在 `problem == 1` 时，候选循环结束后，以当前冠军为起点调用 `anneal`，把返回的 3 个方案交官方评估，`variant` 记为 `sa1`…`sa3`，参与冠军选择。`variants.LABELS(1, N)` 同步增加 `sa1..sa3`（`build` 需要起点冠军，从 `final.csv` 读取）。

**命令**：重跑 P1 主阶段（`NPU_FASTEVAL=1`，前提是 T09 通过；T09 没通过就不设该变量，接受较长运行时间），再重建池。

**验收**：`final.csv` P1 各 N 算术平均不退步；报告写 `results/p1_anneal_report.json`：`sa*` 成为冠军的配置数、每配置新增官方评估次数（应恰为 3）、每配置退火耗时的中位数与最大值（最大值 ≤ 60 s，超过则把 `iters` 降为 1500 重跑一次，仍超过就保留并在报告中注明）。

---

## T15　外部基线与预算对等基线（D1）

**新增算法**（写入 `solution/npu/algorithms.py` 的 `ALGORITHMS`）
1. `heft`：按 T11 的 `rank_u` 降序遍历算子；每个算子放到"最早完成时刻"最小的核（核时间线为单一串行时间线，完成时刻 = `max(核空闲, 前驱完成 + c(前驱, v)) + cycles(v)`），并列取核编号小者；得到 `core_of_op` 后用 `stratify.build_subgraphs`（ASAP 层，不切片）成形。
2. `hgp`（超图划分 + 分层）：
   - 尝试 `python -m pip install mtkahypar`。成功：顶点为可切分算子，权重 `cycles + 1`；超边为每个张量（其 producers ∪ consumers 中至少 2 个算子），权重为张量大小；`k = N`，`epsilon = 0.03`，目标 `km1`，种子 0；
   - 失败则尝试 `python -m pip install pymetis`，用算子图（边权 = 两端共享张量大小之和）做 `k = N` 划分；
   - 两者都失败：该算法返回 `NotImplementedError`，并在 `results/baseline2_status.txt` 写明原因；
   - 划分结果作为 `core_of_op`，用 `stratify.build_subgraphs` 成形。
3. `single`：已存在，作为参照列。

**预算对等**：新增阶段 `baseline2`（`run_experiments.py` 的 `choices` 与分发逻辑中增加）。对每个配置，每个基线算法按下列参数各跑一次，记录全部，并额外输出每个算法的"组合最好"：
- `topo`、`balance`：`blocks_per_core ∈ {2, 4, 8, 16}`；
- `comm`：`block_cap ∈ {0.08, 0.15, 0.35, 0.6}`（需给 `baseline_comm` 增加 `block_cap` 参数，第 207–211 行）；
- `random`：`seed ∈ {0, 1, 2, 3, 4}`；
- `hgp`：`seed ∈ {0, 1, 2, 3}`；
- `heft`：只跑一次（无参数）。
全部结果写 `results/baseline2.csv`，`variant` 字段记参数。

**命令**
```bash
python solution/run_experiments.py --stage baseline2 --jobs 16 --problems 2 3
python solution/run_experiments.py --stage baseline2 --jobs 16 --problems 1      # T09 通过后加 NPU_FASTEVAL 不适用于基线，需官方评估；时间允许才跑
```

**汇总**：`make_report.summary` 增加 `out['baseline2']`：对每个问题、N=4，每个算法给出单配置（默认参数）与组合最好两种口径的 `stats.describe`，以及与 `final.csv` 冠军的 `stats.paired`（Holm 校正）。`fill_paper.py` 增加占位符 `TABLE_BASELINE2`（列：算法 | 口径 | 问题 1 | 问题 2 | 问题 3；单元格：算术平均 [CI]，相对 CAP-LS 的差、p 值、胜/平/负）。

**验收**：`baseline2.csv` 行数 = 配置数 × 参数组合数（允许 `hgp` 全部为不可用）；`summary.json` 中 `baseline2` 存在；`fill_paper.py` 能替换 `TABLE_BASELINE2`。

---

## T16　消融体系重建（D2）

**新增阶段** `ablation2`（`run_experiments.py`），基准配置固定为 `c2` 的参数 `dict(block_cap=0.35, init='rr')`，变体（名称 → 参数覆盖）：

| 变体 | 参数 |
|---|---|
| `full_c2` | 无 |
| `no_comm` | `use_affinity=False` |
| `no_sync` | `sync_weight=0.0` |
| `no_localsearch` | `local_search=False` |
| `no_level` | `subgraph_mode='block'` |
| `no_level_no_comm` | `subgraph_mode='block', use_affinity=False` |
| `max_ops500` | `max_ops=500` |
| `op_full` | `subgraph_mode='op', alpha=0.8, mu=1.0, nu=0.5`（仅 P2/P3） |
| `op_mu0` | 同上但 `mu=0.0` |
| `op_nu0` | 同上但 `nu=0.0` |
| `op_alpha1` | 同上但 `alpha=1.0` |
| `lvl_alap` | `level_mode='alap_fill'` |
| `lvl_compress` | `level_mode='alap_compress'` |

SCC 合并与 σ 线性扩展不做消融：去掉它们会让方案不可行或无法构造，论文中写明这一点即可（T23）。

**组合层与择优层**（新建分析脚本 `solution/portfolio_analysis.py`，只读 CSV，不跑评估）：
1. 贪心前向选择：用 `results/pool.csv` 中的主候选标签（`c*`、`s*`、`sa*`），对每个问题、N=4，逐步加入使算术平均加速比增加最多的标签，输出曲线（候选数 → 算术平均）。
2. 留一消融：从全部标签中去掉一个，重新取冠军，输出算术平均的变化。
3. 择优层：对每个配置，用 `simproxy`（若 `pass_rank=true`）或 `TrafficState.cost`（否则）在主候选中选一个，与官方择优的冠军比较，输出算术平均与 `stats.paired`。这个数字写进论文，回答"离开评估器还剩多少"。

**命令**
```bash
python solution/run_experiments.py --stage ablation2 --jobs 16 --problems 2 3
python solution/run_experiments.py --stage ablation2 --jobs 16 --problems 1
python solution/portfolio_analysis.py
```

**验收**：`results/ablation2.csv` 与 `results/portfolio_analysis.json` 存在；`summary.json` 新增 `ablation2`（每个变体的 `describe` 与相对 `full_c2` 的 `paired`，Holm 校正）；`fill_paper.py` 增加并能替换 `TABLE_ABLATION2`、`TABLE_GREEDY`、`PROXY_ONLY_P2_N4`。

---

## T17　P3 的 L2 专项与命中来源拆分（D8）

### T17.1 分层样本
在 `solution/sample_cases.py` 中填充 `l2_strata`：用 `results/p3_compare.csv` 的 N=4 同方案 L2 收益（P2 makespan / P3 makespan），三层：`>1.05` 全取；`1.01–1.05` 用 `random.Random(20260926)` 抽 10 个；`≤1.01` 用 `random.Random(20260927)` 抽 10 个。

### T17.2 命中来源拆分（不需新评估以外的算力）
新建 `solution/l2_sources.py`：对 `final.csv` 中 P3 的全部冠军，调用 `evaluate.evaluate_plan(3, case, plan, full=True)`（这是 0.1 第 4 条的第二个例外：缓存不保存事件流，必须重跑；只跑 P3 冠军，共 400 次），读取 `_result['cache_events']`：
- 对每个 `hit` 事件分类：`tensor_id` 是图输入张量（`g.producers[tid]` 为空）→ `input_reuse`；`tensor_id` 的生产算子与事件的 `core_id` 在同一核 → `spill_reload`；否则 → `cross_core_mid`。
- 对每个张量的 `miss` 事件按时间排序，第一个之后的 miss：若在它之前没有该张量的 `insert` 事件 → `concurrent_first_read`；若有 `insert` 且之后被 `evicted_tensor_ids` 淘汰 → `fifo_evicted`。
- 输出 `results/l2_sources.csv`（每个配置一行，各类字节数）与汇总 `results/l2_sources.json`。

### T17.3 两种协议的扫描（新增阶段 `l2study`）
样本 = `l2_strata`；N ∈ {2, 4, 5}；参数网格：`cache_capacity_bytes ∈ {0, 65536, 262144, 1048576, 4194304, 16777216}` × 固定带宽 250，以及 `cache_bandwidth_bytes_per_cycle ∈ {60, 125, 250, 500, 1000}` × 固定容量 1048576。`capacity=0` 的点用 problem 2 评估代替（等价于无 L2）。
- 协议 a（固定方案）：用 `final.csv` 的 P3 冠军方案，在 `paths.set_config_override` 下评估；
- 协议 b（重新优化）：在覆盖配置下跑完整候选集（`candidate_params(3, N, 'full')`，与正式结果同一候选集，**不要**用 `'fast'`）。
每点记录：makespan、命中率、子图数、跨核字节、胜出候选标签。写 `results/l2study.csv`。

### T17.4 其他两项
- `cachemodel.py` 接入：对 `final.csv` P3 N=4 的 100 个冠军，用 `cachemodel.simulate_fifo_hits` 预测命中率，与官方命中率一起写入 `results/l2_pred_vs_official.csv`（供 T22 画散点）。
- θ 扫描：`partition.make_blocks` 的 `theta_candidates` 分别固定为 `(INF,)`、`(16,)`、`(4,)`、`(1,)`，在 `l2_strata` × N=4 上跑 P3（需要给 `cap_ls` 增加 `theta_candidates` 透传参数）。写 `results/theta_scan.csv`。

**验收**：四个输出文件都存在；`l2_sources.json` 中三类命中字节之和等于官方 `cache_hit_bytes` 之和；`l2study.csv` 行数 = 样本数 × 3 个 N × 11 个参数点 × 2 个协议。

---

## T18　领读—跟读排序（C10）

**前提**：T17.2 的 `concurrent_first_read` 字节占 P3 N=4 全部 miss 字节的比例 ≥ 5%。不满足时本任务取消，在 `results/c10_skipped.txt` 写明比例。

**修改** `solution/npu/listsched.py`：新增参数 `l2_follow=False`。为真时（仅 P3）：
1. 预计算"跨核多读者张量"：被 ≥ 2 个核上的算子读取的图输入张量与跨核中间张量。
2. 对每个这样的张量，领读核 = 读者核中编号最小的那个。
3. 调度时，非领读核上读取该张量的算子，就绪时刻额外约束为 ≥ 领读核首个读取算子的预计完成时刻 + `size / bandwidth`（模拟 COPY_IN 完成并插入 Cache）。
4. 为保证 FIFO 复用距离，若自领读起已调度的全部核上"新读取的不同张量字节数"累计超过 `cache_capacity_bytes`，则取消该张量的跟读约束。

**候选**：`candidate_params` 在 `problem == 3` 时追加 `dict(block_cap=0.35, init='rr', subgraph_mode='op', alpha=0.8, mu=1.0, nu=0.5, l2_follow=True)`。

**验收**：重跑 P3 主阶段并重建池，`final.csv` P3 不退步；在 L2 收益 >1.05 的用例上报告命中率与 L2 收益变化，写入 `results/c10_report.json`。

---

## T19　界与参照（D6）

新建 `solution/bounds.py`（只读分析，除第 4 点外不评估）：
1. 逐用例 `MK / LB`（`plots.lower_bound` 同一公式，数据源 `final.csv`），输出 CDF 数据到 `results/bounds_cdf.csv`；
2. 单核归一化效率 `(LB_N / MK_N) / (LB_1 / MK_1)`，`MK_1` 为单核基准；
3. 可达加速比上界 `MK_1 / LB_N` 与"达到上界的比例" `speedup / (MK_1 / LB_N)`；
4. 大预算经验参照：样本 = `pilot20` 中前 15 个（按 `samples.json` 顺序），P2、N=4。给 `cap_ls` 的 `init` 增加取值 `'random'`（调用 `assign.random_assign(bs, active, seed)`，第 285–290 行分支中加一支）。对每个用例跑 200 个方案：`seed = 0..199`，`block_cap` 按 `(0.08, 0.15, 0.35, 0.6)` 循环，`init='random'`，全部官方评估（走缓存）。经验参照 = min(这 200 个, `final.csv` 冠军)。输出冠军与参照的差距。
输出 `results/bounds.json`；`fill_paper.py` 增加 `BOUND_EFF_N4`、`BOUND_GAP_EMP`。

**验收**：`bounds.json` 含上述四部分；第 4 部分每个用例恰好 200 条评估记录。

---

## T20　超参数过拟合检验（D5）

新建 `solution/cv_select.py`（只读 `results/pool.csv`，不评估）：
1. 用例按 `paths.all_cases()` 排序，偶数下标为折 A，奇数下标为折 B。
2. 在折 A 上对主候选标签做贪心前向选择，选 4 个；在折 B 上用这 4 个取冠军，计算算术平均加速比；与"在折 B 上用全部标签"的算术平均比较，得到折外损失。再交换 A、B 做一次。
3. 同样方法选 `block_cap` 默认值：在折 A 上从 `g_*` 标签里选算术平均最好的 β，在折 B 上与默认 0.35 比较。
输出 `results/cv_select.json`；`fill_paper.py` 增加 `CV_LOSS`（两折损失的最大值，百分比，一位小数）。

**验收**：`cv_select.json` 存在，两个折都有结果。

---

## T21　冠军邻域精修（C4）

**前提**：`results/simproxy_gate.json` 中 `pass_rank=true`，否则取消本任务并在 `results/c4_skipped.txt` 写明。

新建 `solution/npu/refine.py`，提供 `refine(g, plan, problem, cfg, n_neighbors=200, top_k=5, seed=20260924) -> list[plan]`：
- 从冠军方案读出 `core_of_op` 与每个算子的层 `l`（子图的层可由 (核, 子图在核内序号) 反推：对非 op 模式方案，按 `stratify.cross_core_levels` 重算；对 op 模式方案，直接用 ASAP 层）；
- 邻居三类，各占三分之一：(a) 随机算子换到随机其他核，层取满足 `check_monotone` 的最小值，其后继若违反约束则级联上移；(b) 随机选两个不同核上同层的算子交换核；(c) 随机算子在 `[当前层, upper]` 内上移一层；
- 每个邻居用 `levels.check_monotone` 检查，不合法丢弃；用 `stratify.build_subgraphs(..., levels=l)` 成形；
- 用 `simproxy.estimate` 排序，返回前 `top_k` 个。

**接入**：在 `build_pool.py` 第 1.5 步（取冠军）之后、第 2 步（跨问题）之前，仅对 `problem in (2, 3)`：调用 `refine`，把 5 个方案官方评估，标签 `r1..r5`，参与冠军选择。

**验收**：`final.csv` 不退步；报告 `results/refine_report.json`：`r*` 成为冠军的配置数、每配置新增官方评估次数（恰为 5）、端到端时间（P2/P3 仍 ≤ 600 s）。

---

## T22　图表增补与 trace 剖析（E1、E4）

在 `solution/npu/plots.py` 新增以下函数（数据只读 `results/*.csv|json`），并在 `make_report.py` 第 291–314 行的 `if args.figures:` 块末尾依次调用：

| 函数 | 输出文件 | 数据 |
|---|---|---|
| `fig_speedup_ci()` | `fig05c_speedup_ci.png` | `summary.json` 的 `speedup_mean` 与 `speedup_ci`，误差棒 |
| `fig_monotone_heatmap()` | `fig18_monotone.png` | `final.csv`，行 = 用例，列 = (问题, N)，颜色 = `MK(N)/MK(N−1)` |
| `fig_greedy_curve()` | `fig19_greedy.png` | `portfolio_analysis.json` |
| `fig_anytime()` | `fig20_anytime.png` | `pool.csv` 按标签顺序的累计最好值 |
| `fig_p2_vs_p3()` | `fig21_p2p3.png` | `final.csv`，逐用例 P2 与 P3 冠军的散点 |
| `fig_l2_strata()` | `fig22_l2_strata.png` | `l2study.csv`，三层分别画容量曲线与带宽曲线 |
| `fig_traffic_split()` | `fig23_traffic_split.png` | `final.csv`，每个问题/N 的 `partition_added` 与 `spill_added` 堆叠柱 |
| `fig_proxy_within()` | `fig24_proxy_within.png` | `model_validation_summary_{legacy,sim}.json`，用例内 Spearman 分布与 Recall@K 柱 |
| `fig_bounds_cdf()` | `fig25_bounds_cdf.png` | `bounds_cdf.csv` |
| `fig_baseline_wtl()` | `fig26_baseline_wtl.png` | `summary.json` 的 `baseline2` 胜/平/负 |
| `fig_l2_pred()` | `fig27_l2_pred.png` | `l2_pred_vs_official.csv` |

**trace 剖析（E4）**：新建 `solution/trace_gantt.py`。对 `case_003` 与 `pilot20` 中 `spill_added_copy_bytes` 最大的用例，P2、N=4，分别取三个方案：`a_no_level`、`c0`、`final.csv` 冠军。用官方 CLI 的 `--trace-output` 生成 trace JSON，画每个方案 0 号核四条流水的甘特图（横轴 cycle），并标出"四条流水同时空闲且该核仍有未完成算子"的区间（这就是申请序阻塞）。输出 `figures/fig28_trace_<case>.png`，并把每个方案的阻塞总 cycle 写入 `results/trace_stall.json`。

**验收**：`python solution/make_report.py --figures` 退出码 0，上表 11 个文件与 2 张 trace 图都生成。

---

## T23　论文文本修改（A2、A4、A5、A6、相关工作）

只改 `paper/论文.md`、`paper/04_实验章节.md`、`paper/05_附录.md`。所有新数字用占位符。按下表执行，每一行都是一次 Edit 操作（用 Edit 工具，不要用 heredoc 批量替换含 LaTeX 的文本，见 CLAUDE.md 最后一条）。

### T23.1 八处不一致（A2）

| # | 文件:行 | 锚点文本 | 改为 |
|---|---|---|---|
| 1 | `04_实验章节.md:22` | `跨用例聚合一律用**几何平均**` | "跨用例聚合按赛题定义用**算术平均**，几何平均与中位数作为补充指标" |
| 1 | `04_实验章节.md:40,47,58,61,85,121,125,127,164,173,248,284,324` | 各处"几何平均" | 改为"算术平均"；第 61 行整句改为"算术平均低于中位数，说明少数结构受限的难例拉低了均值（见 §10.3）"；第 248、359 行保留"几何平均"但加"（比值型指标）"（第 359 行不在前面的行号列表里，单独处理） |
| 2 | `论文.md:382` | `**P2-C 缓存压力估计**` 整条 | "**P2-C 子图规模上限**：用 `max_ops` 候选限制单个子图的算子数，间接抑制 Step2 换入换出；核内全序由 §7.x 的容量感知表调度（T11）显式控制驻留。" |
| 3 | `论文.md` §8.2 中"θ 可以取得更小"所在句 | `更小` | 删除该句；若 T17.4 完成，改为引用 `results/theta_scan.csv` 的结论占位符 `@@THETA_SCAN@@` |
| 4 | `论文.md:431` | `由 \`npu/cachemodel.py\`` 所在段 | 改为"……由 `npu/cachemodel.py` 计算，其 FIFO 命中估计与官方命中率的对照见图 27（@@L2_PRED_CORR@@）" |
| 5 | `04_实验章节.md:112` | `**自动选择只用 1 个核**` | "组合择优中的单核兜底候选保证该类用例的加速比不低于 1.00（全部 1200 个配置的最小加速比为 @@MIN_SPEEDUP_ALL@@）" |
| 6 | `04_实验章节.md:153–154` | `**同时取得更高加速比与更低额外搬运量**` | "取得显著更高的加速比，额外搬运量与基线持平（总量 @@ADDED_TOTAL_P2_N4@@ 对 @@ADDED_TOTAL_B3_P2_N4@@）" |
| 7 | `04_实验章节.md:57` | `**加速比随核数单调上升` | "**逐用例加速比随核数单调不降**（保底池保证，见图 18）" |
| 8 | `04_实验章节.md:380` | `换入换出已被切图本身消化掉了` | "换入换出仍占额外搬运的 @@SPILL_SHARE_P2_N4@@，核内全序调度把它降低了 @@SPILL_DROP_OP@@（见图 23）" |
| 8 | `04_实验章节.md:392` | `同一批用例对延迟的敏感度会显著上升` 所在句 | 删除 |
| — | `04_实验章节.md:237` | `$F$ 足以驱动局部搜索` | "旧代理 $F$ 的用例内秩相关中位数仅 @@PROXY_SP_P2_LEGACY@@，不足以驱动局部搜索；新事件模拟代理为 @@PROXY_SP_P2_SIM@@（表 10-x）" |
| — | `04_实验章节.md:257` | `**剩余差距主要来自跨核同步与负载不可整除性**` | "单核方案自身即为下界的 @@LB_SINGLE_MED@@ 倍（中位数），扣除这部分后 N=4 的平均效率为 @@BOUND_EFF_N4@@" |

新增占位符全部在 `fill_paper.py` 中实现，数据来源：`MIN_SPEEDUP_ALL`（`final.csv` 最小 speedup）、`ADDED_TOTAL_*`（`summary.json` 的 `added_copy_total` 与 `baseline.csv` 同口径汇总）、`SPILL_SHARE_P2_N4`（`final.csv` P2 N=4 的 `spill_added` 总和 / `added` 总和）、`SPILL_DROP_OP`（`op_mode_report.json`）、`PROXY_SP_P2_*`（`model_validation_summary_*.json`）、`LB_SINGLE_MED`、`BOUND_EFF_N4`（`bounds.json`）、`L2_PRED_CORR`（`l2_pred_vs_official.csv` 的 Spearman）、`THETA_SCAN`（`theta_scan.csv`）。

### T23.2 硬编码数字改为占位符
`04_实验章节.md` 中以下表格与句子目前是手写数字，全部改为由 `fill_paper.py` 生成的整表占位符：

| 锚点 | 新占位符 | 数据源 |
|---|---|---|
| `**表 10-1　平均加速比` 下的表 | `@@TABLE_10_1@@`（列：问题 × N，单元格 `算术平均 [CI] / 几何 / 中位 / 最小 / 最大`） | `summary.json` |
| `**表 10-2　按最大连通分量占比` 下的表 | `@@TABLE_STRATA@@` | `summary.json` 的 `speedup_by_strata` |
| `**表 10-3　只读 L2 相对无 L2 基线的收益` 下的表 | `@@TABLE_L2@@` | `summary.json` 的 `l2_gain`、`l2_hit_rate` |
| 第 138 行 `几何平均 0.91` | `@@RANDOM_P1_N4@@` | `baseline_speedup` |
| 第 173 行 `1.006`、`1.039` | `@@L2_GAIN_N2@@`、`@@L2_GAIN_N5@@` | `l2_gain` |
| 第 182 行 `1.008`、`1.43` | `@@L2_SPILL_GAIN@@`、`@@L2_SPILL_GAIN_MAX@@` | `l2_sources.json` |
| 第 248 行下方的下界比值表 | `@@TABLE_BOUND@@` | `summary.json` 的 `bound_gap` |
| `**表 11-2　粒度` 下的表 | `@@TABLE_GRAN@@` | `granularity.csv` |
| `**表 11-3　硬件参数敏感性` 下的表 | `@@TABLE_SENS@@` | `sensitivity.csv` |
| §10.7 的代理检验表 | `@@TABLE_PROXY@@`（列：问题 × 代理，Spearman/Kendall 中位、Top-1/3/5 减速比中位/90 分位/最大、Recall@1/3/5） | T04、T10 的 summary JSON |

完成后运行：`grep -nE "[0-9]\.[0-9]{2}" paper/04_实验章节.md`，除占位符、公式、文件名、章节号外不得再有实验数字。把剩余匹配行逐条列在提交说明里。

### T23.3 建模与定位（A5、A6）
1. `论文.md:242` 标题 `### 5.5 可行性的构造性刻画（本文核心引理）` → `### 5.5 可行性的构造性刻画（BSP 超步性质在本题约束下的推论）`。
2. 在 §5.5 引理之前插入一段（原文照录增强版 §3.2 表中"BSP 结构""可行性引理"两行的写法），并在引理之后追加"推论（单调层指派）"及其证明（增强版 C8 的"关键观察"段原样改写为定理形式）。
3. 在 §5.1 之后新增 §5.1′"问题分类与复杂度"一段，内容取自增强版 §3.2 表"问题分类""NP 难""列表调度界"三行，文献引用见 T23.5。
4. 在 §5.4 目标函数中，把场景 B 边界搬运项改写为 $\sum_t s_t(\lambda_t-1)$ 的连通度形式，并注明 COPY 规则（中间张量 $2s_t(\lambda_t-1)$，图输入 $s_t(\lambda_t-1)$）。
5. 在 §2.2（`论文.md:76` 附近，"三条决定性的实现事实"）追加第四条："Step2 的换出按下次使用最远者优先（`code/schedule_step2.py:172`），因此在给定核内顺序下换出选择近似最优，spill 主要由核内顺序与子图边界决定。"以及第五条："问题 3 的 Cache 命中在 COPY_IN 发射时判定、写入在搬运完成后，因此多核并发首读同一张量全部未命中（`code/multicore_cut_evaluate_problem_3.py:543, 416`）。"
6. 摘要与"模型的优点"（§12.1）中"首次""核心引理"一类措辞改为与 T23.3 第 1 条一致的表述。

### T23.4 相关工作
在 `论文.md` 的"## 二、问题分析"之前新增"## 相关工作"一节，按增强版 §3.1 的四段结构写，每段最后一句写本题与这些工作的区别。

### T23.5 参考文献
在 `论文.md` 的"## 参考文献"下，按增强版附录的编号追加条目 1–14、16–31、32–36（第 15 条是开源代码，放脚注），格式与现有条目一致；对增强版标"待核"的 3 条，先在出版方页面确认会议、卷期、页码再写入，无法确认的写 arXiv 号。

### T23.6 新章节文本
为 T11–T21 中产出结果的每个任务，在 `04_实验章节.md` 对应小节（主结果 §10.2、难例 §10.3、基线 §10.4、P3 §10.5、时间 §10.6、代理 §10.7、消融 §11.1、粒度 §11.2）各加一段，只描述"做了什么 + 占位符形式的结果 + 图号"。增强版 §五"验收总表增补"的每一行对应一段，句式照抄该表"目标表述"列，数字全部换成占位符。

**验收**
```bash
python solution/assemble_paper.py
python solution/fill_paper.py paper/论文_完整.md
python solution/md2docx.py paper/论文_完整.md -o paper/论文.docx
```
通过标准：`fill_paper.py` 退出码 0 且无未替换占位符；`md2docx.py` 不报 `All strings must be XML compatible`；`grep -c "几何平均" paper/论文_完整.md` 的每一处都带"补充指标"或"比值型指标"字样。

---

## T24　收尾：全量重建与复核

```bash
python solution/build_pool.py --jobs 16
python solution/check_pool.py
python solution/make_report.py
python solution/export_plans.py
python solution/verify_final.py --problems 1 2 3 --jobs 16
bash solution/finalize.sh
python solution/digest.py > results/digest_final.txt
```
**最终验收清单**（全部满足才算完成）：
1. `check_pool.py` 打印 `POOL OK`；
2. `verify_final.py` `mismatches=0`；
3. `final.csv` 每个问题每个 N 的算术平均 ≥ T07 结束时的值；
4. `fill_paper.py` 无未替换占位符；
5. `paper/论文.docx` 生成成功；
6. 0.3 回归检查通过；
7. `git status` 中没有 `code/`、`data/`、`docs/` 下的改动（`git diff --stat -- code data docs` 输出为空）。

完成后在 `results/CHANGELOG_checklist_v3.md` 按任务编号记录：是否完成、跳过原因（引用对应的 `*_skipped.txt` 或 gate 文件）、关键数字（从 `summary.json` 复制）。
