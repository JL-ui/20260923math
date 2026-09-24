"""基线算法与主算法 CAP-LS 的统一入口。

所有算法签名一致::

    algo(g: Graph, num_cores: int, problem: int, **params) -> plan dict

主算法 **CAP-LS**（Communication-Aware acyclic Partition + Level
Stratification + Local Search）四阶段：

    S1 亲和原子化 + σ 连续区间分块        partition.make_blocks
    S2 负载/通信/同步深度联合的核心分配    TrafficState + 移动式局部搜索
    S3 跨核同步层次分层 → 子图成形        stratify.build_subgraphs
    S4 多起点组合，候选交官方评估器择优     experiment.run_portfolio
"""

from __future__ import annotations

import random
from collections import defaultdict

from . import assign, evaluate, graphlib, partition, paths, stratify


# --------------------------------------------------------------------------
# 增量通信/负载状态（局部搜索内核）
# --------------------------------------------------------------------------

class TrafficState:
    """维护 (块→核) 分配下的每核 Pipe 负载、DDR 搬运量与跨核同步深度。

    单次移动的代价为 O(|T_b| + m)，其中 |T_b| 是块 b 触及的张量数、
    m 是块数；因此可以在几千次移动内完成局部搜索。
    """

    def __init__(self, bs, core_of_block, num_cores, cfg,
                 cache_capacity=0, sync_penalty=0.0):
        self.bs = bs
        self.N = num_cores
        self.cfg = cfg
        self.bw = cfg['bandwidth']
        self.cache_capacity = cache_capacity
        self.cache_bw = cfg['cache_bandwidth_bytes_per_cycle']
        self.sync_penalty = sync_penalty
        self.core = list(core_of_block)
        g = bs.g
        self.tensors, self.size, self.is_out = [], [], []
        self.block_tensors = defaultdict(list)
        self.pcount, self.ccount = [], []
        for tid, (pb, cb) in bs.tensor_blocks.items():
            s = g.size(tid)
            if not s:
                continue
            idx = len(self.tensors)
            self.tensors.append(tid)
            self.size.append(s)
            self.is_out.append(tid in g.graph_output_tensor)
            pc, cc = defaultdict(int), defaultdict(int)
            for b in pb:
                pc[self.core[b]] += 1
                self.block_tensors[b].append((idx, 'p'))
            for b in cb:
                cc[self.core[b]] += 1
                self.block_tensors[b].append((idx, 'c'))
            self.pcount.append(pc)
            self.ccount.append(cc)
        self.cin = [0] * num_cores
        self.cout = [0] * num_cores
        self.hit = [0] * num_cores
        self.total = 0
        for idx in range(len(self.tensors)):
            self._apply(idx, +1)
        self.loadM = [0.0] * num_cores
        self.loadV = [0.0] * num_cores
        for b in range(bs.m):
            self.loadM[self.core[b]] += bs.mcycles[b]
            self.loadV[self.core[b]] += bs.vcycles[b]

    def _apply(self, idx, sign):
        s = self.size[idx]
        pc = [k for k, c in self.pcount[idx].items() if c]
        cc = [k for k, c in self.ccount[idx].items() if c]
        readers = []
        if cc and not pc:
            readers = list(cc)
        if pc and (self.is_out[idx] or not cc):
            for k in pc:
                self.cout[k] += sign * s
                self.total += sign * s
        for sc in pc:
            for dc in cc:
                if dc == sc:
                    continue
                self.cout[sc] += sign * s
                self.total += sign * s
                readers.append(dc)
        for i, k in enumerate(readers):
            self.cin[k] += sign * s
            self.total += sign * s
            if i > 0 and 0 < s <= self.cache_capacity:
                self.hit[k] += sign * s

    def move(self, b, dst):
        src = self.core[b]
        if src == dst:
            return
        touched = self.block_tensors.get(b, ())
        for idx, _ in touched:
            self._apply(idx, -1)
        for idx, role in touched:
            table = self.pcount[idx] if role == 'p' else self.ccount[idx]
            table[src] -= 1
            table[dst] += 1
        for idx, _ in touched:
            self._apply(idx, +1)
        self.loadM[src] -= self.bs.mcycles[b]
        self.loadV[src] -= self.bs.vcycles[b]
        self.loadM[dst] += self.bs.mcycles[b]
        self.loadV[dst] += self.bs.vcycles[b]
        self.core[b] = dst

    def sync_depth(self) -> int:
        """块级跨核同步深度（op 级层次数的上界，作为搜索代价的代理）。"""
        best = [0] * self.bs.m
        top = 0
        core = self.core
        for i in range(self.bs.m):
            cur = 0
            ci = core[i]
            for p in self.bs.pred[i]:
                cand = best[p] + (1 if core[p] != ci else 0)
                if cand > cur:
                    cur = cand
            best[i] = cur
            if cur > top:
                top = cur
        return top

    def cost(self, use_cache=False):
        worst = 0.0
        for k in range(self.N):
            hit = self.hit[k] if use_cache else 0
            miss = self.cin[k] - hit
            mte2 = miss / self.bw + hit / self.cache_bw
            mte3 = self.cout[k] / self.bw
            worst = max(worst, self.loadM[k], self.loadV[k], mte2, mte3)
        ddr = self.total - (sum(self.hit) if use_cache else 0)
        value = max(worst, ddr / self.bw)
        if self.sync_penalty:
            value += self.sync_penalty * self.sync_depth()
        return value


