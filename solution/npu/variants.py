"""按"标签"确定性重建方案：主候选、基线、消融、粒度扫描、单核。

保底池（build_pool.py）与后续全部分析都通过同一个入口 ``build`` 重建方案，
保证同一标签在任何脚本里得到逐位相同的方案（因而命中同一评估缓存）。

标签（顺序固定，见 ``LABELS``）::

    c0 … c{k-1}        主候选，参数 = candidate_params(problem, N, 'full')[i]
    b_random …         基线算法 ALGORITHMS[name]
    a_full …           消融变体（构造逻辑与原 run_experiments.task_ablation 相同）
    g_<β>              粒度扫描 cap_ls(block_cap=β)
    s1 … s16           仅问题 2/3：T13 优先级采样，参数 = 该配置最优 op 候选 + noise=0.05、
                       seed=k；基础参数与被官方评估的标签存于 *_s_base.json
    sa1 … sa3          仅问题 1：代理驱动模拟退火（T14）得到的方案。退火方案无法由
                       参数重建，所以由 run_portfolio 存成
                       results/plans/<case>_p1_n<N>_sa<i>.json，这里直接读文件
    single             整图一个子图放 0 号核，其余核空
"""

from __future__ import annotations

import json

from . import algorithms, assign, evaluate, partition, paths

BASELINES = ('random', 'topo', 'balance', 'comm')

ABLATIONS = {
    'full': dict(),
    'no_comm': dict(use_affinity=False),
    'no_balance': dict(comm_weight=0.0, local_search=False, _rr=True),
    'no_sync': dict(sync_weight=0.0),
    'no_localsearch': dict(local_search=False),
    'no_cache_aware': dict(use_cache_aware=False),
    'no_level': dict(_no_level=True),
}

SAMPLE_K_MAX = 16          # T13 优先级采样的最大样本数
SAMPLE_NOISE = 0.05

# T16 消融体系：基准 = c2 的参数，逐项覆盖（op_* 仅问题 2/3）
ABLATION2_BASE = dict(block_cap=0.35, init='rr')
_OP = dict(subgraph_mode='op', alpha=0.8, mu=1.0, nu=0.5)
ABLATION2 = {
    'full_c2': dict(),
    'no_comm': dict(use_affinity=False),
    'no_sync': dict(sync_weight=0.0),
    'no_localsearch': dict(local_search=False),
    'no_level': dict(subgraph_mode='block'),
    'no_level_no_comm': dict(subgraph_mode='block', use_affinity=False),
    'max_ops500': dict(max_ops=500),
    'op_full': dict(_OP),
    'op_mu0': dict(_OP, mu=0.0),
    'op_nu0': dict(_OP, nu=0.0),
    'op_alpha1': dict(_OP, alpha=1.0),
    'lvl_alap': dict(level_mode='alap_fill'),
    'lvl_compress': dict(level_mode='alap_compress'),
}
ABLATION2_P23_ONLY = ('op_full', 'op_mu0', 'op_nu0', 'op_alpha1')


def ablation2_params(name: str) -> dict:
    return dict(ABLATION2_BASE, **ABLATION2[name])


GRANULARITY_BETAS = (0.03, 0.06, 0.12, 0.25, 0.5, 1.0, 2.0)


def LABELS(problem: int, num_cores: int) -> list:
    k = len(algorithms.candidate_params(problem, num_cores, 'full'))
    labels = [f'c{i}' for i in range(k)]
    labels += [f'b_{name}' for name in BASELINES]
    labels += [f'a_{name}' for name in ABLATIONS]
    labels += [f'g_{beta}' for beta in GRANULARITY_BETAS]
    if problem == 1:
        labels += ['sa1', 'sa2', 'sa3']
    else:
        labels += [f's{k}' for k in range(1, SAMPLE_K_MAX + 1)]
    labels.append('single')
    return labels


def is_saved_plan_label(label: str) -> bool:
    return label.startswith('sa') and label[2:].isdigit()


