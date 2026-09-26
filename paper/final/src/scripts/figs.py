"""论文插图（统一风格）：数据只来自 results/ 与 facts.py 的中间结果，不运行任何实验。

    python paper/final/src/scripts/figs.py
"""
from __future__ import annotations

import csv
import json
import math
import statistics as st
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

ROOT = Path(__file__).resolve().parents[4]
RES = ROOT / 'results'
SRC = Path(__file__).resolve().parents[1]
FIG = SRC / 'figs'
FIG.mkdir(parents=True, exist_ok=True)
DATA = SRC / 'data'

for f in ('/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',):
    if Path(f).exists():
        font_manager.fontManager.addfont(f)
plt.rcParams.update({
    'font.family': ['DejaVu Sans', 'WenQuanYi Zen Hei'],
    'axes.unicode_minus': False,
    'mathtext.fontset': 'dejavusans',
    'font.size': 10,
    'axes.titlesize': 10.5,
    'axes.labelsize': 10,
    'legend.fontsize': 9,
    'xtick.labelsize': 9,
    'ytick.labelsize': 9,
    'axes.spines.top': False,
    'axes.spines.right': False,
    'axes.grid': True,
    'grid.color': '#dddddd',
    'grid.linewidth': 0.6,
    'savefig.dpi': 220,
    'savefig.bbox': 'tight',
})
COL = {1: '#2f6db3', 2: '#d1603d', 3: '#3b9a6b'}
GREY = '#888888'
PN = {1: '问题一（场景 A）', 2: '问题二（场景 B）', 3: '问题三（+ 只读 L2）'}
W1, W2 = 6.3, 3.4   # 版心宽约 16 cm


def read(name):
    with open(RES / name, encoding='utf-8') as fh:
        return list(csv.DictReader(fh))


S = json.loads((RES / 'summary.json').read_text(encoding='utf-8'))
final = read('final.csv')
feat = {r['case']: r for r in json.loads((RES / 'features.json').read_text(encoding='utf-8'))}
single = json.loads((RES / 'singlecore_baseline.json').read_text(encoding='utf-8'))
CASES = sorted(feat)
su = defaultdict(dict)
for r in final:
    su[(int(r['problem']), int(r['num_cores']))][r['case']] = float(r['speedup'])


def save(fig, name):
    fig.savefig(FIG / name)
    plt.close(fig)
    print('saved', name)


