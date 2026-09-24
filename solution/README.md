# CAP-LS：通用神经网络处理器多核切图与调度求解器

本目录是论文《通用神经网络处理器下的多核切图与调度》的**可复现实现**。
所有对外汇报的 Makespan / 额外搬运量 / Cache 命中率**全部由题目自带的官方
评估脚本**（`../code/multicore_cut_evaluate_problem_{1,2,3}.py`）在
`../data/config.txt` 固定配置下给出，本项目的解析模型只用于搜索内部剪枝。

## 1. 环境

* Python ≥ 3.10（开发于 3.13）
* 依赖：`matplotlib`（仅绘图）、标准库。核心算法**不依赖第三方库**。

无需安装，直接在赛题材料包根目录运行即可。

## 2. 目录

```
solution/
  npu/
    paths.py        路径与官方配置（唯一来源，支持敏感性实验的参数覆盖）
    graphlib.py     计算图解析、COPY 收缩、算子级 DAG、搬运量解析模型
    features.py     图特征提取与缓存
    evaluate.py     官方评估器封装 + 方案哈希级评估缓存
    partition.py    S1 亲和原子化 / SCC 合并 / σ 线性扩展 / 连续区间分块
    assign.py       核心分配、解析代价模型（场景 A 的 Task 级事件模拟）
    stratify.py     S3 跨核同步层次 r(v) 与 (核心,层次) 子图成形
    algorithms.py   基线算法 + 主算法 CAP-LS + 候选参数网格
    experiment.py   单次实验 / 多起点组合 / 记录格式
    plots.py        全部论文图表（数据来自 results/*.csv）
  run_singlecore.py   预计算官方单核基准（加速比分母）
  run_experiments.py  实验总驱动（main/baseline/ablation/n1/p3/granularity/sensitivity）
  make_report.py      汇总 → 附录表格 + 正文数字 + 全部图表
  solve.py            单用例求解：生成官方格式方案 JSON
  export_plans.py     把每个 (用例,问题,核数) 的最优方案导出为官方格式
                       results/final_plans/p<问题>/n<核数>/<case>_multicore_res.json
  digest.py           速查全部实验结论（写论文时核对数字）
  check_traffic_model.py  搬运量解析模型 vs 官方输出的独立检验
  validate_model.py   Makespan 代理模型相关性与候选选择损失的独立检验
  assemble_paper.py   拼装 paper/论文.md + 04/05 章节 → paper/论文_完整.md
  fill_paper.py       用 results/summary.json 填充论文里的 @@KEY@@ 占位符
  md2docx.py          Markdown → Word（paper/论文.docx）
  run_all.sh          一键复现全部实验（7 个阶段）
  finalize.sh          实验跑完后的收尾：图表→表格→正文数字→拼装→Word→方案导出
```

## 3. 最常用的三条命令

```bash
# (1) 为单个用例生成官方格式方案（问题 1/2/3、任意核数）
python solution/solve.py data/case_001.json --problem 2 --cores 4 \
       -o data/case_001_multicore_res.json

# (2) 用官方脚本评估该方案
python code/multicore_cut_evaluate_problem_2.py data/case_001.json \
       data/case_001_multicore_res.json --config data/config.txt

# (3) 一键复现论文全部实验、图表与最终方案
bash solution/run_all.sh 16
bash solution/finalize.sh
```

## 4. 算法一览（与论文章节对应）

| 阶段 | 论文 | 实现 |
|---|---|---|
| S1 亲和原子化 + 无环分块 | §6.3 | `partition.make_blocks` |
| S2 核心分配 + 局部搜索 | §6.3 | `algorithms.TrafficState` + `_local_search` |
| S3 同步层次分层 | §5.5、§6.3 | `stratify.cross_core_levels` / `build_subgraphs` |
| S4 多起点组合 | §6.3 | `algorithms.candidate_params` + `experiment.run_portfolio` |
| 场景 A Task 级时序模型 | §6.1 | `assign.estimate_scene_a` |
| 场景 B Pipe 负载模型 | §7.1 | `assign.estimate_scene_b` |
| L2 收益模型 | §8.1–8.2 | `algorithms.TrafficState`（`cache_capacity` 参数） |

## 5. 缓存与可复现性

* `results/cache/features/*.json` —— 图特征（一次计算，全局复用）
* `results/cache/singlecore/*.json` —— 官方单核基准
* `results/cache/p{1,2,3}/<case>.json` —— **方案哈希 → 评估结果**
  只要方案不变就不会重复调用评估器；候选之间产生相同方案时自动命中。
* `results/plans/*.json` —— 各实验阶段产生的最优方案原始记录（内部格式）
* `results/final_plans/p<问题>/n<核数>/<case>_multicore_res.json` —— 经
  `export_plans.py` 导出的**官方格式最终方案**（交付物，见 `results/final_plans/manifest.csv`）
* `results/*.csv`、`results/summary.json` —— 全部实验记录与汇总，
  字段见 `npu/experiment.py`

删除 `results/cache` 即可从零重算；所有随机性由 `--seed` 控制，默认 0。

## 6. 敏感性实验的隔离

`npu.paths.set_config_override(...)` 只在 `--stage sensitivity` 中使用，
且评估缓存按覆盖参数的哈希分目录存放，**不会污染正式配置下的结果**。
正式结果对应的覆盖为空。
