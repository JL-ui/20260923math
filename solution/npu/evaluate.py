"""官方评估器封装 + 候选解评估缓存。

约定（全文遵守）：**任何论文中出现的 Makespan / 搬运量 / 命中率都来自
官方评估脚本**，本项目自己的解析模型只用于搜索内部的快速评价，绝不用于
汇报成绩。

缓存键 = (problem, case, solution_hash)；solution_hash 由
``node_to_subgraph`` 的规范化形式与 ``core_schedules`` 共同决定，因此
只要方案不变就不会重复调用评估器。
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import time
from pathlib import Path

from . import paths


# --------------------------------------------------------------------------
# 方案对象
# --------------------------------------------------------------------------

def make_plan(mapping: dict, core_schedules: list) -> dict:
    """生成官方格式的方案 JSON（键为十进制字符串）。"""
    return {
        'node_to_subgraph': {str(k): int(v) for k, v in sorted(mapping.items())},
        'core_schedules': [[int(s) for s in order] for order in core_schedules],
    }


def plan_hash(plan: dict) -> str:
    payload = json.dumps(
        {'m': sorted((int(k), int(v)) for k, v in plan['node_to_subgraph'].items()),
         'c': [list(map(int, order)) for order in plan['core_schedules']]},
        separators=(',', ':'))
    return hashlib.blake2b(payload.encode('utf-8'), digest_size=16).hexdigest()


def canonical_plan(plan: dict) -> dict:
    """把子图 id 重编号成"按核、按核内顺序"的连续编号。

    评估语义与编号无关，规范化后不同算法产生的同一方案会命中同一缓存。
    """
    remap, next_id = {}, 0
    schedules = []
    for order in plan['core_schedules']:
        new_order = []
        for sg in order:
            if sg not in remap:
                remap[sg] = next_id
                next_id += 1
            new_order.append(remap[sg])
        schedules.append(new_order)
    mapping = {int(k): remap[int(v)] for k, v in plan['node_to_subgraph'].items()}
    return make_plan(mapping, schedules)


# --------------------------------------------------------------------------
# 官方评估器调用
# --------------------------------------------------------------------------

_GRAPH_CACHE: dict = {}


def raw_graph(case: str) -> dict:
    if case not in _GRAPH_CACHE:
        _GRAPH_CACHE[case] = json.loads(
            paths.case_path(case).read_text(encoding='utf-8'))
    return _GRAPH_CACHE[case]


def _summarise(result: dict, problem: int, elapsed: float) -> dict:
    dm = result.get('data_movement_bytes', {})
    out = {
        'feasible': True,
        'makespan': int(result['makespan']),
        'num_cores': int(result['num_cores']),
        'added_copy_bytes': int(dm.get('added_copy_bytes', 0)),
        'scheduled_copy_bytes': int(dm.get('scheduled_copy_bytes', 0)),
        'partition_added_copy_bytes': int(dm.get('partition_added_copy_bytes', 0)),
        'spill_added_copy_bytes': int(dm.get('spill_added_copy_bytes', 0)),
        'original_graph_copy_bytes': int(dm.get('original_graph_copy_bytes', 0)),
        'cross_task_traffic': int(result.get('cross_task_traffic', 0)),
        'eval_seconds': round(elapsed, 3),
        'problem': problem,
        'error': '',
    }
    if problem == 3:
        cs = result.get('cache_stats', {})
        out.update({
            'cache_hit_rate': float(cs.get('hit_rate', 0.0)),
            'cache_hits': int(cs.get('hits', 0)),
            'cache_accesses': int(cs.get('accesses', 0)),
            'cache_hit_bytes': int(cs.get('hit_bytes', 0)),
            'cache_miss_bytes': int(cs.get('miss_bytes', 0)),
        })
    peaks = result.get('memory_peak_by_core', {})
    if peaks:
        out['l1_peak'] = max(int(v.get('L1', 0)) for v in peaks.values())
        out['ub_peak'] = max(int(v.get('UB', 0)) for v in peaks.values())
    return out


def evaluate_plan(problem: int, case: str, plan: dict, full: bool = False) -> dict:
    """直接调用官方评估函数（不经过 CLI，避免进程与磁盘开销）。"""
    cfg = paths.official_config()
    graph = raw_graph(case)
    t0 = time.perf_counter()
    buf_out, buf_err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
            if problem == 1:
                from multicore_cut_evaluate_problem_1 import evaluate_scene_a
                result = evaluate_scene_a(
                    graph, plan, bandwidth=cfg['bandwidth'], capacity=cfg['capacity'],
                    cross_core_wait=cfg['task_cross_core_wait_cycles'],
                    same_core_wait=cfg['task_same_core_wait_cycles'])
            elif problem == 2:
                from multicore_cut_evaluate_problem_2 import evaluate_scene_b
                result = evaluate_scene_b(
                    graph, plan, bandwidth=cfg['bandwidth'], capacity=cfg['capacity'],
                    cross_core_copy_delay=cfg['cross_core_copy_delay_cycles'])
            elif problem == 3:
                from multicore_cut_evaluate_problem_3 import evaluate_problem_3
                result = evaluate_problem_3(
                    graph, plan, bandwidth=cfg['bandwidth'], capacity=cfg['capacity'],
                    cross_core_copy_delay=cfg['cross_core_copy_delay_cycles'],
                    cache_capacity_bytes=cfg['cache_capacity_bytes'],
                    cache_bandwidth_bytes_per_cycle=cfg['cache_bandwidth_bytes_per_cycle'])
            else:
                raise ValueError('problem must be 1, 2 or 3')
    except Exception as exc:                                  # noqa: BLE001
        return {'feasible': False, 'makespan': None, 'problem': problem,
                'error': '{}: {}'.format(type(exc).__name__, str(exc)[:400]),
                'eval_seconds': round(time.perf_counter() - t0, 3)}
    summary = _summarise(result, problem, time.perf_counter() - t0)
    if full:
        summary['_result'] = result
    return summary


# --------------------------------------------------------------------------
# 单核基准（官方 singlecore_evaluate，用于加速比分母）
# --------------------------------------------------------------------------

def _override_tag() -> str:
    ov = paths.config_override()
    if not ov:
        return ''
    return '_' + hashlib.blake2b(
        json.dumps(ov, sort_keys=True).encode(), digest_size=5).hexdigest()


def singlecore_baseline(case: str) -> dict:
    cache_file = paths.CACHE_DIR / ('singlecore' + _override_tag()) / f'{case}.json'
    if cache_file.is_file():
        return json.loads(cache_file.read_text(encoding='utf-8'))
    cfg = paths.official_config()
    graph = raw_graph(case)
    from singlecore_evaluate import evaluate_singlecore
    t0 = time.perf_counter()
    buf_out, buf_err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
            result = evaluate_singlecore(
                graph, bandwidth=cfg['bandwidth'], capacity=cfg['capacity'],
                cross_core_wait=cfg['task_cross_core_wait_cycles'],
                same_core_wait=cfg['task_same_core_wait_cycles'])
        out = _summarise(result, 1, time.perf_counter() - t0)
    except Exception as exc:                                  # noqa: BLE001
        out = {'feasible': False, 'makespan': None,
               'error': '{}: {}'.format(type(exc).__name__, str(exc)[:400])}
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                          encoding='utf-8')
    return out


# --------------------------------------------------------------------------
# 带缓存的评估入口
# --------------------------------------------------------------------------

class EvalCache:
    """(problem, case) 粒度的磁盘缓存 + 进程内存缓存。"""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.mem: dict = {}
        self.dirty: set = set()

    def _file(self, problem: int, case: str) -> Path:
        d = paths.CACHE_DIR / 'p{}{}'.format(problem, _override_tag())
        d.mkdir(parents=True, exist_ok=True)
        return d / f'{case}.json'

    def _load(self, problem: int, case: str) -> dict:
        key = (problem, case, _override_tag())
        if key in self.mem:
            return self.mem[key]
        f = self._file(problem, case)
        data = {}
        if self.enabled and f.is_file():
            try:
                data = json.loads(f.read_text(encoding='utf-8'))
            except json.JSONDecodeError:
                data = {}
        self.mem[key] = data
        return data

    def get(self, problem: int, case: str, plan: dict):
        return self._load(problem, case).get(plan_hash(plan))

    def evaluate(self, problem: int, case: str, plan: dict) -> dict:
        plan = canonical_plan(plan)
        h = plan_hash(plan)
        table = self._load(problem, case)
        if self.enabled and h in table:
            hit = dict(table[h])
            hit['cached'] = True
            return hit
        out = evaluate_plan(problem, case, plan)
        out['cached'] = False
        table[h] = {k: v for k, v in out.items() if k != 'cached'}
        self.dirty.add((problem, case, _override_tag()))
        return out

    def flush(self):
        """原子写盘并与磁盘已有内容合并（多进程实验时避免互相覆盖）。"""
        if not self.enabled:
            return
        for problem, case, tag in sorted(self.dirty):
            f = self._file(problem, case)
            merged = {}
            if f.is_file():
                try:
                    merged = json.loads(f.read_text(encoding='utf-8'))
                except (json.JSONDecodeError, OSError):
                    merged = {}
            merged.update(self.mem[(problem, case, tag)])
            self.mem[(problem, case, tag)] = merged
            tmp = f.with_suffix('.json.tmp{}'.format(os.getpid()))
            try:
                tmp.write_text(json.dumps(merged, ensure_ascii=False),
                               encoding='utf-8')
                os.replace(tmp, f)
            except OSError:
                pass
        self.dirty.clear()


_DEFAULT_CACHE = None


def default_cache() -> EvalCache:
    global _DEFAULT_CACHE
    if _DEFAULT_CACHE is None:
        _DEFAULT_CACHE = EvalCache(
            enabled=os.environ.get('NPU_NO_CACHE') != '1')
    return _DEFAULT_CACHE