# ------------------------------------------------------------------ 框架图
def fig_framework():
    fig, ax = plt.subplots(figsize=(W1, 3.9))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 64)
    ax.axis('off')
    stages = [
        ('S1 通信感知分块', ['扇出阈值 θ 原子化', 'SCC 合并保证无环', 'σ 连续区间成块', '单块上限 β·W/N'], '#e8eef8'),
        ('S2 核心分配', ['LPT/轮转/连续段初解', '解析代价 F 增量评估', '移动式局部搜索'], '#e9f4ec'),
        ('S3 子图成形', ['跨核同步层次 r(v)', '或 ALAP 单调层指派', '(核, 层) 等价类成子图', '问题二/三可用表调度'], '#fbf0e3'),
        ('S4 组合择优', ['14/18 组参数候选', '优先级采样与退火', '官方评估器打分择优'], '#f3eaf6'),
    ]
    xs = [0.5, 26, 51.5, 77]
    for x, (t, lines, c) in zip(xs, stages):
        ax.add_patch(FancyBboxPatch((x, 37), 22.5, 19, boxstyle='round,pad=0.3,rounding_size=1.2',
                                    fc=c, ec='#555555', lw=0.9))
        ax.text(x + 11.25, 53.2, t, ha='center', va='center', fontsize=8.8, fontweight='bold')
        for i, ln in enumerate(lines):
            ax.text(x + 11.25, 49.3 - 3.2 * i, ln, ha='center', va='center', fontsize=7.4)
    for x in (23.3, 48.8, 74.3):
        ax.annotate('', xy=(x + 2.4, 46.5), xytext=(x, 46.5),
                    arrowprops=dict(arrowstyle='-|>', color='#444444', lw=1.0))
    ax.text(0.5, 61, '输入：计算图 G（op–tensor 二部图）与固定配置 config.txt；先收缩 COPY 节点得到算子级 DAG',
            fontsize=7.8, va='center')
    ax.annotate('', xy=(11.75, 56.6), xytext=(11.75, 59.4),
                arrowprops=dict(arrowstyle='-|>', color='#444444', lw=1.0))
    ax.add_patch(FancyBboxPatch((26, 22), 73.5, 8.5, boxstyle='round,pad=0.3,rounding_size=1.2',
                                fc='#eeeeee', ec='#555555', lw=0.9))
    ax.text(62.75, 26.25, '保底池：各问题各核数全部候选 + N−1 方案嵌入 + 跨问题互投 + 单核兜底\n'
            '→ 每个 (用例, 问题, N) 取官方评估 Makespan 最小者为最终方案',
            ha='center', va='center', fontsize=7.8, linespacing=1.5)
    ax.annotate('', xy=(88.25, 30.9), xytext=(88.25, 36.6),
                arrowprops=dict(arrowstyle='-|>', color='#444444', lw=1.0))
    scen = [
        (0.5, COL[1], '问题一：子图即 Task', ['偏粗粒度切分', '同步权重 λ = 1000 cycle']),
        (34, COL[2], '问题二：核即 Task', ['同核边界零搬运', 'λ = 500 cycle，加单算子子图']),
        (67.5, COL[3], '问题三：问题二 + 只读 L2', ['命中字节按 250 B/cycle 折算', '与问题二冠军互投']),
    ]
    for x, c, t1, lines in scen:
        ax.add_patch(FancyBboxPatch((x, 1.5), 32, 13, boxstyle='round,pad=0.3,rounding_size=1.2',
                                    fc='white', ec=c, lw=1.3))
        ax.text(x + 16, 11.2, t1, ha='center', va='center', fontsize=7.8, color=c)
        for i, ln in enumerate(lines):
            ax.text(x + 16, 7.2 - 3.4 * i, ln, ha='center', va='center', fontsize=7.4)
    ax.text(0.5, 17.5, '三个问题共用 S1–S4，差异只在代价权重与候选集合：', fontsize=7.8, va='center')
    save(fig, 'framework.png')


# ------------------------------------------------------------------ 平均加速比
def fig_speedup_main():
    fig, ax = plt.subplots(figsize=(W1 * 0.8, 3.5))
    xs = [1, 2, 3, 4, 5]
    ax.plot(xs, xs, ls='--', color=GREY, lw=1, label='理想线性加速 y = N')
    for p in (1, 2, 3):
        ys = [1.0] + [S[f'problem{p}']['speedup_mean'][str(n)] for n in (2, 3, 4, 5)]
        lab = PN[p] + '：' + ' / '.join(f'{y:.2f}' for y in ys[1:])
        ax.plot(xs, ys, marker='o', ms=5, lw=1.8, color=COL[p], label=lab,
                ls='-' if p != 3 else (0, (4, 1.5)))
    ax.set_xticks(xs)
    ax.set_xlabel('核心数 N')
    ax.set_ylabel('平均加速比（100 个用例算术平均）')
    ax.set_xlim(0.8, 5.2)
    ax.set_ylim(0.8, 5.2)
    ax.legend(loc='upper left', frameon=False, title='图例（冒号后依次为 N = 2, 3, 4, 5 的数值）',
              title_fontsize=8.5, alignment='left')
    save(fig, 'speedup_main.png')


