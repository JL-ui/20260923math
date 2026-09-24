"""论文图表自动生成：全部数据来自 results/*.csv，不做任何手工修改。"""

from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt                                # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle  # noqa: E402

from . import paths                                            # noqa: E402

for _f in ('Microsoft YaHei', 'SimHei', 'SimSun', 'DengXian', 'Arial Unicode MS'):
    try:
        matplotlib.font_manager.findfont(_f, fallback_to_default=False)
        plt.rcParams['font.sans-serif'] = [_f, 'DejaVu Sans']
        break
    except Exception:                                          # noqa: BLE001
        continue
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['figure.dpi'] = 150
plt.rcParams['savefig.dpi'] = 200
plt.rcParams['font.size'] = 10
plt.rcParams['axes.grid'] = True
plt.rcParams['grid.alpha'] = 0.3

CORE_COLORS = ['#3b6fb6', '#d1603d', '#4f9d69', '#8e6bbf', '#c9a227']
ALGO_LABEL = {'random': '随机基线', 'topo': '拓扑等分', 'balance': '负载均衡',
              'comm': '通信聚类', 'capls': 'CAP-LS（本文）',
              'single': '单核基准'}


# --------------------------------------------------------------------------
# 数据读取
# --------------------------------------------------------------------------

def read_csv(name) -> list:
    path = Path(name)
    if not path.is_absolute():
        path = paths.RESULTS_DIR / path
    if not path.is_file():
        return []
    with path.open(encoding='utf-8', newline='') as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        for k in ('makespan', 'added_copy_bytes', 'num_cores', 'n_subgraphs',
                  'cache_hit_bytes', 'spill_added_copy_bytes',
                  'partition_added_copy_bytes', 'baseline_makespan'):
            if r.get(k) not in (None, '', 'None'):
                try:
                    r[k] = int(float(r[k]))
                except ValueError:
                    r[k] = None
            else:
                r[k] = None
        for k in ('speedup', 'runtime_s', 'eval_s', 'cache_hit_rate'):
            if r.get(k) not in (None, '', 'None'):
                r[k] = float(r[k])
            else:
                r[k] = None
        r['feasible'] = str(r.get('feasible')).lower() == 'true'
        r['is_best'] = str(r.get('is_best')).lower() == 'true'
    return rows


def best_plan_rows(rows):
    """只取多起点组合选中的方案行（含其在多个问题下的评估视角）。

    N=1 参考点没有候选可选（方案唯一：整图一个子图），因此一并保留。
    """
    sel = [r for r in rows
           if r.get('is_best') or int(r.get('num_cores') or 0) == 1]
    return sel if sel else rows


def best_rows(rows, key=('case', 'problem', 'num_cores'), metric='makespan'):
    best = {}
    for r in rows:
        if not r['feasible'] or r.get(metric) is None:
            continue
        k = tuple(str(r.get(x)) for x in key)
        if k not in best or r[metric] < best[k][metric]:
            best[k] = r
    return best


def geomean(values):
    values = [v for v in values if v and v > 0]
    if not values:
        return float('nan')
    return math.exp(sum(math.log(v) for v in values) / len(values))


def amean(values):
    values = [v for v in values if v and v > 0]
    if not values:
        return float('nan')
    return sum(values) / len(values)


def save(fig, name):
    paths.FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    out = paths.FIGURES_DIR / name
    fig.savefig(out, bbox_inches='tight')
    plt.close(fig)
    print('figure ->', out)
    return out


# --------------------------------------------------------------------------
# 图 1  多核 NPU 架构
# --------------------------------------------------------------------------

