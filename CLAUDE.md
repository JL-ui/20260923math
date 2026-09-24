# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目性质

这是 2026 年中国研究生数学建模竞赛 A 题（华为）《通用神经网络处理器下的多核调度问题》
的解答工程。仓库分成**两半，边界必须严守**：

* `code/`、`data/`、`docs/`、`README.md`、`通用神经网络处理器下的多核调度问题.docx`
  —— **赛题官方材料，只读，任何情况下不得修改**（尤其是 `data/config.txt`：
  比赛结果必须在该固定配置下产生）。
* `solution/`、`results/`、`figures/`、`paper/`、`SOLUTION.md` —— 本项目自有产出。

## 常用命令

```bash
# 单用例求解：生成官方格式方案 <case>_multicore_res.json
python solution/solve.py data/case_001.json --problem 2 --cores 4 -o out.json
python solution/solve.py data/case_001.json --problem 1 --cores 4 --fast   # 跳过官方评估择优

# 用官方脚本复核（唯一权威的打分方式）
python code/multicore_cut_evaluate_problem_2.py data/case_001.json out.json --config data/config.txt

# 复现全部实验（7 个阶段，16 进程约 12 小时）
bash solution/run_all.sh 16

# 单独跑某个阶段（stage ∈ main|baseline|ablation|n1|p3|granularity|sensitivity）
python solution/run_experiments.py --stage main --jobs 16 --cases case_001 case_005 --cores 4 --problems 2

# 实验跑完后的收尾：图表 → 附录表格 → 正文数字 → 拼装 → Word → 方案导出
bash solution/finalize.sh

# 快速查看全部实验结论（写论文时核对数字用）
PYTHONIOENCODING=utf-8 python solution/digest.py

# 两项独立检验
python solution/check_traffic_model.py            # 搬运量解析模型 vs 官方输出
python solution/validate_model.py --jobs 12       # Makespan 代理模型相关性与选择损失
```

**Windows 终端注意**：Python 脚本输出含中文，直接运行会乱码；
读输出时加 `PYTHONIOENCODING=utf-8`。

## 架构：一条主线

`solve.py` / `run_experiments.py` → `npu.algorithms.cap_ls` → 四个阶段 → 官方评估器。

```
npu/paths.py       路径 + 官方 config.txt 的唯一入口（也是敏感性实验的参数覆盖点）
npu/graphlib.py    读图；把 op–tensor 二部图收缩成"算子级 DAG"；边界搬运量解析模型
npu/partition.py   S1 亲和原子化（张量扇出阈值 θ）+ SCC 合并 + 线性扩展 σ + σ 连续区间分块
npu/assign.py      核心分配启发式（LPT / 轮转 / 连续段）+ 场景 A/B 的解析代价模型
npu/algorithms.py  S2 TrafficState 增量代价 + 移动式局部搜索；cap_ls 主入口；基线算法；候选网格
npu/stratify.py    S3 跨核同步层次 r(v) → 子图 =(核心, 层次) 等价类
npu/cachemodel.py  问题 3 的 L2 复用度 / Cache 价值 / FIFO 命中估计
npu/evaluate.py    官方评估器封装 + 方案哈希级磁盘缓存
npu/experiment.py  单次实验 / 多起点组合 / 记录字段
npu/features.py    五类图特征（规模、计算、通信、缓存压力、结构），带缓存
npu/plots.py       全部论文图表，数据只来自 results/*.csv
```

## 必须知道的四条不变量

改动算法前先理解这四条，否则很容易写出被官方评估器拒绝或性能暴跌的方案。

**1. 算子级依赖必须取自收缩 COPY 后的 DAG，不能只看张量生产/消费关系。**
形如 `op → COPY_OUT → DDR → COPY_IN → op` 的依赖在张量关系上是断开的，
但官方 `derive_multicore_plan` 会把它还原成子图依赖。漏掉这类边会导致自查"无环"
而评估器报 `contracted subgraph graph contains a cycle`。
正确来源：`graphlib.Graph.succs` / `.preds`，块级用 `partition.BlockSet.succ`。