def fig_speedup_panels():
    fig, axes = plt.subplots(1, 3, figsize=(W1, 2.6), sharey=True)
    xs = [1, 2, 3, 4, 5]
    for ax, p in zip(axes, (1, 2, 3)):
        blk = S[f'problem{p}']
        mean = [1.0] + [blk['speedup_mean'][str(n)] for n in (2, 3, 4, 5)]
        lo = [1.0] + [blk['speedup_ci'][str(n)][0] for n in (2, 3, 4, 5)]
        hi = [1.0] + [blk['speedup_ci'][str(n)][1] for n in (2, 3, 4, 5)]
        med = [1.0] + [blk['speedup_median'][str(n)] for n in (2, 3, 4, 5)]
        q1 = [1.0]
        q3 = [1.0]
        for n in (2, 3, 4, 5):
            v = sorted(su[(p, n)].values())
            q1.append(v[24])
            q3.append(v[74])
        ax.fill_between(xs, q1, q3, color=COL[p], alpha=0.12, lw=0, label='四分位区间')
        ax.fill_between(xs, lo, hi, color=COL[p], alpha=0.35, lw=0, label='均值 95% 置信区间')
        ax.plot(xs, mean, marker='o', ms=4, color=COL[p], lw=1.8, label='算术平均')
        ax.plot(xs, med, marker='s', ms=3, color=COL[p], lw=1, ls=':', label='中位数')
        ax.plot(xs, xs, ls='--', color=GREY, lw=0.9, label='y = N')
        ax.set_title(PN[p])
        ax.set_xticks(xs)
        ax.set_xlabel('核心数 N')
    axes[0].set_ylabel('加速比')
    axes[0].set_ylim(0.6, 5.6)
    h, l = axes[2].get_legend_handles_labels()
    fig.legend(h, l, loc='lower center', ncol=5, frameon=False, bbox_to_anchor=(0.5, -0.09))
    fig.tight_layout()
    save(fig, 'speedup_panels.png')


def fig_box():
    fig, axes = plt.subplots(1, 3, figsize=(W1, 2.5), sharey=True)
    for ax, p in zip(axes, (1, 2, 3)):
        data = [list(su[(p, n)].values()) for n in (2, 3, 4, 5)]
        bp = ax.boxplot(data, positions=[2, 3, 4, 5], widths=0.55, patch_artist=True,
                        flierprops=dict(marker='.', ms=3, mec=GREY))
        for b in bp['boxes']:
            b.set(facecolor=COL[p], alpha=0.35, edgecolor=COL[p])
        for m in bp['medians']:
            m.set(color='black')
        ax.plot([2, 3, 4, 5], [st.mean(d) for d in data], 'D', color='black', ms=3.5, label='算术平均')
        ax.plot([1.5, 5.5], [1.5, 5.5], ls='--', color=GREY, lw=0.9, label='y = N')
        ax.set_title(PN[p])
        ax.set_xlabel('核心数 N')
    axes[0].set_ylabel('逐用例加速比')
    axes[0].legend(loc='upper left', frameon=False, fontsize=8)
    fig.tight_layout()
    save(fig, 'speedup_box.png')


# ------------------------------------------------------------------ 结构特征
def fig_features():
    y = [su[(2, 4)][c] for c in CASES]
    items = [
        ('最大连通分量占比 ρ_max', [feat[c]['largest_component_frac'] for c in CASES], False),
        ('关键路径 / 总计算量', [feat[c]['cp_over_total'] for c in CASES], False),
        ('DAG 平均宽度', [feat[c]['avg_width'] for c in CASES], True),
        ('计算量 / DDR 时间下界', [feat[c]['compute_over_ddr'] for c in CASES], True),
    ]
    fig, axes = plt.subplots(1, 4, figsize=(W1, 2.2), sharey=True)
    for ax, (lab, x, lg) in zip(axes, items):
        ax.scatter(x, y, s=9, color=COL[2], alpha=0.75, lw=0)
        if lg:
            ax.set_xscale('log')
        ax.set_xlabel(lab, fontsize=8.5)
    axes[0].set_ylabel('加速比（问题二，N=4）')
    fig.tight_layout()
    save(fig, 'features.png')