def fig_architecture(num_cores=4):
    fig, ax = plt.subplots(figsize=(9, 5.0))
    ax.set_axis_off()
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6.2)
    cfg = paths.official_config()
    for k in range(num_cores):
        x = 0.35 + k * 2.4
        ax.add_patch(FancyBboxPatch((x, 2.0), 2.05, 3.5, boxstyle='round,pad=0.05',
                                    fc='#eef3fb', ec='#3b6fb6', lw=1.4))
        ax.text(x + 1.02, 5.25, f'AI Core {k}', ha='center', fontsize=10,
                color='#22406e', fontweight='bold')
        for i, (name, color) in enumerate([
                ('Cube / PIPE_M', '#3b6fb6'), ('Vector / PIPE_V', '#4f9d69'),
                ('MTE2 (DDR→L1/UB)', '#c9a227'), ('MTE3 (L1/UB→DDR)', '#d1603d')]):
            ax.add_patch(Rectangle((x + 0.12, 4.55 - i * 0.48), 1.8, 0.36,
                                   fc=color, alpha=0.25, ec=color))
            ax.text(x + 1.02, 4.72 - i * 0.48, name, ha='center', va='center',
                    fontsize=7.2)
        ax.add_patch(Rectangle((x + 0.12, 2.45), 0.85, 0.75, fc='#ffffff',
                               ec='#555555'))
        ax.text(x + 0.545, 2.82, 'L1\n{}KB'.format(cfg['L1'] // 1024),
                ha='center', va='center', fontsize=7)
        ax.add_patch(Rectangle((x + 1.07, 2.45), 0.85, 0.75, fc='#ffffff',
                               ec='#555555'))
        ax.text(x + 1.495, 2.82, 'UB\n{}KB'.format(cfg['UB'] // 1024),
                ha='center', va='center', fontsize=7)
        ax.add_patch(FancyArrowPatch((x + 1.02, 2.0), (x + 1.02, 1.35),
                                     arrowstyle='<->', mutation_scale=11,
                                     color='#666666'))
    ax.add_patch(FancyBboxPatch((0.35, 0.72), 9.3, 0.62,
                                boxstyle='round,pad=0.04',
                                fc='#fdf3e7', ec='#c9a227', lw=1.3))
    ax.text(5.0, 1.03, '共享只读 L2 Cache（问题 3）：{} MB，{} B/cycle，'
                       '与 DDR 带宽相互独立'.format(
                           cfg['cache_capacity_bytes'] // (1024 * 1024),
                           cfg['cache_bandwidth_bytes_per_cycle']),
            ha='center', va='center', fontsize=8.5)
    ax.add_patch(FancyBboxPatch((0.35, 0.05), 9.3, 0.58,
                                boxstyle='round,pad=0.04',
                                fc='#eaeaea', ec='#444444', lw=1.3))
    ax.text(5.0, 0.34, '共享 DDR 主存：总带宽 {} B/cycle（所有核心的 COPY_IN/'
                       'COPY_OUT/换入换出公平共享）'.format(cfg['bandwidth']),
            ha='center', va='center', fontsize=8.5)
    return save(fig, 'fig01_architecture.png')


# --------------------------------------------------------------------------
# 图 2 / 图 3  示例 DAG 与切图示意
# --------------------------------------------------------------------------

def _mini_dag_layout(g, members):
    from collections import defaultdict as dd
    by_level = dd(list)
    for v in members:
        by_level[g.level[v]].append(v)
    pos = {}
    for lv in sorted(by_level):
        row = sorted(by_level[lv])
        for i, v in enumerate(row):
            pos[v] = (lv, i - (len(row) - 1) / 2.0)
    return pos


def fig_example_dag(case='case_001', limit=26):
    from . import graphlib
    g = graphlib.load_graph(paths.case_path(case))
    members = []
    seen = set()
    for v in g.topo:
        if len(members) >= limit:
            break
        members.append(v)
        seen.add(v)
    pos = _mini_dag_layout(g, members)
    fig, ax = plt.subplots(figsize=(8.2, 4.0))
    ax.set_axis_off()
    pipe_color = {'PIPE_M': '#3b6fb6', 'PIPE_V': '#4f9d69',
                  'PIPE_MTE2': '#c9a227', 'PIPE_MTE3': '#d1603d'}
    for v in members:
        for w in g.succs[v]:
            if w in pos:
                ax.annotate('', xy=pos[w], xytext=pos[v],
                            arrowprops=dict(arrowstyle='->', color='#999999',
                                            lw=0.8, shrinkA=9, shrinkB=9))
    for v in members:
        x, y = pos[v]
        c = pipe_color.get(g.pipe(v), '#888888')
        ax.scatter([x], [y], s=430, c=c, alpha=0.75, edgecolors='k',
                   linewidths=0.6, zorder=3)
        ax.text(x, y, g.ops[v]['op'][:5], ha='center', va='center',
                fontsize=6.0, color='white', zorder=4, fontweight='bold')
    handles = [plt.Line2D([], [], marker='o', ls='', color=c, label=p)
               for p, c in pipe_color.items()]
    ax.legend(handles=handles, loc='upper center', ncol=4, fontsize=8,
              frameon=False, bbox_to_anchor=(0.5, 1.12))
    ax.set_title('{} 的算子级 DAG 局部（收缩 COPY 节点后，共 {} 个可切分算子）'
                 .format(case, g.n), fontsize=9.5, pad=18)
    return save(fig, 'fig02_example_dag.png')


def fig_partition_sketch():
    """切图 / 分核 / 分层示意（示意图，非实验数据）。"""
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.4))
    titles = ['(a) 原始计算图', '(b) 亲和原子化 + 无环切图',
              '(c) 分核 + 跨核同步层次分层']
    rng = [(0, 0), (1, 0), (1, 1), (2, 0), (2, 1), (3, 0)]
    nodes = {
        0: (0, 1.6), 1: (0, 0.6), 2: (1, 2.1), 3: (1, 1.1), 4: (1, 0.1),
        5: (2, 1.6), 6: (2, 0.6), 7: (3, 1.1),
    }
    edges = [(0, 2), (0, 3), (1, 3), (1, 4), (2, 5), (3, 5), (3, 6), (4, 6),
             (5, 7), (6, 7)]
    groups = {0: 0, 1: 0, 2: 1, 3: 1, 4: 1, 5: 2, 6: 2, 7: 3}
    cores = {0: 0, 1: 1, 2: 0, 3: 1, 4: 1, 5: 0, 6: 1, 7: 0}
    # 层次 r(v) 由定义直接算出，不手工填写
    levels = {}
    for v in sorted(nodes):
        levels[v] = max((levels[a] + (1 if cores[a] != cores[v] else 0)
                         for a, b in edges if b == v), default=0)
    for ax, title, mode in zip(axes, titles, ('plain', 'group', 'core')):
        ax.set_axis_off()
        ax.set_xlim(-0.6, 3.6)
        ax.set_ylim(-0.6, 2.8)
        ax.set_title(title, fontsize=9.5)
        for a, b in edges:
            ax.annotate('', xy=nodes[b], xytext=nodes[a],
                        arrowprops=dict(arrowstyle='->', color='#aaaaaa',
                                        lw=0.9, shrinkA=11, shrinkB=11))
        for v, (x, y) in nodes.items():
            if mode == 'plain':
                c = '#888888'
            elif mode == 'group':
                c = CORE_COLORS[groups[v]]
            else:
                c = CORE_COLORS[cores[v]]
            ax.scatter([x], [y], s=380, c=c, alpha=0.8, edgecolors='k',
                       linewidths=0.6, zorder=3)
            label = str(v) if mode != 'core' else '{}\nr={}'.format(v, levels[v])
            ax.text(x, y, label, ha='center', va='center', fontsize=7,
                    color='white', zorder=4, fontweight='bold')
        if mode == 'group':
            ax.text(1.5, -0.45, '同色 = 同一块（σ 的连续区间；块级商图必为 DAG）',
                    ha='center', fontsize=8)
        elif mode == 'core':
            ax.text(1.5, -0.45,
                    '同色 = 同一核心；r 为跨核同步层次\n'
                    '子图 = (核心, r)：核 0 执行 {0,2}→{5,7}，核 1 执行 {1,4}→{3,6}',
                    ha='center', fontsize=7.5)
        else:
            ax.text(1.5, -0.45, '节点 = 计算算子，边 = 张量依赖',
                    ha='center', fontsize=8)
    return save(fig, 'fig03_partition_sketch.png')


