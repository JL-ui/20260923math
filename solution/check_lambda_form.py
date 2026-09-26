# 本程序及代码是在人工智能工具辅助下完成的。
# 人工智能工具：Claude Sonnet 5（型号 claude-sonnet-5）、Claude Opus 5.5（型号 claude-opus-5-5）
# 开发机构：Anthropic 公司
# 版本发布日期：Claude Sonnet 5 为 2026-06-30，Claude Opus 5.5 为 2026-09-22
"""论文 §5.4 的 (λ-1) 连通度写法与评估器 COPY 规则的一致性检验。

    python solution/check_lambda_form.py

切分相对原图新增的搬运量（不含核内换入换出）写成
    ΔB_cut = Σ_t w_t · s_t · (λ_t − 1)，
其中 λ_t 为张量 t 触及的核数；图输入张量 w=1，单生产核的中间张量 w=2，
图输出张量与多生产核张量按逐项规则另计。本脚本在若干最终方案上把这一写法与
``graphlib.scene_b_copy_bytes − graphlib.original_copy_bytes``（官方 COPY 规则的
逐条复刻，已由 check_traffic_model.py 对 300 组官方输出逐位核对）逐项比较。
全部一致打印 LAMBDA FORM OK。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from npu import experiment, graphlib, paths                      # noqa: E402

CASES = (('case_001', 4), ('case_010', 3), ('case_044', 5), ('case_020', 2))


def check(case, n):
    g = experiment.get_graph(case)
    plan = json.loads((paths.RESULTS_DIR / 'final_plans' / 'p2' / f'n{n}'
                       / f'{case}_multicore_res.json').read_text(encoding='utf-8'))
    mapping = {int(k): v for k, v in plan['node_to_subgraph'].items()}
    core_of_sub = {sg: k for k, o in enumerate(plan['core_schedules']) for sg in o}
    exact = (graphlib.scene_b_copy_bytes(g, mapping, core_of_sub)
             - graphlib.original_copy_bytes(g))
    formula = special = 0
    for tid in g.tensors:
        ps, cs = g.producers[tid], g.consumers[tid]
        if not ps and not cs:
            continue
        s = g.size(tid)
        P = {core_of_sub[mapping[o]] for o in ps}
        C = {core_of_sub[mapping[o]] for o in cs}
        lam = len(P | C)
        is_out = tid in g.graph_output_tensor
        if not ps:                                   # 图输入：w = 1
            formula += s * (lam - 1)
        elif len(P) == 1 and not is_out and cs:      # 单生产核中间张量：w = 2
            formula += 2 * s * (lam - 1)
        else:                                        # 图输出 / 多生产核：逐项规则
            special += 1
            tot = s * len(P) if (is_out or not cs) else 0
            tot += sum(2 * s * len(C - {sc}) for sc in P)
            formula += tot - (s if is_out else 0)    # 原图对图输出已有一次 COPY_OUT
    return exact, formula, special


def main():
    ok = True
    for case, n in CASES:
        exact, formula, special = check(case, n)
        print(case, 'N=%d' % n, 'exact', exact, 'formula', formula,
              'match', exact == formula, 'special tensors', special)
        ok = ok and exact == formula
    print('LAMBDA FORM OK' if ok else 'LAMBDA FORM MISMATCH')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