# ------------------------------------------------------------------ 基线
def fig_baselines():
    algs = [('random', 'B1 随机（官方 stub）', '#9e9e9e', 'x'), ('topo', 'B2 拓扑等分', '#b58b5a', 'v'),
            ('balance', 'B3 负载均衡', '#8a6fb0', '^'), ('comm', 'B4 通信聚类', '#5c9fbf', 's')]
    fig, axes = plt.subplots(1, 3, figsize=(W1, 2.7), sharey=True)
    xs = [1, 2, 3, 4, 5]
    for ax, p in zip(axes, (1, 2, 3)):
        for a, lab, c, m in algs:
            ys = [1.0] + [S['baseline_speedup'][f'p{p}_n{n}'][a] for n in (2, 3, 4, 5)]
            ax.plot(xs, ys, marker=m, ms=4, color=c, lw=1.2, label=lab)
        ys = [1.0] + [S['baseline_speedup'][f'p{p}_n{n}']['capls'] for n in (2, 3, 4, 5)]
        ax.plot(xs, ys, marker='o', ms=4.5, color=COL[p], lw=2, label='CAP-LS（本文）')
        ax.set_title(PN[p])
        ax.set_xticks(xs)
        ax.set_xlabel('核心数 N')
    axes[0].set_ylabel('平均加速比')
    h, l = axes[0].get_legend_handles_labels()
    from matplotlib.lines import Line2D
    h[-1] = Line2D([], [], color='black', marker='o', ms=4.5, lw=2)
    fig.legend(h, l, loc='lower center', ncol=5, frameon=False, bbox_to_anchor=(0.5, -0.1), fontsize=8.5)
    fig.tight_layout()
    save(fig, 'baselines.png')


def fig_traffic():
    fig, ax = plt.subplots(figsize=(W1, 2.6))
    labels, part, spill = [], [], []
    for p in (1, 2, 3):
        for n in (2, 3, 4, 5):
            labels.append(f'P{p}\nN={n}')
            part.append(S[f'problem{p}']['partition_added_total'][str(n)] / 1e9)
            spill.append(S[f'problem{p}']['spill_added_total'][str(n)] / 1e9)
    x = list(range(len(labels)))
    ax.bar(x, part, color='#5c8fc7', label='切分边界引入的搬运')
    ax.bar(x, spill, bottom=part, color='#e08a5b', label='核内换入换出（spill）')
    sc = sum(single[c]['spill_added_copy_bytes'] for c in CASES) / 1e9
    ax.axhline(sc, ls='--', color='black', lw=1)
    ax.text(7.5, sc + 0.04, f'单核基准自身的换入换出总量 {sc:.2f} GB', ha='center', fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=7.5)
    ax.set_ylabel('100 个用例合计 (GB)')
    ax.legend(frameon=False, loc='upper right', bbox_to_anchor=(1, 1.04))
    ax.set_ylim(0, 1.95)
    save(fig, 'traffic.png')