def fig_framework():
    """图 4：P1/P2/P3 统一求解框架。"""
    fig, ax = plt.subplots(figsize=(10.4, 4.6))
    ax.set_axis_off()
    ax.set_xlim(0, 10.4)
    ax.set_ylim(0, 4.6)
    stages = [
        ('输入\n计算图 G\nconfig.txt', '#eeeeee'),
        ('S1 亲和原子化\nθ 扇出阈值\nSCC 合并\nσ 连续区间分块', '#eef3fb'),
        ('S2 核心分配\nLPT 装箱\n负载+通信+同步深度\n移动式局部搜索', '#eaf5ee'),
        ('S3 同步层次分层\nr(v) 计算\n子图=(核,层次)\n规模切分', '#fdf3e7'),
        ('S4 多起点组合\n候选参数网格\n官方评估器择优', '#f7ecf7'),
        ('输出\nnode_to_subgraph\ncore_schedules', '#eeeeee'),
    ]
    w, gap = 1.44, 0.28
    for i, (text, color) in enumerate(stages):
        x = 0.25 + i * (w + gap)
        ax.add_patch(FancyBboxPatch((x, 1.45), w, 1.75,
                                    boxstyle='round,pad=0.06',
                                    fc=color, ec='#555555', lw=1.0))
        ax.text(x + w / 2, 2.32, text, ha='center', va='center', fontsize=7.6)
        if i < len(stages) - 1:
            ax.add_patch(FancyArrowPatch((x + w, 2.32), (x + w + gap, 2.32),
                                         arrowstyle='->', mutation_scale=12,
                                         color='#444444'))
    notes = [
        ('问题 1（场景 A）', '子图=Task；粗粒度子图摊薄边界搬运；\n'
                             '层次数 -> Task 串行级数×1000 cycle'),
        ('问题 2（场景 B）', '核=Task；同核子图片内驻留，边界搬运为零；\n'
                             '层次分层掩盖 500 cycle 跨核同步'),
        ('问题 3（+L2）', '跨核重复读取由只读 Cache 承担；\n'
                          '分配代价中命中字节按 250 B/cycle 折算'),
    ]
    for i, (head, body) in enumerate(notes):
        x = 0.25 + i * 3.45
        ax.add_patch(FancyBboxPatch((x, 0.12), 3.2, 1.0,
                                    boxstyle='round,pad=0.05',
                                    fc='#ffffff', ec=CORE_COLORS[i], lw=1.1))
        ax.text(x + 1.6, 0.92, head, ha='center', fontsize=8.4,
                fontweight='bold', color=CORE_COLORS[i])
        ax.text(x + 1.6, 0.48, body, ha='center', va='center', fontsize=7.2)
    ax.text(5.2, 3.72, '场景自适应：S2 的代价权重与 S3 的子图粒度按问题切换',
            ha='center', fontsize=9, color='#333333')
    return save(fig, 'fig04_framework.png')


# --------------------------------------------------------------------------
# 图 5  平均加速比曲线
# --------------------------------------------------------------------------

def _speedup_table(main_rows, n1_rows):
    """返回 {problem: {ncores: [speedups]}}，N=1 固定为 1.0。"""
    best = best_rows([r for r in main_rows if r.get('is_best') in (None, '', 'True', True)
                      or True])
    table = defaultdict(lambda: defaultdict(list))
    for (case, problem, ncores), r in best.items():
        if r['speedup']:
            table[int(problem)][int(ncores)].append(r['speedup'])
    cases = sorted({c for (c, _, _) in best})
    for p in list(table):
        table[p][1] = [1.0] * len(cases)
    return table, cases


