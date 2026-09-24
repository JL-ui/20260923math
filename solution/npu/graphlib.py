"""计算图解析与算子级 DAG 构造。

本模块的语义严格对齐官方评估器：

* 可切分节点 = 除 ``COPY_IN``/``COPY_OUT`` 之外的全部 op（见
  ``stub_multicore_cut_and_schedule.EXCLUDED_COPY_TYPES``）；
* 算子级依赖 = 把 tensor 中转边与直接 op→op 边统一展开后，再把
  COPY 节点收缩掉（等价于 ``_contract_excluded_copy_nodes``）；
* 张量的 producer / consumer 只统计"可切分 op"，与评估器的
  ``eligible_producers`` / ``eligible_consumers`` 一致。

因此本模块给出的边界搬运量预测与评估器的 ``data_movement_bytes``
在结构上完全对应（唯一差别是核内 spill，它由 Step2 在运行时决定）。
"""

from __future__ import annotations

import json
import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path

PIPES = ('PIPE_MTE2', 'PIPE_MTE3', 'PIPE_M', 'PIPE_V')
COPY_TYPES = ('COPY_IN', 'COPY_OUT')


@dataclass
class Graph:
    """原始计算图的只读视图 + 预计算的算子级 DAG。"""

    name: str
    ops: dict                      # op_id -> op dict
    tensors: dict                  # tensor_id -> tensor dict
    nodes: list                    # 可切分 op（升序）
    index: dict                    # op_id -> 0..n-1 稠密下标
    preds: dict                    # op_id -> set(op_id)   收缩 COPY 后
    succs: dict                    # op_id -> set(op_id)
    producers: dict                # tensor_id -> set(可切分 op)
    consumers: dict                # tensor_id -> set(可切分 op)
    op_in: dict                    # op_id -> list(tensor_id)
    op_out: dict                   # op_id -> list(tensor_id)
    direct_edges: list             # 原图里的 op->op 直接边
    graph_output_tensor: set       # 被原始 COPY_OUT 消费的 tensor
    topo: list = field(default_factory=list)      # 可切分 op 的拓扑序
    level: dict = field(default_factory=dict)     # 最长路径层号
    _cache: dict = field(default_factory=dict)

    # ---------- 基础属性 ----------
    def cycles(self, op_id: int) -> int:
        return int(self.ops[op_id].get('cycles', 0))

    def pipe(self, op_id: int) -> str:
        return self.ops[op_id]['pipe']

    def size(self, tensor_id: int) -> int:
        return int(self.tensors[tensor_id]['size'])

    @property
    def n(self) -> int:
        return len(self.nodes)


def load_graph(path) -> Graph:
    path = Path(path)
    raw = json.loads(path.read_text(encoding='utf-8'))
    return build_graph(raw, name=path.stem)


def build_graph(raw: dict, name: str = 'graph') -> Graph:
    ops = {o['id']: o for o in raw['ops']}
    tensors = {t['id']: t for t in raw['tensors']}
    op_ids = set(ops)
    copy_ids = {i for i, o in ops.items() if o.get('op') in COPY_TYPES}
    nodes = sorted(op_ids - copy_ids)

    # --- 原始二部图展开 ---
    prod_all = defaultdict(set)   # tensor -> 全部 producer op（含 COPY）
    cons_all = defaultdict(set)   # tensor -> 全部 consumer op（含 COPY）
    op_in = defaultdict(list)
    op_out = defaultdict(list)
    direct_edges = []
    for e in raw['edges']:
        s, t = e['source'], e['target']
        s_is_op, t_is_op = s in op_ids, t in op_ids
        if s_is_op and not t_is_op:
            prod_all[t].add(s)
            op_out[s].append(t)
        elif t_is_op and not s_is_op:
            cons_all[s].add(t)
            op_in[t].append(s)
        elif s_is_op and t_is_op and s != t:
            direct_edges.append({'source': s, 'target': t})

    # --- 含 COPY 的完整 op 邻接（用于收缩） ---
    full_succs = defaultdict(set)
    for tid, ps in prod_all.items():
        cs = cons_all.get(tid, ())
        for a in ps:
            for b in cs:
                if a != b:
                    full_succs[a].add(b)
    for e in direct_edges:
        full_succs[e['source']].add(e['target'])

    # --- 收缩 COPY 节点，得到可切分 op 之间的依赖 ---
    node_set = set(nodes)
    preds = {v: set() for v in nodes}
    succs = {v: set() for v in nodes}
    for v in nodes:
        stack = list(full_succs.get(v, ()))
        seen_copy = set()
        while stack:
            w = stack.pop()
            if w in node_set:
                if w != v:
                    succs[v].add(w)
                    preds[w].add(v)
                continue
            if w in seen_copy:
                continue
            seen_copy.add(w)
            stack.extend(full_succs.get(w, ()))

    producers = {tid: (ps & node_set) for tid, ps in prod_all.items()}
    consumers = {tid: (cs & node_set) for tid, cs in cons_all.items()}
    for tid in tensors:
        producers.setdefault(tid, set())
        consumers.setdefault(tid, set())

    graph_output_tensor = set()
    for cid in copy_ids:
        if ops[cid].get('op') == 'COPY_OUT':
            graph_output_tensor.update(op_in.get(cid, ()))

    g = Graph(
        name=name, ops=ops, tensors=tensors, nodes=nodes,
        index={v: i for i, v in enumerate(nodes)},
        preds=preds, succs=succs,
        producers=producers, consumers=consumers,
        op_in=dict(op_in), op_out=dict(op_out),
        direct_edges=direct_edges,
        graph_output_tensor=graph_output_tensor,
    )
    g.topo, g.level = _topo_and_level(g)
    return g