# ------------------------------------------------------------------ 问题三
def fig_l2():
    cmp_ = json.loads((DATA / 'p3_compare_final.json').read_text(encoding='utf-8'))
    n1 = read('n1.csv')
    n1mk = {(r['problem'], r['case']): int(r['makespan']) for r in n1}
    xs = [1, 2, 3, 4, 5]
    nol2, l2 = [], []
    for n in xs:
        if n == 1:
            nol2.append(st.mean(single[c]['makespan'] / n1mk[('2', c)] for c in CASES))
            l2.append(st.mean(single[c]['makespan'] / n1mk[('3', c)] for c in CASES))
        else:
            nol2.append(S['problem2']['speedup_mean'][str(n)])
            l2.append(S['problem3']['speedup_mean'][str(n)])
    fig, axes = plt.subplots(1, 2, figsize=(W1, 2.7))
    ax = axes[0]
    ax.plot(xs, nol2, marker='s', color=COL[2], lw=1.6,
            label='无 L2：' + ' / '.join(f'{a:.2f}' for a in nol2))
    ax.plot(xs, l2, marker='o', color=COL[3], lw=1.6, ls=(0, (4, 1.5)),
            label='只读 L2：' + ' / '.join(f'{b:.2f}' for b in l2))
    ax.plot(xs, xs, ls='--', color=GREY, lw=0.9, label='y = N')
    ax.set_xticks(xs)
    ax.set_xlabel('核心数 N')
    ax.set_ylabel('相对单核基准的平均加速比')
    ax.legend(frameon=False, loc='lower right', fontsize=7.3, title='N = 1…5', title_fontsize=7.3, alignment='left')
    ax.set_title('(a) 两种配置的加速比曲线')
    ax = axes[1]
    g_final = [st.mean(cmp_[str(n)]['gain']) for n in xs]
    g_same = [S['l2_gain'][str(n)] for n in xs]
    hit = [st.mean(cmp_[str(n)]['hit']) for n in xs]
    ax.plot(xs, g_final, marker='o', color=COL[3], lw=1.6, label='Cache 加速比（各自最终方案）')
    ax.plot(xs, g_same, marker='^', color='#1f5d3f', lw=1.2, ls='--', label='Cache 加速比（P3 阶段同一方案）')
    ax.set_ylabel('Cache 加速比 MK(无L2)/MK(L2)')
    ax.set_xticks(xs)
    ax.set_xlabel('核心数 N')
    ax2 = ax.twinx()
    ax2.bar(xs, [100 * h for h in hit], width=0.4, color=COL[3], alpha=0.18, label='按字节命中率')
    ax2.set_ylabel('按字节命中率 (%)')
    ax2.grid(False)
    ax2.set_ylim(0, 60)
    ax.set_zorder(ax2.get_zorder() + 1)
    ax.patch.set_visible(False)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2_ = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2_, frameon=False, loc='upper left', fontsize=7.8)
    ax.set_ylim(0.99, 1.075)
    ax.set_title('(b) Cache 加速比与命中率')
    fig.tight_layout()
    save(fig, 'l2_compare.png')


def fig_l2_sources():
    ls = json.loads((RES / 'l2_sources.json').read_text(encoding='utf-8'))['by_n']
    ns = ['2', '3', '4', '5']
    parts = [('hit_input_reuse', '命中：图输入多核复读', '#3b9a6b'),
             ('hit_cross_core_mid', '命中：跨核中间张量', '#8fd1a8'),
             ('miss_first_miss', '未命中：首次读入', '#9e9e9e'),
             ('miss_concurrent_first_read', '未命中：并发首读', '#e0a458'),
             ('miss_fifo_evicted', '未命中：FIFO 淘汰后再读', '#c9573b')]
    fig, ax = plt.subplots(figsize=(W1 * 0.8, 2.6))
    bottom = [0.0] * len(ns)
    for k, lab, c in parts:
        v = [ls[n][k] / 1e6 for n in ns]
        ax.bar(ns, v, bottom=bottom, color=c, label=lab, width=0.55)
        bottom = [b + x for b, x in zip(bottom, v)]
    ax.set_xlabel('核心数 N')
    ax.set_ylabel('100 个用例合计 (MB)')
    ax.legend(frameon=False, fontsize=7.8, loc='center left', bbox_to_anchor=(1.0, 0.5))
    save(fig, 'l2_sources.png')


def fig_p2p3():
    x = [su[(2, 4)][c] for c in CASES]
    y = [su[(3, 4)][c] for c in CASES]
    fig, ax = plt.subplots(figsize=(3.2, 3.0))
    ax.scatter(x, y, s=10, color=COL[3], alpha=0.8, lw=0)
    ax.plot([1, 6], [1, 6], ls='--', color=GREY, lw=0.9)
    ax.set_xlabel('问题二冠军加速比（N=4）')
    ax.set_ylabel('问题三冠军加速比（N=4）')
    save(fig, 'p2p3.png')


