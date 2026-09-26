# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Sonnet 5（型号 claude-sonnet-5）、Claude Opus 5.5（型号 claude-opus-5-5）
# 开发机构：Anthropic 公司
# 版本发布日期：Claude Sonnet 5 为 2026-06-30，Claude Opus 5.5 为 2026-09-22
"""问题 1 的代理驱动模拟退火：在 Task 划分与分核上做合并 / 拆分 / 换核邻域搜索。

适应度为 ``proxy_a.estimate_scene_a_from_plan``。为使每次迭代的代价与图规模
无关，这里用增量状态维护它需要的全部量（各 Task 的 M/V 周期、边界搬运字节、
张量级前驱关系），逐项计算方式与原函数完全相同，因此数值逐位一致
（``_State.estimate`` 与原函数的一致性由 T14 的检查覆盖）。

合法性按官方 P1 评估入口的判据：收缩 COPY 后的子图依赖 ∪ 每核 Task 顺序边无环。
"""

from __future__ import annotations

import math
import random
from collections import defaultdict

from . import evaluate

SEED = 20260924
# 规格默认 3000。预跑量测（case_041 N=4：3000 步 150.2 s、1500 步 55.0 s）显示
# 3000 步会超过 T14 验收的 60 s 上限，按规则降为 1500。退火耗时取决于轨迹里
# 合并/拆分的任务大小（case_087 N=2 反而是 3000 步 7.9 s、1500 步 38.6 s），
# 因此最终是否满足上限以整轮实验的 p1_anneal_report.json 为准。
ITERS = 1500


