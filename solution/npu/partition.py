# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Sonnet 5（型号 claude-sonnet-5）、Claude Opus 5.5（型号 claude-opus-5-5）
# 开发机构：Anthropic 公司
# 版本发布日期：Claude Sonnet 5 为 2026-06-30，Claude Opus 5.5 为 2026-09-22
"""切图：从算子 DAG 构造"块"（block），块是子图的候选单元。

设计要点
--------
1. **亲和原子化**：以"张量扇出阈值 θ"区分强连接与广播连接。
   扇出 ≤ θ 的张量把它的生产者/消费者绑成一个原子（切开它必然产生
   DDR 往返）；扇出 > θ 的张量视为广播数据，允许被多个原子重复读取
   （问题 3 中这类重复读取由 L2 承担，代价极低）。
2. **SCC 合并**：收缩后的原子图可能成环，用 Tarjan 求强连通分量并合并，
   保证原子图是 DAG。
3. **局部性线性序 σ**：原子按拓扑序排列，原子内部用"逆向 DFS"顺序
   （与官方 Step1 同族），使得 σ 的任意连续区间近似一个"祖先锥"。
4. **块 = σ 的连续区间**：连续区间构成凸划分，商图必为 DAG，从而
   自动满足官方评估器的"子图依赖无环 + 同核顺序合法"硬约束。
5. **块合并**：在核心分配之后，把同核相邻块合并成更大的子图（问题 1
   用来摊薄边界搬运），合并前用可达性位图检验不产生环。
"""

from __future__ import annotations

import math
from collections import defaultdict

from . import graphlib

INF = float('inf')


# --------------------------------------------------------------------------
# 1. 亲和原子
# --------------------------------------------------------------------------

class _DSU:
    def __init__(self, items):
        self.p = {x: x for x in items}

    def find(self, x):
        p = self.p
        while p[x] != x:
            p[x] = p[p[x]]
            x = p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


def affinity_atoms(g: graphlib.Graph, theta: float) -> list:
    """扇出阈值 θ 下的亲和原子（无向连通块）。"""
    dsu = _DSU(g.nodes)
    for tid in g.tensors:
        ps, cs = g.producers[tid], g.consumers[tid]
        if not ps and not cs:
            continue
        if len(cs) > theta:          # 广播张量：允许重复读取，不绑定
            continue
        members = list(ps) + list(cs)
        first = members[0]
        for x in members[1:]:
            dsu.union(first, x)
    groups = defaultdict(list)
    for v in g.nodes:
        groups[dsu.find(v)].append(v)
    return list(groups.values())


def _atom_graph(g: graphlib.Graph, atom_of: dict, n_atoms: int):
    succ = [set() for _ in range(n_atoms)]
    for v in g.nodes:
        a = atom_of[v]
        for w in g.succs[v]:
            b = atom_of[w]
            if a != b:
                succ[a].add(b)
    return succ


def _merge_scc(atoms: list, atom_of: dict, succ: list):
    """Tarjan 求 SCC 并把每个 SCC 合成一个原子，保证原子图无环。"""
    n = len(atoms)
    index = [-1] * n
    low = [0] * n
    on_stack = [False] * n
    stack, comp, counter = [], [-1] * n, [0, 0]
    for root in range(n):
        if index[root] != -1:
            continue
        work = [(root, iter(succ[root]))]
        index[root] = low[root] = counter[0]
        counter[0] += 1
        stack.append(root)
        on_stack[root] = True
        while work:
            v, it = work[-1]
            advanced = False
            for w in it:
                if index[w] == -1:
                    index[w] = low[w] = counter[0]
                    counter[0] += 1
                    stack.append(w)
                    on_stack[w] = True
                    work.append((w, iter(succ[w])))
                    advanced = True
                    break
                if on_stack[w]:
                    low[v] = min(low[v], index[w])
            if advanced:
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[v])
            if low[v] == index[v]:
                cid = counter[1]
                counter[1] += 1
                while True:
                    w = stack.pop()
                    on_stack[w] = False
                    comp[w] = cid
                    if w == v:
                        break
    if counter[1] == n:
        return atoms, atom_of, succ
    merged = defaultdict(list)
    for a, members in enumerate(atoms):
        merged[comp[a]].extend(members)
    new_atoms = [merged[c] for c in sorted(merged)]
    remap = {c: i for i, c in enumerate(sorted(merged))}
    new_atom_of = {}
    for i, members in enumerate(new_atoms):
        for v in members:
            new_atom_of[v] = i
    new_succ = [set() for _ in new_atoms]
    for a in range(n):
        for b in succ[a]:
            x, y = remap[comp[a]], remap[comp[b]]
            if x != y:
                new_succ[x].add(y)
    return new_atoms, new_atom_of, new_succ


# --------------------------------------------------------------------------
# 2. 局部性线性序
# --------------------------------------------------------------------------