# ------------------------------------------------------------------ 消融 / 粒度 / 敏感性
def fig_ablation():
    names = [('no_level', '去同步层次分层'), ('no_comm', '去通信感知分块'),
             ('no_level_no_comm', '同时去分层与通信感知'), ('no_sync', '去同步深度代价'),
             ('no_localsearch', '去局部搜索'), ('max_ops500', '子图算子数上限 500'),
             ('lvl_alap', 'ALAP 层指派'), ('op_full', '单算子子图 + 表调度')]
    fig, ax = plt.subplots(figsize=(W1, 3.0))
    h = 0.26
    for j, p in enumerate((1, 2, 3)):
        d = S['ablation2'][f'problem{p}']
        ys, xs = [], []
        for i, (k, _) in enumerate(names):
            if k in d:
                ys.append(i + (j - 1) * h)
                xs.append(100 * d[k]['paired']['rel'])
        ax.barh(ys, xs, height=h, color=COL[p], label=PN[p])
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels([n for _, n in names])
    ax.invert_yaxis()
    ax.axvline(0, color='black', lw=0.8)
    ax.set_xlabel('相对基准配置 c2 的平均加速比变化 (%)')
    ax.legend(frameon=False, loc='lower left')
    save(fig, 'ablation.png')


def fig_granularity():
    gr = read('granularity.csv')
    betas = ['0.03', '0.06', '0.12', '0.25', '0.5', '1.0', '2.0']
    fig, ax = plt.subplots(figsize=(W1 * 0.62, 2.6))
    for p in (1, 2, 3):
        ys = [st.mean(float(r['speedup']) for r in gr if int(r['problem']) == p and r['variant'] == b) for b in betas]
        ax.plot([float(b) for b in betas], ys, marker='o', ms=4, color=COL[p], label=PN[p])
    ax.axvline(0.35, ls=':', color=GREY)
    ax.text(0.37, 3.0, '默认 β = 0.35', fontsize=8, color=GREY, va='top')
    ax.set_xscale('log')
    ax.set_xlabel('粒度参数 β（单块计算量上限 = β·W/N）')
    ax.set_ylabel('29 个用例平均加速比（N=4）')
    ax.legend(frameon=False, fontsize=8, loc='lower right')
    save(fig, 'granularity.png')


def fig_sensitivity():
    sens = json.loads((DATA / 'sens_table.json').read_text(encoding='utf-8'))
    order = [('bandwidth', 'DDR 带宽 (B/cycle)', 60), ('L1', 'L1 容量 (KB)', 524288), ('UB', 'UB 容量 (KB)', 131072),
             ('cache_capacity_bytes', 'L2 容量 (KB)', 1048576), ('cache_bandwidth_bytes_per_cycle', 'L2 带宽 (B/cycle)', 250),
             ('cross_core_copy_delay_cycles', 'B 同步延迟 (cycle)', 500),
             ('task_cross_core_wait_cycles', 'A 跨核等待 (cycle)', 1000)]
    fig, axes = plt.subplots(2, 4, figsize=(W1, 3.6))
    for ax, (k, lab, dflt) in zip(axes.flat, order):
        vals = sens[k]
        xs = [float(v) for v, _ in vals]
        ys = [m for _, m in vals]
        scale = 1024 if 'KB' in lab else 1
        xs_ = [x / scale if x else x for x in xs]
        ax.plot(range(len(xs_)), ys, marker='o', ms=3.5, color='#2f6db3')
        ax.set_xticks(range(len(xs_)))
        ax.set_xticklabels([f'{x:g}' for x in xs_], fontsize=7, rotation=30)
        di = xs.index(float(dflt))
        ax.axvline(di, ls=':', color=COL[2], lw=1)
        ax.set_title(lab, fontsize=8.5)
        ax.tick_params(axis='y', labelsize=7)
    axes.flat[-1].axis('off')
    axes.flat[-1].text(0.02, 0.5, '纵轴：Makespan 相对默认配置的倍数\n（几何平均，>1 表示更快）\n虚线：赛题固定配置', fontsize=8, va='center')
    fig.tight_layout()
    save(fig, 'sensitivity.png')