def fig_speedup(main_csv='main.csv', n1_csv='n1.csv'):
    rows = read_csv(main_csv)
    table, cases = _speedup_table(rows, read_csv(n1_csv))
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    for i, problem in enumerate(sorted(table)):
        xs = sorted(table[problem])
        ys = [amean(table[problem][n]) for n in xs]
        ax.plot(xs, ys, marker='o', color=CORE_COLORS[i], lw=1.8,
                label=f'问题 {problem}')
        dy = {0: -15, 1: 6, 2: 15}.get(i, 7)
        for x, y in zip(xs, ys):
            if x == 1:
                continue
            ax.annotate(f'{y:.2f}', (x, y), textcoords='offset points',
                        xytext=(6, dy), ha='left', fontsize=7.5,
                        color=CORE_COLORS[i])
    xs = sorted(set().union(*[set(table[p]) for p in table])) or [1]
    ax.plot(xs, xs, ls='--', color='#999999', lw=1.0, label='理想线性加速')
    ax.set_xlabel('核心数 N')
    ax.set_ylabel('平均加速比（{} 个用例的算术平均）'.format(len(cases)))
    ax.set_xticks(xs)
    ax.legend(fontsize=8.5)
    ax.set_title('CAP-LS 在三个问题上的平均加速比', fontsize=10)
    return save(fig, 'fig05_speedup.png')


def fig_speedup_box(main_csv='main.csv'):
    rows = read_csv(main_csv)
    best = best_rows(rows)
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.6), sharey=True)
    for ax, problem in zip(axes, (1, 2, 3)):
        data, labels = [], []
        for n in (2, 3, 4, 5):
            vals = [r['speedup'] for (c, p, nn), r in best.items()
                    if int(p) == problem and int(nn) == n and r['speedup']]
            if vals:
                data.append(vals)
                labels.append(str(n))
        if data:
            bp = ax.boxplot(data, tick_labels=labels, showfliers=False,
                            patch_artist=True)
            for patch in bp['boxes']:
                patch.set_facecolor('#dce8f7')
        ax.set_title(f'问题 {problem}', fontsize=9.5)
        ax.set_xlabel('核心数 N')
    axes[0].set_ylabel('加速比')
    fig.suptitle('各用例加速比分布（箱线图）', fontsize=10)
    return save(fig, 'fig05b_speedup_box.png')


# --------------------------------------------------------------------------
# 图 6 / 7 / 9  算法对比
# --------------------------------------------------------------------------

def _algo_compare(main_csv, baseline_csv, problem, ncores, metric):
    main = best_rows([r for r in read_csv(main_csv)
                      if int(r['problem']) == problem
                      and int(r['num_cores'] or 0) == ncores])
    base = read_csv(baseline_csv)
    series = defaultdict(dict)
    for r in base:
        if (not r['feasible'] or int(r['problem']) != problem
                or int(r['num_cores'] or 0) != ncores):
            continue
        series[r['algorithm']][r['case']] = r
    series['capls'] = {c: r for (c, p, n), r in main.items()}
    cases = sorted(set().union(*[set(v) for v in series.values()])) if series else []
    return series, cases


def fig_makespan_compare(problem=2, ncores=4, main_csv='main.csv',
                         baseline_csv='baseline.csv'):
    series, cases = _algo_compare(main_csv, baseline_csv, problem, ncores,
                                  'makespan')
    fig, ax = plt.subplots(figsize=(7.0, 4.0))
    names = ['random', 'topo', 'balance', 'comm', 'capls']
    vals, labels = [], []
    for i, name in enumerate(names):
        sp = [series[name][c]['speedup'] for c in cases
              if c in series.get(name, {}) and series[name][c]['speedup']]
        if not sp:
            continue
        vals.append(sp)
        labels.append('{}\n(n={})'.format(ALGO_LABEL[name], len(sp)))
    bp = ax.boxplot(vals, tick_labels=labels, showfliers=False, patch_artist=True)
    for i, patch in enumerate(bp['boxes']):
        patch.set_facecolor(CORE_COLORS[i % len(CORE_COLORS)])
        patch.set_alpha(0.45)
    for i, v in enumerate(vals):
        ax.scatter([i + 1], [amean(v)], marker='D', color='k', s=22, zorder=4)
    ax.axhline(1.0, ls='--', color='#999999', lw=1.0)
    ax.set_ylabel('加速比（相对官方单核基准）')
    ax.set_title(f'问题 {problem}、N={ncores}：各算法加速比对比（◆ 为算术平均）',
                 fontsize=10)
    return save(fig, f'fig06_makespan_compare_p{problem}_n{ncores}.png')


