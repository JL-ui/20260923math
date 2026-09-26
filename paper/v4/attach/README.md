# 多核切图与调度求解程序（CAP-LS）

本目录为论文所用的求解与实验程序。所有 Makespan、额外搬运量与 Cache 命中率均由给定的评估程序
（code/multicore_cut_evaluate_problem_{1,2,3}.py）在 data/config.txt 的固定配置下给出，
程序中的解析模型与代理只用于搜索内部的候选比较。

## 运行环境

- Python 3.10 及以上；依赖见 requirements.txt。
- 把本目录解压到材料包根目录（与 code/、data/ 同级）后直接运行，无需安装。

## 目录

```
solution/
  solve.py              单用例求解：按标准求解流程输出规定格式的方案文件
  run_experiments.py    实验驱动（main / baseline / ablation / n1 / p3 / granularity / sensitivity）
  run_all.sh            按顺序运行全部实验阶段
  run_singlecore.py     计算单核基准（加速比的分母）
  export_plans.py       导出每个（用例，问题，核数）的方案文件
  verify_final.py       用评估程序逐个复核方案文件
  check_traffic_model.py  搬运量解析式与评估程序输出的对照
  validate_model.py     搜索代理的排序能力检验
  npu/                  算法实现
    graphlib.py         读图、COPY 收缩、算子级 DAG、边界搬运量解析式
    partition.py        S1 亲和原子化、强连通分量合并、线性扩展与无环切块
    assign.py           S2 初始分配与场景解析模型
    algorithms.py       S2 局部搜索、候选网格、基线算法
    stratify.py         S3 跨核同步层次与（核心，层次）子图
    listsched.py        单算子子图与容量感知表调度
    p1_anneal.py        问题一的代理驱动模拟退火
    cachemodel.py       问题三的 L2 复用度与命中估计
    evaluate.py         评估程序封装与方案哈希缓存
    experiment.py       单次实验、候选组合与记录格式
方案文件/
  p<问题>/n<核数>/case_XXX_multicore_res.json   1500 个方案文件（3 个问题 × 100 个用例 × 5 个核数）
  manifest.csv          每个方案由评估程序给出的指标
```

## 常用命令

```bash
# 求解单个用例（问题 1/2/3，核数 1～5）
python solution/solve.py data/case_001.json --problem 2 --cores 4 -o out.json

# 用评估程序评估方案
python code/multicore_cut_evaluate_problem_2.py data/case_001.json out.json --config data/config.txt

# 运行全部实验（参数为并行进程数）
bash solution/run_all.sh 16
```

评估结果按方案哈希缓存在 results/cache/，删除该目录即从零重算；随机过程均固定种子。
