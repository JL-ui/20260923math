"""trace 剖析：核内流水甘特图与"申请序阻塞"区间（T22 / E4）。

    python solution/trace_gantt.py

用例：case_003，以及 pilot20 中问题 2、N=4 冠军 spill_added_copy_bytes 最大的用例。
每个用例取三个方案：a_no_level、c0、final.csv 冠军；用官方 CLI 的 --trace-output
生成 trace JSON（写到临时目录，data/ 只读），画 0 号核四条流水的甘特图，并标出
"四条流水同时空闲而该核仍有未完成算子"的区间（即申请序 / 跨核等待造成的整核停顿）。
输出 figures/fig28_trace_<case>.png 与 results/trace_stall.json。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from npu import evaluate, experiment, paths, plots, variants      # noqa: E402

import matplotlib.pyplot as plt                                    # noqa: E402

PIPES = ('PIPE_MTE2', 'PIPE_MTE3', 'PIPE_M', 'PIPE_V')
PIPE_COLOR = {'PIPE_MTE2': '#c9a227', 'PIPE_MTE3': '#d1603d',
              'PIPE_M': '#3b6fb6', 'PIPE_V': '#4f9d69'}


def run_trace(case, plan, tag, tmp):
    plan_path = Path(tmp) / f'{case}_{tag}_plan.json'
    plan_path.write_text(json.dumps(plan), encoding='utf-8')
    trace = Path(tmp) / f'{case}_{tag}_trace.json'
    cmd = [sys.executable, str(paths.CODE_DIR / 'multicore_cut_evaluate_problem_2.py'),
           str(paths.case_path(case)), str(plan_path), '--config', str(paths.CONFIG_PATH),
           '-o', str(Path(tmp) / f'{case}_{tag}_res.json'),
           '--trace-output', str(trace),
           '--log-output', str(Path(tmp) / f'{case}_{tag}_log.txt')]
    subprocess.run(cmd, check=True, capture_output=True,
                   env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    return json.loads(trace.read_text(encoding='utf-8'))


def core_spans(trace):
    """{core: {pipe: [(start, end)]}}"""
    names = {}
    for ev in trace['traceEvents']:
        if ev.get('ph') == 'M' and ev.get('name') == 'thread_name':
            names[(ev['pid'], ev['tid'])] = ev['args']['name']
    out = {}
    for ev in trace['traceEvents']:
        if ev.get('ph') != 'X' or ev.get('cat') == 'SUBGRAPH':
            continue
        core = ev['pid'] - 1000
        pipe = names.get((ev['pid'], ev['tid']), ev.get('cat'))
        out.setdefault(core, {p: [] for p in PIPES})[pipe].append(
            (ev['ts'], ev['ts'] + ev['dur']))
    return out


def stalls(spans):
    """四条流水全部空闲、且该核仍有未完成算子的区间。"""
    iv = sorted(x for lst in spans.values() for x in lst)
    if not iv:
        return []
    end_all = max(e for _, e in iv)
    gaps, cur = [], 0
    for s, e in iv:
        if s > cur:
            gaps.append((cur, s))
        cur = max(cur, e)
    return [(a, b) for a, b in gaps if b <= end_all and b > a]


def main():
    samples = json.loads((paths.RESULTS_DIR / 'samples.json').read_text(encoding='utf-8'))
    final = {(r['case'], int(r['problem']), int(r['num_cores'])): r
             for r in plots.read_csv('final.csv')}
    pilot = [final[(c, 2, 4)] for c in samples['pilot20'] if (c, 2, 4) in final]
    spill_case = max(pilot, key=lambda r: (r['spill_added_copy_bytes'] or 0, r['case']))['case']
    cases = ['case_003'] + ([spill_case] if spill_case != 'case_003' else [])
    tmp = Path(tempfile.gettempdir()) / 'npu_trace_gantt'
    tmp.mkdir(parents=True, exist_ok=True)
    report = {}
    for case in cases:
        g = experiment.get_graph(case)
        champ = final[(case, 2, 4)]
        plans = [('a_no_level', variants.build(g, 'a_no_level', 2, 4)),
                 ('c0', variants.build(g, 'c0', 2, 4)),
                 ('champion ({})'.format(champ['variant']),
                  json.loads((paths.ROOT / champ['plan_path']).read_text(encoding='utf-8')))]
        fig, axes = plt.subplots(len(plans), 1, figsize=(11, 2.1 * len(plans)), sharex=False)
        report[case] = {}
        for ax, (tag, plan) in zip(axes, plans):
            trace = run_trace(case, plan, tag.split()[0], tmp)
            spans = core_spans(trace)
            total_stall = {k: sum(b - a for a, b in stalls(sp)) for k, sp in spans.items()}
            mk = trace['otherData']['makespan']
            report[case][tag] = {'makespan': mk,
                                 'stall_core0': total_stall.get(0, 0),
                                 'stall_all_cores': sum(total_stall.values()),
                                 'stall_by_core': total_stall}
            sp0 = spans.get(0, {p: [] for p in PIPES})
            for i, p in enumerate(PIPES):
                ax.broken_barh([(s, e - s) for s, e in sp0[p]], (i - 0.4, 0.8),
                               facecolors=PIPE_COLOR[p], linewidth=0)
            for a, b in stalls(sp0):
                ax.axvspan(a, b, color='#e03030', alpha=0.18, lw=0)
            ax.set_yticks(range(len(PIPES)))
            ax.set_yticklabels(PIPES, fontsize=7)
            ax.set_title('{}：makespan={:,}，0 号核整核停顿 {:,} cycle（红色）'.format(
                tag, mk, total_stall.get(0, 0)), fontsize=8.5)
            ax.grid(False)
        axes[-1].set_xlabel('cycle')
        fig.suptitle(f'{case}（问题 2，N=4）0 号核四条流水甘特图', fontsize=10)
        fig.tight_layout(rect=(0, 0, 1, 0.96))
        plots.save(fig, f'fig28_trace_{case}.png')
    (paths.RESULTS_DIR / 'trace_stall.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