# ------------------------------------------------------------------ 代理与组合
def fig_proxy():
    leg = json.loads((RES / 'model_validation_summary_legacy.json').read_text(encoding='utf-8'))
    sim = json.loads((RES / 'model_validation_summary_sim.json').read_text(encoding='utf-8'))
    fig, axes = plt.subplots(1, 2, figsize=(W1, 2.4))
    x = [0, 1, 2]
    w = 0.36
    ax = axes[0]
    ax.bar([i - w / 2 for i in x], [leg[f'problem{p}']['spearman_median'] for p in (1, 2, 3)], w, color='#9e9e9e', label='解析代理 F')
    ax.bar([i + w / 2 for i in x], [sim[f'problem{p}']['spearman_median'] for p in (1, 2, 3)], w, color='#2f6db3', label='事件模拟代理')
    ax.set_xticks(x)
    ax.set_xticklabels(['问题一', '问题二', '问题三'])
    ax.set_ylabel('用例内 Spearman 中位数')
    ax.set_ylim(0, 1.18)
    ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.legend(frameon=False, fontsize=8, ncol=2, loc='upper center')
    ax.set_title('(a) 排序一致性')
    ax = axes[1]
    for j, (lab, key) in enumerate((('Recall@1', 'recall1'), ('Recall@3', 'recall3'), ('Recall@5', 'recall5'))):
        ax.bar(j - w / 2, leg['problem2'][key], w, color='#9e9e9e')
        ax.bar(j + w / 2, sim['problem2'][key], w, color='#2f6db3')
    ax.set_xticks([0, 1, 2])
    ax.set_xticklabels(['Recall@1', 'Recall@3', 'Recall@5'])
    ax.set_ylim(0, 1)
    ax.set_ylabel('真实最优落入代理前 K 名的比例')
    ax.set_title('(b) 问题二的 Top-K 召回')
    fig.tight_layout()
    save(fig, 'proxy.png')


def fig_greedy():
    pa = json.loads((RES / 'portfolio_analysis.json').read_text(encoding='utf-8'))
    fig, ax = plt.subplots(figsize=(W1 * 0.62, 2.6))
    for p in (1, 2, 3):
        g = pa['greedy'][f'P{p}']
        ax.plot([r['k'] for r in g], [r['amean'] for r in g], marker='.', color=COL[p], label=PN[p])
        ax.axhline(pa['proxy_selection'][f'P{p}']['proxy_only_amean'], ls=':', color=COL[p], lw=1)
    from matplotlib.lines import Line2D
    ax.set_xlabel('已选候选数 k')
    ax.set_ylabel('N=4 平均加速比')
    h, l = ax.get_legend_handles_labels()
    h.append(Line2D([], [], ls=':', color='black', lw=1))
    l.append('点线：只按代理挑 1 个')
    ax.legend(h, l, frameon=False, fontsize=8, loc='lower right')
    save(fig, 'greedy.png')


def fig_bounds():
    rows = read('bounds_cdf.csv')
    fig, ax = plt.subplots(figsize=(W1 * 0.62, 2.6))
    for p in (1, 2, 3):
        v = sorted(float(r['mk_over_lb']) for r in rows if r['problem'] == str(p) and r['num_cores'] == '4')
        ax.step(v, [(i + 1) / len(v) for i in range(len(v))], where='post', color=COL[p], label=PN[p])
    ax.set_xlabel('Makespan / 理论下界（N=4）')
    ax.set_ylabel('累计比例')
    ax.legend(frameon=False, fontsize=8, loc='lower right')
    save(fig, 'bounds.png')