def fig_addedcopy_compare(problem=2, ncores=4, main_csv='main.csv',
                          baseline_csv='baseline.csv'):
    series, cases = _algo_compare(main_csv, baseline_csv, problem, ncores,
                                  'added_copy_bytes')
    fig, ax = plt.subplots(figsize=(7.0, 4.0))
    names = ['random', 'topo', 'balance', 'comm', 'capls']
    vals, labels = [], []
    for name in names:
        v = [series[name][c]['added_copy_bytes'] / 1048576.0 for c in cases
             if c in series.get(name, {})
             and series[name][c]['added_copy_bytes'] is not None]
        if not v:
            continue
        vals.append(v)
        labels.append(ALGO_LABEL[name])
    bp = ax.boxplot(vals, tick_labels=labels, showfliers=False, patch_artist=True)
    for i, patch in enumerate(bp['boxes']):
        patch.set_facecolor(CORE_COLORS[i % len(CORE_COLORS)])
        patch.set_alpha(0.45)
    ax.set_yscale('symlog', linthresh=1.0)
    ax.set_ylabel('总额外数据搬运量 (MB)')
    ax.set_title(f'问题 {problem}、N={ncores}：额外搬运量对比', fontsize=10)
    return save(fig, f'fig07_addedcopy_p{problem}_n{ncores}.png')


def fig_runtime(main_csv='main.csv'):
    rows = [r for r in read_csv(main_csv) if r['feasible'] and r['runtime_s']]
    feats = {f['case']: f for f in json.loads(
        (paths.RESULTS_DIR / 'features.json').read_text(encoding='utf-8'))}
    fig, ax = plt.subplots(figsize=(6.2, 4.0))
    for i, n in enumerate((2, 3, 4, 5)):
        pts = [(feats[r['case']]['n_ops'], r['runtime_s']) for r in rows
               if int(r['num_cores'] or 0) == n and r['case'] in feats]
        if not pts:
            continue
        pts.sort()
        ax.scatter([p[0] for p in pts], [p[1] for p in pts], s=10,
                   color=CORE_COLORS[i], alpha=0.55, label=f'N={n}')
    ax.set_xscale('log')
    ax.set_yscale('log')
    ax.set_xlabel('可切分算子数 |V_op|')
    ax.set_ylabel('算法求解时间 (s)')
    ax.legend(fontsize=8)
    ax.set_title('CAP-LS 单候选求解时间随图规模的变化', fontsize=10)
    return save(fig, 'fig09_runtime.png')


# --------------------------------------------------------------------------
# 图 8  Cache
# --------------------------------------------------------------------------

def fig_cache(main_csv='main.csv', p3_csv='p3_compare.csv'):
    rows = read_csv(p3_csv)
    if not rows:
        rows = [r for r in read_csv(main_csv) if int(r['problem']) == 3]
    fig, axes = plt.subplots(1, 2, figsize=(10.2, 3.9))
    byn = defaultdict(list)
    for r in rows:
        if r['feasible'] and r.get('cache_hit_rate') is not None \
                and int(r.get('eval_problem') or 3) == 3:
            byn[int(r['num_cores'] or 0)].append(r['cache_hit_rate'])
    xs = sorted(byn)
    axes[0].bar([str(x) for x in xs], [sum(byn[x]) / len(byn[x]) for x in xs],
                color='#3b6fb6', alpha=0.75)
    for i, x in enumerate(xs):
        axes[0].text(i, sum(byn[x]) / len(byn[x]), '{:.3f}'.format(
            sum(byn[x]) / len(byn[x])), ha='center', va='bottom', fontsize=8)
    axes[0].set_xlabel('核心数 N')
    axes[0].set_ylabel('Cache 命中率（按字节）')
    axes[0].set_title('只读 L2 平均命中率', fontsize=9.5)

    pairs = defaultdict(dict)
    for r in best_plan_rows(rows):
        if not r['feasible']:
            continue
        pairs[(r['case'], int(r['num_cores'] or 0))][int(r['eval_problem'] or 0)] = r
    byn2 = defaultdict(list)
    for (case, n), d in pairs.items():
        if 2 in d and 3 in d and d[3]['makespan']:
            byn2[n].append(d[2]['makespan'] / d[3]['makespan'])
    xs2 = sorted(byn2)
    if xs2:
        axes[1].plot(xs2, [amean(byn2[x]) for x in xs2], marker='o',
                     color='#d1603d', lw=1.8)
        for x in xs2:
            axes[1].annotate('{:.3f}'.format(amean(byn2[x])),
                             (x, amean(byn2[x])), textcoords='offset points',
                             xytext=(0, 7), ha='center', fontsize=7.5)
    axes[1].axhline(1.0, ls='--', color='#999999', lw=1.0)
    axes[1].set_xlabel('核心数 N')
    axes[1].set_ylabel('只读 Cache 相对无 L2 的加速比')
    axes[1].set_xticks(xs2 or [1])
    axes[1].set_title('相同方案下 L2 带来的 Makespan 收益', fontsize=9.5)
    return save(fig, 'fig08_cache.png')