class _State:
    def __init__(self, g, mapping, schedules, cfg):
        self.g = g
        self.bw = cfg['bandwidth']
        self.same_wait = cfg['task_same_core_wait_cycles']
        self.cross_wait = cfg['task_cross_core_wait_cycles']
        self.task_of = dict(mapping)
        self.sched = [list(o) for o in schedules]
        self.members = defaultdict(set)
        self.M = defaultdict(int)
        self.V = defaultdict(int)
        for v, t in self.task_of.items():
            self.members[t].add(v)
            if g.pipe(v) == 'PIPE_M':
                self.M[t] += g.cycles(v)
            elif g.pipe(v) == 'PIPE_V':
                self.V[t] += g.cycles(v)
        self.topo_pos = {v: i for i, v in enumerate(g.topo)}
        self.tids = [tid for tid in g.tensors
                     if g.producers[tid] or g.consumers[tid]]
        self.tset = set(self.tids)
        self.pcnt = {tid: defaultdict(int) for tid in self.tids}
        self.ccnt = {tid: defaultdict(int) for tid in self.tids}
        for tid in self.tids:
            for o in g.producers[tid]:
                self.pcnt[tid][self.task_of[o]] += 1
            for o in g.consumers[tid]:
                self.ccnt[tid][self.task_of[o]] += 1
        self.cin = defaultdict(int)
        self.cout = defaultdict(int)
        self.total = 0
        self.pred_of = defaultdict(lambda: defaultdict(int))   # b -> {a: 张量数}
        for tid in self.tids:
            self._contrib(tid, +1)
        self.dep = defaultdict(lambda: defaultdict(int))       # a -> {b: 边数}
        for u in g.nodes:
            a = self.task_of[u]
            for w in g.succs[u]:
                b = self.task_of[w]
                if a != b:
                    self.dep[a][b] += 1
        self.next_id = max(self.task_of.values(), default=-1) + 1

    # ---------- 增量维护 ----------
    def _contrib(self, tid, sign):
        P = [t for t, c in self.pcnt[tid].items() if c]
        C = [t for t, c in self.ccnt[tid].items() if c]
        size = self.g.size(tid)
        Ps, Cs = set(P), set(C)
        is_out = tid in self.g.graph_output_tensor
        for s in Cs - Ps:
            self.cin[s] += sign * size
            self.total += sign * size
        for s in Ps:
            if is_out or not Cs or (Cs - {s}):
                self.cout[s] += sign * size
                self.total += sign * size
        for a in Ps:
            for b in Cs:
                if a != b:
                    row = self.pred_of[b]
                    row[a] += sign
                    if row[a] == 0:
                        del row[a]

    def move_ops(self, ops, dst):
        g = self.g
        touched = set()
        edges = set()
        for v in ops:
            touched.update(t for t in g.op_in.get(v, ()) if t in self.tset)
            touched.update(t for t in g.op_out.get(v, ()) if t in self.tset)
            for w in g.succs[v]:
                edges.add((v, w))
            for u in g.preds[v]:
                edges.add((u, v))
        for tid in touched:
            self._contrib(tid, -1)
        for u, w in edges:
            a, b = self.task_of[u], self.task_of[w]
            if a != b:
                row = self.dep[a]
                row[b] -= 1
                if row[b] == 0:
                    del row[b]
        for v in ops:
            old = self.task_of[v]
            if old == dst:
                continue
            self.members[old].discard(v)
            self.members[dst].add(v)
            c = g.cycles(v)
            if g.pipe(v) == 'PIPE_M':
                self.M[old] -= c
                self.M[dst] += c
            elif g.pipe(v) == 'PIPE_V':
                self.V[old] -= c
                self.V[dst] += c
            for tid in g.op_out.get(v, ()):
                if tid in self.tset:
                    self.pcnt[tid][old] -= 1
                    self.pcnt[tid][dst] += 1
            for tid in g.op_in.get(v, ()):
                if tid in self.tset:
                    self.ccnt[tid][old] -= 1
                    self.ccnt[tid][dst] += 1
            self.task_of[v] = dst
        for u, w in edges:
            a, b = self.task_of[u], self.task_of[w]
            if a != b:
                self.dep[a][b] += 1
        for tid in touched:
            self._contrib(tid, +1)

    # ---------- 合法性与适应度 ----------
    def legal(self) -> bool:
        tasks = [t for order in self.sched for t in order]
        tset = set(tasks)
        succ = defaultdict(set)
        for a in tasks:
            for b in self.dep.get(a, ()):
                if b in tset:
                    succ[a].add(b)
        for order in self.sched:
            for a, b in zip(order, order[1:]):
                succ[a].add(b)
        indeg = {t: 0 for t in tasks}
        for a in tasks:
            for b in succ[a]:
                indeg[b] += 1
        stack = [t for t in tasks if indeg[t] == 0]
        seen = 0
        while stack:
            a = stack.pop()
            seen += 1
            for b in succ[a]:
                indeg[b] -= 1
                if indeg[b] == 0:
                    stack.append(b)
        return seen == len(tasks)

    def estimate(self) -> float:
        """与 proxy_a.estimate_scene_a_from_plan 逐项相同的计算。"""
        schedules = self.sched
        core_of_sub = {}
        for k, order in enumerate(schedules):
            for sg in order:
                core_of_sub[sg] = k
        end, core_time, done = {}, {}, set()
        ptr = [0] * len(schedules)
        makespan = 0.0
        remaining = len(core_of_sub)
        bw = self.bw
        while remaining:
            progressed = False
            for k, order in enumerate(schedules):
                if ptr[k] >= len(order):
                    continue
                sg = order[ptr[k]]
                preds = self.pred_of.get(sg, {})
                if any(d not in done for d in preds):
                    continue
                dur = max(self.M[sg], self.V[sg],
                          (self.cin[sg] + self.cout[sg]) / bw, 1.0)
                start = core_time.get(k)
                start = 0.0 if start is None else start + self.same_wait
                for pdep in preds:
                    start = max(start, end[pdep] + (self.cross_wait
                                                    if core_of_sub[pdep] != k else 0))
                end[sg] = start + dur
                core_time[k] = end[sg]
                done.add(sg)
                ptr[k] += 1
                remaining -= 1
                makespan = max(makespan, end[sg])
                progressed = True
            if not progressed:
                raise RuntimeError('scene A estimate: task graph deadlock')
        return max(makespan, self.total / bw)

    def plan(self) -> dict:
        return evaluate.canonical_plan(evaluate.make_plan(self.task_of, self.sched))

    def min_pos(self, t):
        return min(self.topo_pos[v] for v in self.members[t])

    def reaches_via_others(self, a, b) -> bool:
        """商图中是否存在经其他 Task 的 a → … → b 路径。"""
        stack = [x for x in self.dep.get(a, ()) if x != b]
        seen = set(stack)
        while stack:
            x = stack.pop()
            for y in self.dep.get(x, ()):
                if y == b:
                    return True
                if y not in seen and y != a:
                    seen.add(y)
                    stack.append(y)
        return False