def locality_order(g: graphlib.Graph, members) -> list:
    """对一组算子给出"逆向 DFS"拓扑序：尽量把同一祖先锥排在一起。

    与官方 Step1 同族（从汇点出发、优先补齐前驱），因此块内部的顺序与
    评估器核内调度看到的顺序高度一致，能让块的峰值驻留估计更可靠。
    """
    member_set = set(members)
    preds = {v: [p for p in g.preds[v] if p in member_set] for v in member_set}
    succs = {v: [s for s in g.succs[v] if s in member_set] for v in member_set}
    sinks = sorted((v for v in member_set if not succs[v]),
                   key=lambda v: (g.level[v], v))
    if not sinks:
        sinks = sorted(member_set)
    visited = set()
    order = []
    stack = list(reversed(sinks))
    while stack:
        u = stack[-1]
        if u in visited:
            stack.pop()
            continue
        pending = [p for p in preds[u] if p not in visited]
        if pending:
            pending.sort(key=lambda v: (-g.level[v], -v))
            stack.extend(pending)
            continue
        visited.add(u)
        order.append(u)
        stack.pop()
    if len(order) != len(member_set):           # 兜底：补齐（理论上不会发生）
        order.extend(sorted(member_set - visited))
    return order


def _atom_topo_order(succ: list, weight: list) -> list:
    """原子图的拓扑序，同层内按计算量降序（利于后续装箱）。"""
    import heapq
    n = len(succ)
    indeg = [0] * n
    for a in range(n):
        for b in succ[a]:
            indeg[b] += 1
    heap = [(-weight[a], a) for a in range(n) if indeg[a] == 0]
    heapq.heapify(heap)
    order = []
    while heap:
        _, a = heapq.heappop(heap)
        order.append(a)
        for b in sorted(succ[a]):
            indeg[b] -= 1
            if indeg[b] == 0:
                heapq.heappush(heap, (-weight[b], b))
    if len(order) != n:
        raise RuntimeError('atom graph is cyclic after SCC merge')
    return order


# --------------------------------------------------------------------------
# 3. 块构造
# --------------------------------------------------------------------------

class BlockSet:
    """σ 连续区间构成的块集合 + 块级 DAG + 块级代价。"""

    def __init__(self, g, blocks, sigma):
        self.g = g
        self.blocks = blocks                      # list[list[op_id]]，σ 顺序
        self.sigma = sigma
        self.block_of = {}
        for i, b in enumerate(blocks):
            for v in b:
                self.block_of[v] = i
        self.m = len(blocks)
        self._compute_costs()
        self._compute_edges()

    def _compute_costs(self):
        g = self.g
        self.mcycles = [0] * self.m
        self.vcycles = [0] * self.m
        self.nops = [len(b) for b in self.blocks]
        for i, b in enumerate(self.blocks):
            m = v = 0
            for op in b:
                if g.pipe(op) == 'PIPE_M':
                    m += g.cycles(op)
                elif g.pipe(op) == 'PIPE_V':
                    v += g.cycles(op)
            self.mcycles[i] = m
            self.vcycles[i] = v
        self.work = [self.mcycles[i] + self.vcycles[i] for i in range(self.m)]

    def _compute_edges(self):
        """块间通信：cut_bytes[(i,j)] = 若 i、j 不在同一单元需 DDR 中转的字节。

        同时记录每个张量涉及的块集合，用于广播复读代价与 Cache 收益估计。
        """
        g = self.g
        self.tensor_blocks = {}          # tid -> (producer blocks, consumer blocks)
        self.pair_bytes = defaultdict(int)
        self.broadcast = []              # (tid, size, producer block or None, consumer blocks)
        for tid, t in g.tensors.items():
            ps, cs = g.producers[tid], g.consumers[tid]
            if not ps and not cs:
                continue
            pb = {self.block_of[o] for o in ps}
            cb = {self.block_of[o] for o in cs}
            self.tensor_blocks[tid] = (pb, cb)
            size = t['size']
            if pb and cb:
                for a in pb:
                    for b in cb:
                        if a != b:
                            key = (a, b) if a < b else (b, a)
                            self.pair_bytes[key] += size
            if len(cb) > 1:
                self.broadcast.append((tid, size, tuple(sorted(pb)), tuple(sorted(cb))))
        # 块级依赖必须取自"收缩 COPY 后的算子 DAG"，而不是张量关系：
        # 形如 op→COPY_OUT→DDR→COPY_IN→op 的依赖在张量关系里是断开的，
        # 但官方 derive_multicore_plan 会把它还原成子图依赖。漏掉这类边会
        # 让合并阶段的无环判据失效。
        self.succ = [set() for _ in range(self.m)]
        self.pred = [set() for _ in range(self.m)]
        bo = self.block_of
        for v in g.nodes:
            a = bo[v]
            for w in g.succs[v]:
                b = bo[w]
                if a != b:
                    self.succ[a].add(b)
                    self.pred[b].add(a)