def fig_p3_curve(p3_csv='p3_compare.csv', main_csv='main.csv'):
    """问题 3 正文图：1–5 核下"无 L2"与"只读 Cache"两种配置的加速比曲线。

    同时给出两种口径：
      (a) 受控对比——同一张切图方案分别在 problem 2 / problem 3 下评估，
          隔离出 L2 的净收益；
      (b) 端到端对比——各自用对应场景优化出的最优方案。
    """
    rows = read_csv(p3_csv)
    pairs = defaultdict(dict)
    for r in best_plan_rows(rows):
        if r['feasible'] and r['speedup']:
            pairs[(r['case'], int(r['num_cores'] or 0))][
                int(r.get('eval_problem') or 0)] = r
    byn = defaultdict(lambda: defaultdict(list))
    for (case, n), d in pairs.items():
        for p in (2, 3):
            if p in d and d[p]['speedup']:
                byn[p][n].append(d[p]['speedup'])
    # 端到端：问题 2 自身最优
    main = best_rows([r for r in read_csv(main_csv) if int(r['problem']) == 2])
    e2e = defaultdict(list)
    for (case, p, n), r in main.items():
        if r['speedup']:
            e2e[int(n)].append(r['speedup'])
    for n in byn[2]:
        e2e.setdefault(n, [])
    e2e[1] = byn[2].get(1, [])

    fig, ax = plt.subplots(figsize=(6.6, 4.3))
    labels = {2: '无 L2（同一方案在 problem 2 下评估）',
              3: '只读 L2 Cache（problem 3）'}
    for i, p in enumerate((2, 3)):
        xs = sorted(byn[p])
        if not xs:
            continue
        ys = [amean(byn[p][x]) for x in xs]
        ax.plot(xs, ys, marker='o' if p == 2 else 's', color=CORE_COLORS[i],
                lw=1.8, label=labels[p])
        for x, y in zip(xs, ys):
            ax.annotate(f'{y:.2f}', (x, y), textcoords='offset points',
                        xytext=(0, 8 if p == 3 else -13), ha='center',
                        fontsize=7.5, color=CORE_COLORS[i])
    xs3 = sorted(x for x in e2e if e2e[x])
    if xs3:
        ax.plot(xs3, [amean(e2e[x]) for x in xs3], marker='^', ls='--',
                color='#777777', lw=1.3, label='无 L2（场景 B 自身最优方案）')
    ax.set_xlabel('核心数 N')
    ax.set_ylabel('平均加速比（相对官方单核基准，算术平均）')
    ax.set_xticks(sorted(set(byn[2]) | set(byn[3])) or [1])
    ax.legend(fontsize=8)
    ax.set_title('问题 3：无 L2 与只读 Cache 两种配置的加速比曲线', fontsize=10)
    return save(fig, 'fig10_p3_curve.png')


# --------------------------------------------------------------------------
# 图 10  消融
# --------------------------------------------------------------------------

ABL_LABEL = {
    'full': '完整 CAP-LS', 'no_comm': '去通信感知切图',
    'no_balance': '去负载均衡', 'no_sync': '去同步深度代价',
    'no_localsearch': '去局部搜索', 'no_cache_aware': '去 L2 感知',
    'no_level': '去同步层次分层',
}