def fig_runtime():
    main = read('main.csv')
    tot = defaultdict(float)
    sa = defaultdict(float)
    for r in main:
        if r['variant'] == '_best':
            continue
        k = (int(r['problem']), r['case'], r['num_cores'])
        tot[k] += float(r['runtime_s'] or 0) + float(r['eval_s'] or 0)
        prm = json.loads(r['params'] or '{}') if r.get('params') else {}
        if 'anneal_seconds' in prm:
            sa[k] = max(sa[k], prm['anneal_seconds'])
    fig, axes = plt.subplots(1, 2, figsize=(W1, 2.6))
    ax = axes[0]
    for p in (1, 2, 3):
        v = sorted(tot[k] + sa[k] for k in tot if k[0] == p)
        ax.step(v, [(i + 1) / len(v) for i in range(len(v))], where='post', color=COL[p], label=PN[p])
    for t in (300, 600):
        ax.axvline(t, ls=':', color=GREY)
    ax.text(300, 0.05, ' 5 min', fontsize=7.5, color=GREY)
    ax.text(600, 0.16, ' 10 min', fontsize=7.5, color=GREY)
    ax.set_xscale('log')
    ax.set_xlabel('单个 (用例, N) 端到端耗时 (s)')
    ax.set_ylabel('累计比例')
    ax.legend(frameon=False, fontsize=7.5, loc='upper left')
    ax.set_title('(a) 含官方评估的端到端耗时')
    ax = axes[1]
    xs, ys = [], []
    for r in main:
        if r['variant'].startswith('c') and r['variant'][1:].isdigit():
            n = feat[r['case']]['n_ops']
            t = float(r['runtime_s'] or 0)
            if t > 0:
                xs.append(n)
                ys.append(t)
    ax.scatter(xs, ys, s=2, alpha=0.25, color='#2f6db3', lw=0)
    ax.set_xscale('log')
    ax.set_yscale('log')
    ax.set_xlabel('可切分算子数 |V_op|')
    ax.set_ylabel('单候选算法时间 (s)')
    ax.set_title('(b) 单候选 S1–S3 时间')
    fig.tight_layout()
    save(fig, 'runtime.png')


def fig_speedup_single(p):
    fig, ax = plt.subplots(figsize=(W1 * 0.62, 2.9))
    xs = [1, 2, 3, 4, 5]
    blk = S[f'problem{p}']
    mean = [1.0] + [blk['speedup_mean'][str(n)] for n in (2, 3, 4, 5)]
    lo = [1.0] + [blk['speedup_ci'][str(n)][0] for n in (2, 3, 4, 5)]
    hi = [1.0] + [blk['speedup_ci'][str(n)][1] for n in (2, 3, 4, 5)]
    med = [1.0] + [blk['speedup_median'][str(n)] for n in (2, 3, 4, 5)]
    ax.plot(xs, xs, ls='--', color=GREY, lw=0.9, label='理想线性加速 y = N')
    ax.fill_between(xs, lo, hi, color=COL[p], alpha=0.25, lw=0, label='算术平均的 95% 置信区间')
    ax.plot(xs, med, marker='s', ms=3, color=COL[p], lw=1, ls=':', label='中位数')
    ax.plot(xs, mean, marker='o', ms=4.5, color=COL[p], lw=2, label='算术平均（赛题口径）')
    for x, y in zip(xs, mean):
        ax.text(x + 0.06, y - 0.12, f'{y:.2f}', fontsize=8, color=COL[p], va='top')
    ax.set_xticks(xs)
    ax.set_xlim(0.8, 5.4)
    ax.set_ylim(0.7, 5.3)
    ax.set_xlabel('核心数 N')
    ax.set_ylabel('平均加速比')
    ax.legend(frameon=False, fontsize=7.8, loc='upper left')
    save(fig, f'speedup_p{p}.png')


if __name__ == '__main__':
    fig_framework()
    fig_speedup_main()
    fig_speedup_panels()
    for _p in (1, 2, 3):
        fig_speedup_single(_p)
    fig_box()
    fig_features()
    fig_baselines()
    fig_traffic()
    fig_l2()
    fig_l2_sources()
    fig_p2p3()
    fig_ablation()
    fig_granularity()
    fig_sensitivity()
    fig_proxy()
    fig_greedy()
    fig_bounds()
    fig_runtime()
