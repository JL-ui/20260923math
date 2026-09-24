"""计算图特征提取与缓存。

特征分五类：规模、计算、通信、缓存压力、结构。所有特征只依赖原始计算图，
与切图方案无关，因此一次计算、全局复用（缓存到 ``results/cache/features``）。
"""

from __future__ import annotations

import json
import math
from collections import defaultdict

from . import graphlib, paths


def _weighted_critical_path(g: graphlib.Graph) -> int:
    """算子级 DAG 上以 cycles 为点权的最长路径（纯计算关键路径）。"""
    best = {}
    longest = 0
    for v in g.topo:
        cur = g.cycles(v) + max((best[p] for p in g.preds[v]), default=0)
        best[v] = cur
        if cur > longest:
            longest = cur
    return longest


def _component_stats(g: graphlib.Graph):
    """弱连通分量：个数、最大分量占比、各分量的计算量。"""
    parent = {v: v for v in g.nodes}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for v in g.nodes:
        for w in g.succs[v]:
            a, b = find(v), find(w)
            if a != b:
                parent[a] = b
    groups = defaultdict(list)
    for v in g.nodes:
        groups[find(v)].append(v)
    sizes = sorted((len(m) for m in groups.values()), reverse=True)
    work = sorted((sum(g.cycles(v) for v in m) for m in groups.values()),
                  reverse=True)
    return len(sizes), sizes, work


def extract(g: graphlib.Graph) -> dict:
    cfg = paths.official_config()
    bw = cfg['bandwidth']
    inputs, outputs, _ = graphlib.tensor_roles(g)

    pipe_cycles = {p: 0 for p in graphlib.PIPES}
    for v in g.nodes:
        pipe_cycles[g.pipe(v)] += g.cycles(v)

    depth = max(g.level.values()) + 1 if g.nodes else 0
    width = defaultdict(int)
    for v in g.nodes:
        width[g.level[v]] += 1

    tensor_sizes = [t['size'] for t in g.tensors.values()]
    mid_sizes = [g.size(t) for t in g.tensors
                 if g.producers[t] and g.consumers[t]]

    # 复用度：中间张量被多少个算子消费（切分后可能变成重复读取）
    fanout = [len(g.consumers[t]) for t in g.tensors if g.consumers[t]]
    multi_reader_bytes = sum(g.size(t) for t in g.tensors
                             if len(g.consumers[t]) > 1)

    ncomp, comp_sizes, comp_work = _component_stats(g)
    total_cycles = sum(pipe_cycles.values())
    ddr_bytes = graphlib.original_copy_bytes(g)

    feats = {
        'case': g.name,
        # --- 规模 ---
        'n_ops_all': len(g.ops),
        'n_ops': g.n,
        'n_tensors': len(g.tensors),
        'n_edges': sum(len(s) for s in g.succs.values()),
        'depth': depth,
        'avg_width': g.n / depth if depth else 0.0,
        'max_width': max(width.values()) if width else 0,
        # --- 计算 ---
        'total_cycles': total_cycles,
        'pipe_m_cycles': pipe_cycles['PIPE_M'],
        'pipe_v_cycles': pipe_cycles['PIPE_V'],
        'mv_ratio': (pipe_cycles['PIPE_M'] / pipe_cycles['PIPE_V']
                     if pipe_cycles['PIPE_V'] else math.inf),
        'balanced_compute': max(pipe_cycles['PIPE_M'], pipe_cycles['PIPE_V']),
        'critical_path_cycles': _weighted_critical_path(g),
        # --- 通信 ---
        'original_copy_bytes': ddr_bytes,
        'ddr_input_bytes': sum(inputs.values()),
        'ddr_output_bytes': sum(outputs.values()),
        'ddr_time_lb': ddr_bytes / bw,
        'intermediate_bytes': sum(mid_sizes),
        'multi_reader_bytes': multi_reader_bytes,
        'mean_fanout': (sum(fanout) / len(fanout)) if fanout else 0.0,
        'max_fanout': max(fanout) if fanout else 0,
        # --- 缓存压力 ---
        'max_tensor_bytes': max(tensor_sizes) if tensor_sizes else 0,
        'mean_tensor_bytes': (sum(tensor_sizes) / len(tensor_sizes)
                              if tensor_sizes else 0),
        'l1_bytes': sum(t['size'] for t in g.tensors.values() if t['pos'] == 'L1'),
        'ub_bytes': sum(t['size'] for t in g.tensors.values() if t['pos'] == 'UB'),
        'l1_pressure': sum(t['size'] for t in g.tensors.values()
                           if t['pos'] == 'L1') / cfg['L1'],
        'ub_pressure': sum(t['size'] for t in g.tensors.values()
                           if t['pos'] == 'UB') / cfg['UB'],
        # --- 结构 ---
        'n_components': ncomp,
        'largest_component_frac': comp_sizes[0] / g.n if g.n else 0.0,
        'top4_component_work_frac': (sum(comp_work[:4]) / sum(comp_work)
                                     if sum(comp_work) else 0.0),
        'mean_in_degree': (sum(len(g.preds[v]) for v in g.nodes) / g.n
                           if g.n else 0.0),
        'mean_out_degree': (sum(len(g.succs[v]) for v in g.nodes) / g.n
                            if g.n else 0.0),
        'source_ops': sum(1 for v in g.nodes if not g.preds[v]),
        'sink_ops': sum(1 for v in g.nodes if not g.succs[v]),
    }
    # 计算/带宽瓶颈判别：并行上界与 DDR 下界的比值
    feats['compute_over_ddr'] = (feats['balanced_compute'] / feats['ddr_time_lb']
                                 if feats['ddr_time_lb'] else math.inf)
    feats['cp_over_total'] = (feats['critical_path_cycles'] / total_cycles
                              if total_cycles else 0.0)
    return feats


_FEATURE_CACHE: dict = {}


def case_features(case: str, refresh: bool = False) -> dict:
    if case in _FEATURE_CACHE and not refresh:
        return _FEATURE_CACHE[case]
    f = paths.CACHE_DIR / 'features' / f'{case}.json'
    if f.is_file() and not refresh:
        feats = json.loads(f.read_text(encoding='utf-8'))
    else:
        feats = extract(graphlib.load_graph(paths.case_path(case)))
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(feats, ensure_ascii=False, indent=1),
                     encoding='utf-8')
    _FEATURE_CACHE[case] = feats
    return feats


def all_features(cases=None, refresh: bool = False) -> list:
    return [case_features(c, refresh) for c in (cases or paths.all_cases())]