def fig_ablation(abl_csv='ablation.csv'):
    rows = read_csv(abl_csv)
    data = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if r['feasible'] and r['speedup']:
            data[int(r['problem'])][r['variant']].append(r['speedup'])
    problems = sorted(data)
    fig, axes = plt.subplots(1, len(problems), figsize=(4.6 * len(problems), 4.0),
                             sharey=False)
    if len(problems) == 1:
        axes = [axes]
    order = ['full', 'no_comm', 'no_balance', 'no_sync', 'no_localsearch',
             'no_level', 'no_cache_aware']
    for ax, p in zip(axes, problems):
        names = [v for v in order if v in data[p]]
        vals = [amean(data[p][v]) for v in names]
        base = vals[0] if names and names[0] == 'full' else max(vals)
        colors = ['#3b6fb6'] + ['#b0b7c3'] * (len(names) - 1)
        ax.barh(range(len(names))[::-1], vals, color=colors, alpha=0.85)
        for i, (v, name) in enumerate(zip(vals, names)):
            txt = ' {:.2f}'.format(v) if name == 'full' else                 ' {:.2f} ({:+.1%})'.format(v, v / base - 1)
            ax.text(v, len(names) - 1 - i, txt, va='center', fontsize=7.5)
        ax.set_yticks(range(len(names))[::-1])
        ax.set_yticklabels([ABL_LABEL.get(n, n) for n in names], fontsize=8)
        ax.set_xlabel('平均加速比')
        ax.set_title(f'问题 {p}', fontsize=9.5)
        ax.set_xlim(0, max(vals) * 1.55 if vals else 1)
    fig.suptitle('消融实验：各机制对平均加速比的贡献（灰条为移除该机制后的结果）',
                 fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    return save(fig, 'fig11_ablation.png')


# --------------------------------------------------------------------------
# 图 11  特征相关性
# --------------------------------------------------------------------------

def fig_feature_effect(main_csv='main.csv', problem=2, ncores=4):
    best = best_rows([r for r in read_csv(main_csv)
                      if int(r['problem']) == problem
                      and int(r['num_cores'] or 0) == ncores])
    feats = {f['case']: f for f in json.loads(
        (paths.RESULTS_DIR / 'features.json').read_text(encoding='utf-8'))}
    keys = [('largest_component_frac', '最大连通分量占比'),
            ('cp_over_total', '关键路径 / 总计算量'),
            ('compute_over_ddr', '计算量 / DDR 下界（对数）'),
            ('avg_width', 'DAG 平均宽度（对数）')]
    fig, axes = plt.subplots(1, 4, figsize=(13, 3.2))
    for ax, (k, label) in zip(axes, keys):
        xs, ys = [], []
        for (case, p, n), r in best.items():
            f = feats.get(case)
            if not f or r['speedup'] is None:
                continue
            v = f[k]
            if v in (None, float('inf')):
                continue
            xs.append(v)
            ys.append(r['speedup'])
        ax.scatter(xs, ys, s=12, alpha=0.6, color='#3b6fb6')
        if k in ('compute_over_ddr', 'avg_width'):
            ax.set_xscale('log')
        ax.set_xlabel(label, fontsize=8)
        ax.set_ylabel('加速比' if ax is axes[0] else '')
        if len(xs) > 2:
            import numpy as np
            lx = np.log(np.array(xs)) if k in ('compute_over_ddr', 'avg_width') \
                else np.array(xs)
            corr = np.corrcoef(lx, np.array(ys))[0, 1]
            ax.set_title('r = {:.2f}'.format(corr), fontsize=8.5)
    fig.suptitle(f'问题 {problem}、N={ncores}：图特征与加速比的关系', fontsize=10)
    return save(fig, f'fig12_features_p{problem}_n{ncores}.png')


# --------------------------------------------------------------------------
# 图 12  Pareto
# --------------------------------------------------------------------------

def fig_pareto(main_csv='main.csv', baseline_csv='baseline.csv',
               problem=2, ncores=4):
    series, cases = _algo_compare(main_csv, baseline_csv, problem, ncores, 'makespan')
    fig, ax = plt.subplots(figsize=(6.4, 4.4))
    for i, name in enumerate(['random', 'topo', 'balance', 'comm', 'capls']):
        pts = []
        for c in cases:
            r = series.get(name, {}).get(c)
            if not r or not r['feasible'] or r['added_copy_bytes'] is None:
                continue
            if not r['speedup']:
                continue
            pts.append((max(r['added_copy_bytes'], 1) / 1048576.0, r['speedup']))
        if not pts:
            continue
        ax.scatter([p[0] for p in pts], [p[1] for p in pts], s=13,
                   alpha=0.55, color=CORE_COLORS[i % 5], label=ALGO_LABEL[name])
        gx = amean([p[0] for p in pts])
        gy = amean([p[1] for p in pts])
        ax.scatter([gx], [gy], marker='*', s=190, color=CORE_COLORS[i % 5],
                   edgecolors='k', linewidths=0.6, zorder=5)
    ax.set_xscale('log')
    ax.set_xlabel('总额外数据搬运量 (MB，对数)')
    ax.set_ylabel('加速比')
    ax.legend(fontsize=8)
    ax.set_title(f'问题 {problem}、N={ncores}：Makespan–搬运量 Pareto 视图'
                 '（★ 为算术平均）', fontsize=10)
    return save(fig, f'fig13_pareto_p{problem}_n{ncores}.png')


def fig_granularity(gran_csv='granularity.csv'):
    rows = read_csv(gran_csv)
    if not rows:
        return None
    data = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if r['feasible'] and r['speedup']:
            data[int(r['problem'])][r['variant']].append(r['speedup'])
    fig, ax = plt.subplots(figsize=(6.6, 4.0))
    for i, p in enumerate(sorted(data)):
        variants = sorted(data[p], key=lambda s: float(s))
        ys = [amean(data[p][v]) for v in variants]
        ax.plot([float(v) for v in variants], ys, marker='o',
                color=CORE_COLORS[i], label=f'问题 {p}')
    ax.set_xscale('log')
    ax.set_xlabel('切图粒度参数 β（单块计算量上限 = β·W/N）')
    ax.set_ylabel('平均加速比')
    ax.legend(fontsize=8.5)
    ax.set_title('切图粒度对性能的影响', fontsize=10)
    return save(fig, 'fig14_granularity.png')


# --------------------------------------------------------------------------
# 图 15  硬件参数敏感性（研究性实验，非正式配置）
# --------------------------------------------------------------------------

KNOB_LABEL = {
    'bandwidth': 'DDR 总带宽 (B/cycle)',
    'L1': 'L1 容量 (KB)',
    'UB': 'UB 容量 (KB)',
    'cache_capacity_bytes': 'L2 容量 (KB)',
    'cache_bandwidth_bytes_per_cycle': 'L2 带宽 (B/cycle)',
    'cross_core_copy_delay_cycles': '跨核同步延迟 (cycle)',
    'task_cross_core_wait_cycles': '场景 A 跨核等待 (cycle)',
}
KNOB_SCALE = {'L1': 1 / 1024, 'UB': 1 / 1024, 'cache_capacity_bytes': 1 / 1024}


def fig_sensitivity(sens_csv='sensitivity.csv'):
    rows = [r for r in read_csv(sens_csv) if r['feasible'] and r['makespan']]
    if not rows:
        return None
    by = defaultdict(lambda: defaultdict(dict))     # knob -> case -> value -> makespan
    default_value = {}
    for r in rows:
        knob = r['knob']
        val = float(r['value'])
        by[knob][r['case']][val] = r['makespan']
        if str(r.get('is_default')).lower() == 'true':
            default_value[knob] = val
    knobs = [k for k in KNOB_LABEL if k in by]
    ncol = 4
    nrow = (len(knobs) + ncol - 1) // ncol
    fig, axes = plt.subplots(nrow, ncol, figsize=(3.3 * ncol, 3.0 * nrow))
    axes = axes.ravel() if hasattr(axes, 'ravel') else [axes]
    for ax, knob in zip(axes, knobs):
        base = default_value.get(knob)
        xs = sorted({v for case in by[knob].values() for v in case})
        ys = []
        for v in xs:
            ratios = []
            for case, table in by[knob].items():
                if v in table and base in table and table[v]:
                    ratios.append(table[base] / table[v])
            ys.append(geomean(ratios) if ratios else float('nan'))
        scale = KNOB_SCALE.get(knob, 1.0)
        ax.plot([x * scale for x in xs], ys, marker='o', color='#3b6fb6')
        if base is not None:
            ax.axvline(base * scale, ls='--', color='#d1603d', lw=1.0)
        # 含 0 的参数（同步延迟）不能用纯对数轴
        ax.set_xscale('symlog' if min(xs) <= 0 else 'log',
                      **({'linthresh': 100} if min(xs) <= 0 else {}))
        ax.set_xlabel(KNOB_LABEL[knob], fontsize=8)
        ax.set_ylabel('相对默认配置', fontsize=7.5)
        ax.tick_params(labelsize=7)
        for x, y in zip(xs, ys):
            ax.annotate('{:.3f}'.format(y), (x * scale, y),
                        textcoords='offset points', xytext=(0, 6),
                        ha='center', fontsize=6.2, color='#555555')
    for ax in axes[len(knobs):]:
        ax.set_axis_off()
    fig.suptitle('硬件参数敏感性（研究性实验，虚线为题目固定配置）', fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    return save(fig, 'fig15_sensitivity.png')


def fig_subgraph_count(main_csv='main.csv'):
    """子图数量与加速比的关系（切图粒度的经验证据）。"""
    rows = read_csv(main_csv)
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.3), sharey=True)
    for ax, problem in zip(axes, (1, 2, 3)):
        best = best_rows([r for r in rows if int(r['problem']) == problem])
        xs = [r['n_subgraphs'] for r in best.values() if r['n_subgraphs']]
        ys = [r['speedup'] for r in best.values() if r['n_subgraphs'] and r['speedup']]
        ax.scatter(xs, ys, s=10, alpha=0.5, color=CORE_COLORS[problem - 1])
        ax.set_xscale('log')
        ax.set_xlabel('最优方案的子图数 S', fontsize=8.5)
        ax.set_title(f'问题 {problem}', fontsize=9.5)
    axes[0].set_ylabel('加速比')
    fig.suptitle('最优切图粒度在三个场景下的差异', fontsize=10)
    return save(fig, 'fig16_subgraph_count.png')