def anneal(g, plan, cfg, iters=ITERS, seed=SEED) -> list:
    """以 plan 为起点退火，返回代理最好的前 3 个不同方案（不含起点）。"""
    rng = random.Random(seed)
    mapping = {int(k): int(v) for k, v in plan['node_to_subgraph'].items()}
    st = _State(g, mapping, plan['core_schedules'], cfg)
    num_cores = len(st.sched)
    cur = st.estimate()
    start_hash = evaluate.plan_hash(st.plan())
    temp = 0.02 * cur
    decay = (1e-3) ** (1.0 / max(1, iters))
    top = []                                   # [(fitness, hash, plan)]

    def remember(val):
        if len(top) >= 3 and val >= top[-1][0]:
            return
        p = st.plan()
        h = evaluate.plan_hash(p)
        if h == start_hash or any(h == x[1] for x in top):
            return
        top.append((val, h, p))
        top.sort(key=lambda x: (x[0], x[1]))
        del top[3:]

    def try_move():
        """随机施加一个邻域操作；返回撤销函数，不可行则返回 None（已自动撤销）。"""
        kind = rng.randrange(3)
        snap = [list(o) for o in st.sched]
        moved = []
        if kind == 0:                                       # 合并
            cores = [k for k in range(num_cores) if len(st.sched[k]) >= 2]
            if not cores:
                return None
            k = rng.choice(cores)
            i = rng.randrange(len(st.sched[k]) - 1)
            a, b = st.sched[k][i], st.sched[k][i + 1]
            if st.reaches_via_others(a, b):
                return None
            ops = list(st.members[b])
            moved = [(v, b) for v in ops]
            st.move_ops(ops, a)
            st.sched[k].remove(b)
        elif kind == 1:                                     # 拆分
            tasks = [t for order in st.sched for t in order
                     if len(st.members[t]) >= 2]
            if not tasks:
                return None
            t = rng.choice(tasks)
            ops = sorted(st.members[t], key=st.topo_pos.__getitem__)
            second = ops[len(ops) // 2:]
            new = st.next_id
            st.next_id += 1
            moved = [(v, t) for v in second]
            st.move_ops(second, new)
            for order in st.sched:
                if t in order:
                    order.insert(order.index(t) + 1, new)
                    break
        else:                                               # 换核
            tasks = [t for order in st.sched for t in order]
            t = rng.choice(tasks)
            src = next(k for k, order in enumerate(st.sched) if t in order)
            if num_cores < 2:
                return None
            dst = rng.choice([k for k in range(num_cores) if k != src])
            st.sched[src].remove(t)
            st.sched[dst].append(t)
            st.sched[dst].sort(key=st.min_pos)

        def undo():
            groups = defaultdict(list)
            for v, old in moved:
                groups[old].append(v)
            for old, ops in groups.items():
                st.move_ops(ops, old)
            st.sched[:] = snap

        if not st.legal():
            undo()
            return None
        return undo

    for _ in range(iters):
        undo = None
        for _retry in range(20):
            undo = try_move()
            if undo is not None:
                break
        if undo is None:
            temp *= decay
            continue
        val = st.estimate()
        remember(val)
        delta = val - cur
        if delta <= 0 or (temp > 0 and rng.random() < math.exp(-delta / temp)):
            cur = val
        else:
            undo()
        temp *= decay
    return [p for _, _, p in top]