def make_blocks(g: graphlib.Graph, num_cores: int,
                block_cap: float = 0.5,
                theta_candidates=(INF, 16, 8, 4, 2, 1),
                min_block_ops: int = 1,
                use_affinity: bool = True) -> BlockSet:
    """构造块集合。

    ``block_cap``：单块计算量上限 = block_cap × 总计算量 / 核数。
    θ 从大到小尝试，取第一个使"最大原子 ≤ 上限"的值；仍超限的原子再沿
    σ 切成连续小块。``use_affinity=False`` 时退化为纯拓扑区间切分
    （消融实验用：去掉通信感知）。
    """
    total_work = sum(g.cycles(v) for v in g.nodes)
    cap = max(1.0, block_cap * total_work / max(1, num_cores))

    if use_affinity:
        chosen = None
        for theta in theta_candidates:
            atoms = affinity_atoms(g, theta)
            if not atoms:
                continue
            biggest = max(sum(g.cycles(v) for v in a) for a in atoms)
            chosen = (theta, atoms)
            if biggest <= cap:
                break
        theta, atoms = chosen
    else:
        theta, atoms = INF, [list(g.nodes)]

    atom_of = {}
    for i, members in enumerate(atoms):
        for v in members:
            atom_of[v] = i
    succ = _atom_graph(g, atom_of, len(atoms))
    atoms, atom_of, succ = _merge_scc(atoms, atom_of, succ)
    weight = [sum(g.cycles(v) for v in a) for a in atoms]
    order = _atom_topo_order(succ, weight)

    sigma, blocks = [], []
    for a in order:
        members = locality_order(g, atoms[a])
        sigma.extend(members)
        if weight[a] <= cap or len(members) <= min_block_ops:
            blocks.append(members)
            continue
        # 超限原子：沿局部性序切成连续块
        pieces = max(2, int(math.ceil(weight[a] / cap)))
        target = weight[a] / pieces
        cur, cur_w = [], 0.0
        for v in members:
            cur.append(v)
            cur_w += g.cycles(v)
            if cur_w >= target:
                blocks.append(cur)
                cur, cur_w = [], 0.0
        if cur:
            blocks.append(cur)
    blocks = [b for b in blocks if b]
    bs = BlockSet(g, blocks, sigma)
    bs.theta = theta
    bs.cap = cap
    return bs


# --------------------------------------------------------------------------
# 4. 块合并（受可达性约束）
# --------------------------------------------------------------------------

def reachability(succ: list) -> list:
    """位图传递闭包：reach[i] 的第 j 位为 1 表示 i 可达 j（不含自身）。"""
    m = len(succ)
    reach = [0] * m
    for i in range(m - 1, -1, -1):
        acc = 0
        for j in succ[i]:
            acc |= (1 << j) | reach[j]
        reach[i] = acc
    return reach


def merge_same_core_blocks(bs: BlockSet, core_of_block: list,
                           max_ops: int, max_work: float,
                           max_bytes: float = INF) -> list:
    """把同核相邻块贪心合并成子图组，返回 list[list[block_id]]。

    合并条件：(a) 同核；(b) 规模不超限；(c) 合并后商图仍无环。
    无环判据：设已并集合 S（σ 序在前）与候选块 j，若存在块 k∉S∪{j}
    使 S ⇝ k ⇝ j，则合并会产生环，拒绝。
    """
    reach = reachability(bs.succ)
    coreach = [0] * bs.m
    for i in range(bs.m):
        for j in bs.succ[i]:
            coreach[j] |= (1 << i) | coreach[i]

    groups, current = [], {}
    for i in range(bs.m):
        k = core_of_block[i]
        grp = current.get(k)
        if grp is None:
            grp = {'blocks': [i], 'ops': bs.nops[i], 'work': bs.work[i],
                   'mask': 1 << i, 'reach': reach[i]}
            current[k] = grp
            groups.append((k, grp))
            continue
        ok = (grp['ops'] + bs.nops[i] <= max_ops
              and grp['work'] + bs.work[i] <= max_work)
        if ok:
            middle = grp['reach'] & coreach[i]
            if middle & ~(grp['mask'] | (1 << i)):
                ok = False
        if ok:
            grp['blocks'].append(i)
            grp['ops'] += bs.nops[i]
            grp['work'] += bs.work[i]
            grp['mask'] |= 1 << i
            grp['reach'] |= reach[i]
        else:
            grp = {'blocks': [i], 'ops': bs.nops[i], 'work': bs.work[i],
                   'mask': 1 << i, 'reach': reach[i]}
            current[k] = grp
            groups.append((k, grp))
    return [(k, g['blocks']) for k, g in groups]