# --------------------------------------------------------------------------
# 图 17  与理论下界的距离
# --------------------------------------------------------------------------

def lower_bound(feat: dict, n: int) -> float:
    """MK >= max( M/N, V/N, B_DDR/bw, CP )：四条相互独立的下界取最大。"""
    return max(feat['pipe_m_cycles'] / n, feat['pipe_v_cycles'] / n,
               feat['ddr_time_lb'], feat['critical_path_cycles'], 1.0)


def bound_gap(main_csv='main.csv', problem=2):
    feats = {f['case']: f for f in json.loads(
        (paths.RESULTS_DIR / 'features.json').read_text(encoding='utf-8'))}
    best = best_rows([r for r in read_csv(main_csv)
                      if int(r['problem']) == problem])
    out = defaultdict(list)
    for (case, p, n), r in best.items():
        f = feats.get(case)
        if not f or not r['makespan']:
            continue
        out[int(n)].append(r['makespan'] / lower_bound(f, int(n)))
    return out


def fig_lower_bound(main_csv='main.csv'):
    fig, ax = plt.subplots(figsize=(6.4, 4.1))
    for i, problem in enumerate((1, 2, 3)):
        g = bound_gap(main_csv, problem)
        xs = sorted(g)
        if not xs:
            continue
        ax.plot(xs, [geomean(g[x]) for x in xs], marker='o',
                color=CORE_COLORS[i], label=f'问题 {problem}')
    ax.axhline(1.0, ls='--', color='#999999', lw=1.0, label='理论下界')
    ax.set_xlabel('核心数 N')
    ax.set_ylabel('Makespan / 理论下界（几何平均，比值型指标）')
    ax.set_xticks(sorted(bound_gap(main_csv, 2)) or [1])
    ax.legend(fontsize=8.5)
    ax.set_title('CAP-LS 解与理论下界 max(M/N, V/N, B/bw, CP) 的距离',
                 fontsize=10)
    return save(fig, 'fig17_lower_bound.png')