**2. 可行性由构造保证，不要在搜索里反复判环。**
定义跨核同步层次 `r(v) = max over u→v of (r(u) + [core(u) ≠ core(v)])`，
取**子图 = (核心, 层次) 等价类**、按 `(r, core)` 递增编号，则题目全部 9 条硬约束
（子图商图无环、同核顺序合法、场景 A Task 图无环、场景 B 全局执行图无环……）
自动成立。实现见 `stratify.build_subgraphs`。**任何新的子图成形方式都必须保持这个性质。**

**3. 跨核依赖的真实代价远大于配置里的 500/1000 cycle。**
官方 `schedule_step3.issue_step` 对"会申请片上张量的算子"施加**全局申请序**，
只有申请序队首者能发射。因此核内序列前部的一个跨核 `COPY_IN` 会让**整个核心
的四条 Pipe 同时停摆**（实测单次 7.1×10⁵ cycle）。这正是同步层次分层存在的理由：
它把依赖远端数据的算子整体后移，让核心先跑完本地就绪的工作。

**4. 场景差异只有两处，不要重复造轮子。**
问题 1（子图 = Task）与问题 2/3（核心 = Task）共用同一套 `cap_ls`，
差异仅在 (a) `sync_weight`（1000 vs 500）、(b) 问题 3 是否折算 L2 命中、
(c) 子图粒度倾向（问题 1 偏粗：同核子图边界要经 DDR；问题 2/3 同核边界零搬运，
切图在核内只剩排序作用）。

## 数据与缓存

* `results/cache/features/` 图特征、`results/cache/singlecore/` 官方单核基准、
  `results/cache/p{1,2,3}/<case>.json` **方案哈希 → 评估结果**。
  删掉 `results/cache` 即可从零重算；缓存写盘是"读回合并 + 原子替换"，多进程安全。
* 敏感性实验通过 `paths.set_config_override(...)` 改硬件参数，
  评估缓存按覆盖哈希分到独立目录，**与正式配置的结果物理隔离**。正式结果对应空覆盖。
* 官方评估器很慢（中位 0.77 s，最大 1829 s）。任何批量实验都要走
  `evaluate.default_cache().evaluate(...)` 而不是 `evaluate_plan(...)`。

## 论文写作约定

* **论文里的每一个 Makespan / 搬运量 / 命中率都必须来自官方评估脚本**，
  `npu` 里的解析模型只用于搜索内部剪枝。
* 正文数字用 `@@KEY@@` 占位符，由 `solution/fill_paper.py` 从 `results/summary.json` 注入；
  脚本会报出任何未替换的占位符。**不要手工填数字。**
* 装配顺序：`paper/论文.md`（骨架，含 `@@EXPERIMENTS@@` 标记）
  + `paper/04_实验章节.md` + `paper/05_附录.md` → `assemble_paper.py`
  → `paper/论文_完整.md` → `fill_paper.py` → `md2docx.py` → `paper/论文.docx`。
* **用 Bash heredoc 批量改论文里的 LaTeX 时要当心**：非 raw Python 字符串会把
  `\b`（`\beta`）、`\t`（`\times`）、`\r`（`\rho`）、`\a`（`\approx`）
  变成控制字符，进而让 `md2docx.py` 抛 `All strings must be XML compatible`。
  优先用 Edit 工具或 raw 字符串。

## 其他 AI 工具配置

检测到用户级的 Codex（`~/.codex/config.toml`）与 Gemini CLI（`~/.gemini/settings.json`）配置。
如需把其中的 MCP 服务器 / 斜杠命令 / 子代理 / 技能 / 指令导入 Claude Code，
回复 `/import` 让它扫描并列出可导入项，再用 `/import --yes=<digest>`（扫描输出会给出 digest）
应用用户级条目。若当前界面没有 `/import`，在终端运行 `claude import`。