def _topo_and_level(g: Graph):
    indeg = {v: len(g.preds[v]) for v in g.nodes}
    ready = deque(v for v in g.nodes if indeg[v] == 0)
    level = {v: 0 for v in g.nodes}
    topo = []
    while ready:
        u = ready.popleft()
        topo.append(u)
        for w in g.succs[u]:
            if level[w] < level[u] + 1:
                level[w] = level[u] + 1
            indeg[w] -= 1
            if indeg[w] == 0:
                ready.append(w)
    if len(topo) != len(g.nodes):
        raise ValueError(f'{g.name}: contracted op graph has a cycle')
    return topo, level


# --------------------------------------------------------------------------
# 张量分类（与评估器的边界规则一一对应）
# --------------------------------------------------------------------------

def tensor_roles(g: Graph):
    """把张量分成 图输入 / 中间 / 图输出 三类，并给出大小。

    * 图输入：无可切分 producer，但有可切分 consumer（原图里由 COPY_IN 搬入）；
    * 图输出：有可切分 producer，且被原始 COPY_OUT 消费或没有可切分 consumer；
    * 中间：既有 producer 又有 consumer。
    """
    inputs, outputs, middles = {}, {}, {}
    for tid, t in g.tensors.items():
        ps, cs = g.producers[tid], g.consumers[tid]
        if not ps and not cs:
            continue
        if not ps:
            inputs[tid] = t['size']
            continue
        if tid in g.graph_output_tensor or not cs:
            outputs[tid] = t['size']
        if cs:
            middles[tid] = t['size']
    return inputs, outputs, middles


# --------------------------------------------------------------------------
# 切图方案的搬运量 / 负载 解析模型
# --------------------------------------------------------------------------

def original_copy_bytes(g: Graph) -> int:
    """原图自带的 DDR 搬运量（评估器 ``original_graph_copy_bytes``）。"""
    total = 0
    for oid, op in g.ops.items():
        kind = op.get('op')
        if kind == 'COPY_IN':
            total += sum(g.size(t) for t in g.op_out.get(oid, ()) if t in g.tensors)
        elif kind == 'COPY_OUT':
            total += sum(g.size(t) for t in g.op_in.get(oid, ()) if t in g.tensors)
    return total


def scene_a_copy_bytes(g: Graph, mapping: dict) -> int:
    """问题 1：按子图边界规则统计总 COPY 字节（不含核内 spill）。"""
    total = 0
    for tid, t in g.tensors.items():
        ps, cs = g.producers[tid], g.consumers[tid]
        if not ps and not cs:
            continue
        size = t['size']
        p_sub = {mapping[o] for o in ps}
        c_sub = {mapping[o] for o in cs}
        is_out = tid in g.graph_output_tensor
        # COPY_IN：每个"只消费不生产"该张量的子图各读一次
        total += size * len(c_sub - p_sub)
        # COPY_OUT：每个生产该张量、且需要写回 DDR 的子图各写一次
        for sg in p_sub:
            if is_out or not c_sub or (c_sub - {sg}):
                total += size
    return total


def scene_b_copy_bytes(g: Graph, mapping: dict, core_of_sub: dict) -> int:
    """问题 2/3：按核边界规则统计总 COPY 字节（不含核内 spill）。"""
    total = 0
    for tid, t in g.tensors.items():
        ps, cs = g.producers[tid], g.consumers[tid]
        if not ps and not cs:
            continue
        size = t['size']
        p_cores = {core_of_sub[mapping[o]] for o in ps}
        c_cores = {core_of_sub[mapping[o]] for o in cs}
        is_out = tid in g.graph_output_tensor
        if cs and not ps:                       # 图输入：每个消费核读一次
            total += size * len(c_cores)
        if ps and (is_out or not cs):           # 图输出：每个生产核写一次
            total += size * len(p_cores)
        for sc in p_cores:                      # 跨核：每条 (src,dst) 一对 COPY
            total += 2 * size * len(c_cores - {sc})
    return total


def scene_b_cross_bytes(g: Graph, mapping: dict, core_of_sub: dict) -> int:
    """问题 2/3 的跨核单向传输字节（cross_task_traffic）。"""
    total = 0
    for tid, t in g.tensors.items():
        ps, cs = g.producers[tid], g.consumers[tid]
        if not ps or not cs:
            continue
        size = t['size']
        p_cores = {core_of_sub[mapping[o]] for o in ps}
        c_cores = {core_of_sub[mapping[o]] for o in cs}
        for sc in p_cores:
            total += size * len(c_cores - {sc})
    return total


# --------------------------------------------------------------------------
# 子图/核心负载的解析代价模型（用于搜索内部的快速评价）
# --------------------------------------------------------------------------

def pipe_workload(g: Graph, node_ids) -> dict:
    """一组算子在四条 Pipe 上的计算负载（不含边界 COPY）。"""
    load = {p: 0 for p in PIPES}
    for v in node_ids:
        load[g.pipe(v)] += g.cycles(v)
    return load


def subgraph_boundary_bytes(g: Graph, members: set, mapping: dict):
    """给定子图成员集合，返回 (copy_in 字节, copy_out 字节)。"""
    cin = cout = 0
    touched = set()
    for v in members:
        touched.update(g.op_in.get(v, ()))
        touched.update(g.op_out.get(v, ()))
    for tid in touched:
        ps, cs = g.producers[tid], g.consumers[tid]
        size = g.size(tid)
        local_p = ps & members
        local_c = cs & members
        if local_c and not local_p:
            cin += size
        if local_p:
            if tid in g.graph_output_tensor or not cs or (cs - members):
                cout += size
    return cin, cout


def copy_cycles(nbytes: int, bandwidth: int) -> int:
    return max(1, math.ceil(nbytes / bandwidth)) if nbytes else 0