def is_sample_label(label: str) -> bool:
    return label.startswith('s') and label[1:].isdigit()


def sample_base_path(case: str, problem: int, num_cores: int):
    """T13：记录采样所用基础参数与被官方评估的样本标签。"""
    return paths.PLAN_DIR / f'{case}_p{problem}_n{num_cores}_s_base.json'


def saved_plan_path(case: str, problem: int, num_cores: int, label: str):
    return paths.PLAN_DIR / f'{case}_p{problem}_n{num_cores}_{label}.json'


def label_params(label: str, problem: int, num_cores: int):
    """标签对应的参数（写入记录的 params 字段）；无参数的标签返回 None。"""
    if label.startswith('c') and label[1:].isdigit():
        return algorithms.candidate_params(problem, num_cores, 'full')[int(label[1:])]
    if label.startswith('a_'):
        return ABLATIONS[label[2:]]
    if label.startswith('g_'):
        return {'block_cap': float(label[2:])}
    return None


def ablation_plan(g, name: str, problem: int, num_cores: int) -> dict:
    ncores = num_cores
    params = dict(ABLATIONS[name])
    rr = params.pop('_rr', False)
    no_level = params.pop('_no_level', False)
    if rr or no_level:
        cfg = paths.official_config()
        bs = partition.make_blocks(
            g, ncores, block_cap=params.get('block_cap', 0.35),
            use_affinity=params.get('use_affinity', True))
        if rr:
            core = assign.round_robin_assign(bs, ncores)
        else:
            core = assign.lpt_assign(bs, ncores)
            state = algorithms.TrafficState(
                bs, core, ncores, cfg,
                sync_penalty=(cfg['task_cross_core_wait_cycles']
                              if problem == 1
                              else cfg['cross_core_copy_delay_cycles']),
                cache_capacity=(cfg['cache_capacity_bytes']
                                if problem == 3 else 0))
            algorithms._local_search(bs, state, ncores, problem == 3)
            core = state.core
        if no_level:
            plan = algorithms._plan_blocks_as_subgraphs(bs, core, ncores)
        else:
            plan = algorithms._plan_from_core_map(g, bs, core, ncores)
    else:
        plan = algorithms.cap_ls(g, ncores, problem, **params)
    return plan


def build(g, label: str, problem: int, num_cores: int, seed: int = 0) -> dict:
    if label.startswith('c') and label[1:].isdigit():
        params = label_params(label, problem, num_cores)
        plan = algorithms.cap_ls(g, num_cores, problem, seed=seed, **params)
    elif label.startswith('b_'):
        plan = algorithms.ALGORITHMS[label[2:]](g, num_cores, problem, seed=seed)
    elif label.startswith('a_'):
        plan = ablation_plan(g, label[2:], problem, num_cores)
    elif label.startswith('g_'):
        plan = algorithms.cap_ls(g, num_cores, problem, block_cap=float(label[2:]))
    elif is_saved_plan_label(label):
        path = saved_plan_path(g.name, problem, num_cores, label)
        if not path.is_file():
            raise FileNotFoundError(f'no saved anneal plan: {path.name}')
        plan = json.loads(path.read_text(encoding='utf-8'))
    elif is_sample_label(label):
        path = sample_base_path(g.name, problem, num_cores)
        if not path.is_file():
            raise FileNotFoundError(f'no sampling base: {path.name}')
        info = json.loads(path.read_text(encoding='utf-8'))
        if label not in info['evaluated']:
            raise FileNotFoundError(f'sample {label} not evaluated')
        plan = algorithms.cap_ls(g, num_cores, problem, seed=int(label[1:]),
                                 **dict(info['base'], noise=SAMPLE_NOISE))
    elif label == 'single':
        plan = algorithms.baseline_singlecore(g, num_cores, problem)
    else:
        raise KeyError(f'unknown variant label: {label}')
    return evaluate.canonical_plan(plan)
