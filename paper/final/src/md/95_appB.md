# 附录 B　程序说明与复现步骤

## B.1　运行环境

程序为纯 Python 实现，在赛题材料包根目录下运行，不需要安装。要求 Python 3.10 及以上；依赖见仓库根目录的 `requirements.txt`（numpy、scipy、matplotlib、python-docx），其中 CAP-LS 的求解部分只用标准库，scipy 只用于统计检验，matplotlib 与 python-docx 只用于出图和生成 Word。官方评估脚本 `code/` 与数据 `data/` 保持赛题原样，`data/config.txt` 未做任何修改。

## B.2　目录结构

Table: 表 B-1　程序与数据的目录结构

| 路径 | 内容 |
|:--|:--|
| `code/`、`data/` | 赛题提供的评估程序、示例生成器、100 个用例与固定配置（只读） |
| `solution/solve.py` | 单用例求解入口，输出官方格式方案 |
| `solution/npu/` | 算法实现：`graphlib`（读图、COPY 收缩、搬运量模型）、`partition`（S1）、`assign` 与 `algorithms`（S2、候选网格、基线）、`stratify` 与 `levels`（S3、单调层指派）、`listsched`（容量感知表调度）、`p1_anneal`（问题一退火）、`simproxy`（事件模拟代理）、`evaluate`（官方评估封装与哈希缓存） |
| `solution/run_experiments.py` | 实验驱动，阶段包括 main、baseline、ablation、ablation2、n1、p3、granularity、sensitivity |
| `solution/build_pool.py`、`check_pool.py` | 保底池汇总与检查，输出 `results/final.csv`、`results/pool.csv` |
| `solution/export_plans.py`、`verify_final.py` | 导出官方格式最终方案；用官方命令行脚本逐个复核 |
| `results/` | 全部实验记录（csv、json）、评估缓存与最终方案 |
| `paper/final/src/` | 本文的数字提取、作图、附录生成与排版脚本 |

## B.3　输入与输出格式

输入为赛题附录 B.3 格式的计算图 `data/<case>.json`。输出严格按赛题附录 B.5：文件名为 `<case>_multicore_res.json`，顶层只有两个字段。

* `node_to_subgraph`：键为全部非 `COPY_IN`/`COPY_OUT` 操作 id 的十进制字符串，值为非负整数子图编号；
* `core_schedules`：二维整数数组，外层下标为核心 id，内层按执行顺序列出该核的子图编号，可以为空。

CAP-LS 生成的子图编号按 (层, 核) 递增分配，每个核的内层数组就是其子图编号的升序，这一性质保证了第 5.6 节的可行性。以赛题附录 B.7 的最小计算图为例，两核方案的输出为：

```
{"node_to_subgraph": {"11": 0},
 "core_schedules": [[0], []]}
```

## B.4　单用例求解与官方评估

```
# 生成问题 2、4 核的方案（候选网格逐个交官方评估器择优）
python solution/solve.py data/case_001.json --problem 2 --cores 4 -o out.json

# 只跑默认配置、不调用评估器（最快）
python solution/solve.py data/case_001.json --problem 1 --cores 4 --fast -o out.json

# 用官方脚本评估（问题 1/2/3 分别换成对应脚本）
python code/multicore_cut_evaluate_problem_2.py data/case_001.json out.json --config data/config.txt
```

`solve.py` 只包含候选网格（第 6.3 节表 6-1），不含退火、采样和保底池，因此其结果可能低于正文报告的最终方案（第 10.2 节）。所有网格候选都失败时，它退回整图单核方案，保证总有可行输出。

## B.5　复现全部实验

以下命令在材料包根目录执行，`16` 为并行进程数。评估结果按方案哈希缓存在 `results/cache/p{1,2,3}/`，删除该目录即从零重算。

```
# 1. 单核基准、N=1 参考点、主实验（含问题一退火与问题二/三采样）、问题三对照、
#    基线、消融、粒度与硬件敏感性
bash solution/run_all.sh 16
python solution/run_experiments.py --stage ablation2 --jobs 16

# 2. 保底池汇总与检查（输出 results/final.csv、results/pool.csv）
python solution/build_pool.py --jobs 16
python solution/check_pool.py

# 3. 导出官方格式最终方案并用官方命令行脚本复核
python solution/export_plans.py
python solution/verify_final.py --problems 1 2 3 --jobs 16

# 4. 分析与检验
python solution/check_traffic_model.py
python solution/validate_model.py --all --proxy legacy --jobs 16
python solution/validate_model.py --all --proxy sim --jobs 16
python solution/bounds.py --jobs 16 --skip-empirical
python solution/l2_sources.py --jobs 16
python solution/portfolio_analysis.py --jobs 16
python solution/cv_select.py
python solution/check_op_mode.py
python solution/p1_anneal_report.py
python solution/sampling_report.py
```

随机过程全部固定种子（主算法 0，问题一退火 20260924），同一方案的评估结果由缓存保证一致，因此重复运行得到相同的 `final.csv`。硬件敏感性实验通过参数覆盖接口修改配置，其评估缓存按覆盖参数的哈希分目录存放，不影响正式结果。

## B.6　最终方案文件与复核

最终方案共 {{N_FINAL_ROWS}} 个，位于 `results/final_plans/p<问题>/n<核数>/<case>_multicore_res.json`，清单与官方指标见同目录的 `manifest.csv`。`verify_final.py` 对这些方案以及 $N=1$ 的整图方案（共 {{VERIFY_N}} 个）逐个调用官方命令行脚本，比较 Makespan、总额外搬运量与命中率，结果写入 `results/verify_final.csv`，不一致数为 {{VERIFY_MISMATCH}}。复核任意一个方案：

```
python code/multicore_cut_evaluate_problem_3.py data/case_044.json \
    results/final_plans/p3/n5/case_044_multicore_res.json --config data/config.txt
```

## B.7　本文数字与图表的生成

正文和附录中的实验数字不手工填写。`paper/final/src/scripts/facts.py` 从 `results/` 中的 csv 与 json 提取全部数字，写入 `facts.json`，每一项都记录来源文件与字段（即随论文提交的《数字溯源表》）；`figs.py` 只读取 `results/` 作图；`appA.py` 生成附录 A；`build.py` 把各章 Markdown 中的占位符替换为 `facts.json` 的数值后排版为 Word，任何未替换的占位符都会使构建失败。