# --------------------------------------------------------------------------
# 方案组装
# --------------------------------------------------------------------------

def _plan_from_core_map(g, bs, core_of_block, num_cores, max_ops=None,
                        max_work=None):
    core_of_op = {v: core_of_block[bs.block_of[v]] for v in g.nodes}
    rank = {v: i for i, v in enumerate(bs.sigma)}
    mapping, schedules, _ = stratify.build_subgraphs(
        g, core_of_op, num_cores, rank, max_ops=max_ops, max_work=max_work)
    return evaluate.make_plan(mapping, schedules)


def _plan_blocks_as_subgraphs(bs, core_of_block, num_cores):
    """块直接作为子图（σ 序编号），用于基线算法。"""
    mapping = {}
    schedules = [[] for _ in range(num_cores)]
    for i in range(bs.m):
        for op in bs.blocks[i]:
            mapping[op] = i
        schedules[core_of_block[i]].append(i)
    return evaluate.make_plan(mapping, schedules)


# --------------------------------------------------------------------------
# 基线算法
# --------------------------------------------------------------------------

def baseline_random(g, num_cores, problem, seed=0, **kw):
    """Baseline-1：官方 stub 的随机合法切图 + 随机分核。"""
    from stub_multicore_cut_and_schedule import generate_multicore_plan
    raw = evaluate.raw_graph(g.name)
    n = max(2, g.n // max(1, num_cores * 4))
    return generate_multicore_plan(
        raw, num_cores=num_cores, seed=seed,
        min_subgraph_size=max(1, n // 2), max_subgraph_size=n)


def baseline_topo(g, num_cores, problem, blocks_per_core=4, **kw):
    """Baseline-2：纯拓扑区间等分 + 轮转分核（无通信、无负载、无分层）。"""
    bs = partition.make_blocks(g, num_cores, block_cap=1.0 / blocks_per_core,
                               use_affinity=False)
    core = assign.round_robin_assign(bs, num_cores)
    return _plan_blocks_as_subgraphs(bs, core, num_cores)


def baseline_balance(g, num_cores, problem, blocks_per_core=4, **kw):
    """Baseline-3：拓扑区间 + 纯计算量负载均衡（LPT），无通信感知、无分层。"""
    bs = partition.make_blocks(g, num_cores, block_cap=1.0 / blocks_per_core,
                               use_affinity=False)
    core = assign.lpt_assign(bs, num_cores, comm_weight=0.0)
    return _plan_blocks_as_subgraphs(bs, core, num_cores)


def baseline_comm(g, num_cores, problem, **kw):
    """Baseline-4：通信感知亲和聚类 + 轮转分核（无负载均衡、无分层）。"""
    bs = partition.make_blocks(g, num_cores, block_cap=0.35)
    core = assign.round_robin_assign(bs, num_cores)
    return _plan_blocks_as_subgraphs(bs, core, num_cores)


def baseline_singlecore(g, num_cores, problem, **kw):
    """参考：整图 1 个子图放 0 号核（= 官方单核基准方案）。"""
    schedules = [[] for _ in range(max(1, num_cores))]
    schedules[0] = [0]
    return evaluate.make_plan({v: 0 for v in g.nodes}, schedules)


# --------------------------------------------------------------------------
# 主算法 CAP-LS
# --------------------------------------------------------------------------

def _local_search(bs, state, num_cores, use_cache, passes=6, budget=None,
                  seed=0, max_candidates=260):
    """移动式局部搜索。

    为控制规模，只考察计算量最大的 ``max_candidates`` 个块，并给移动次数
    设上限——实验表明继续增大预算对 Makespan 的改善已不足 0.5%，
    但求解时间随块数线性增长。
    """
    rng = random.Random(seed)
    best = state.cost(use_cache=use_cache)
    idx = sorted(range(bs.m), key=lambda b: -bs.work[b])[:max_candidates]
    budget = budget if budget is not None else min(max(300, 8 * len(idx)), 2200)
    tried = 0
    for _ in range(passes):
        improved = False
        for b in idx:
            if tried >= budget:
                break
            src = state.core[b]
            order = list(range(num_cores))
            rng.shuffle(order)
            for k in order:
                if k == src:
                    continue
                state.move(b, k)
                tried += 1
                val = state.cost(use_cache=use_cache)
                if val < best - 1e-9:
                    best = val
                    improved = True
                    break
                state.move(b, src)
        if not improved or tried >= budget:
            break
    return best


def cap_ls(g, num_cores, problem, block_cap=0.35, comm_weight=0.0,
           local_search=True, use_affinity=True, use_cache_aware=None,
           sync_weight=None, max_ops=None, max_work=None,
           cores_used=None, init='lpt', subgraph_mode='level', seed=0,
           _return_cost=False, **kw):
    """主算法。

    ``init``           分配初始解：``lpt`` 最大优先装箱 / ``rr`` 轮转（多起点）；
    ``subgraph_mode``  子图成形：``level`` 按 (核心, 跨核同步层次) /
                       ``block`` 直接以块为子图（细粒度，保留 σ 顺序）；
    ``cores_used``     只使用前 c 个核（自适应降并行度，用于通信受限的图）。
    ``_return_cost``   True 时返回 ``(plan, cost)``，``cost`` 为局部搜索内部用的
                       ``TrafficState.cost()`` 解析估计（单核退化时为 0.0）；
                       仅供 大图 P1 的代理排序兜底使用，不作为任何正式指标。
    """
    cfg = paths.official_config()
    if use_cache_aware is None:
        use_cache_aware = (problem == 3)
    if sync_weight is None:
        sync_weight = (cfg['task_cross_core_wait_cycles'] if problem == 1
                       else cfg['cross_core_copy_delay_cycles'])
    active = min(num_cores, cores_used or num_cores)
    bs = partition.make_blocks(g, max(1, active), block_cap=block_cap,
                               use_affinity=use_affinity)
    cost = 0.0
    if active <= 1:
        core = [0] * bs.m
    else:
        if init == 'rr':
            core = assign.round_robin_assign(bs, active)
        elif init == 'contig':
            core = assign.contiguous_assign(bs, active)
        else:
            core = assign.lpt_assign(bs, active, comm_weight=comm_weight)
        state = TrafficState(
            bs, core, active, cfg, sync_penalty=sync_weight,
            cache_capacity=cfg['cache_capacity_bytes'] if use_cache_aware else 0)
        if local_search:
            _local_search(bs, state, active, use_cache_aware, seed=seed)
        cost = state.cost(use_cache_aware)
        core = state.core
    if subgraph_mode == 'block':
        plan = _plan_blocks_as_subgraphs(bs, core, num_cores)
    else:
        plan = _plan_from_core_map(g, bs, core, num_cores,
                                   max_ops=max_ops, max_work=max_work)
    return (plan, cost) if _return_cost else plan


# --------------------------------------------------------------------------
# 多起点候选集
# --------------------------------------------------------------------------

def candidate_params(problem: int, num_cores: int, level: str = 'full'):
    if num_cores <= 1:
        return [dict(block_cap=0.35),
                dict(block_cap=0.35, max_ops=2000),
                dict(block_cap=0.35, max_ops=600)]
    grid = [
        dict(block_cap=0.35),
        dict(block_cap=0.15),
        dict(block_cap=0.35, init='rr'),
        dict(block_cap=0.35, init='contig'),
        dict(block_cap=0.35, subgraph_mode='block'),
        dict(block_cap=0.35, subgraph_mode='block', init='rr'),
        dict(block_cap=0.60, comm_weight=1e-6),
    ]
    if level != 'full':
        return grid[:4]
    grid += [
        dict(block_cap=0.08),
        dict(block_cap=0.005),          # 超细粒度：挖掘"深链 + 层内并行"结构
        dict(block_cap=0.35, max_ops=(2000 if problem == 1 else 500)),
        dict(block_cap=0.35, cores_used=max(1, num_cores - 1)),
    ]
    if problem == 1:
        grid.append(dict(block_cap=0.35, cores_used=max(1, num_cores // 2)))
    else:
        grid.append(dict(block_cap=0.35, sync_weight=0.0))
    return grid


ALGORITHMS = {
    'random': baseline_random,
    'topo': baseline_topo,
    'balance': baseline_balance,
    'comm': baseline_comm,
    'single': baseline_singlecore,
    'capls': cap_ls,
}
