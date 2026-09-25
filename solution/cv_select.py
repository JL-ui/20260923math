"""超参数过拟合检验：二折交叉验证（T20，只读 results/pool.csv，不评估）。

    python solution/cv_select.py

1. 用例按 paths.all_cases() 排序，偶数下标为折 A，奇数下标为折 B。
2. 候选组合：在折 A 上对主候选标签（c*、s*、sa*）做贪心前向选择，选 4 个；在折 B
   上用这 4 个取冠军，算术平均加速比与"折 B 上用全部标签"（即保底池冠军）比较，
   得折外损失；再交换 A、B。
3. block_cap 默认值：在折 A 上从 g_* 标签中选算术平均最好的 β，在折 B 上与默认
   0.35（主候选 c0 = {block_cap: 0.35}）比较；再交换。
每个问题单独做，配置 = (用例, N)，N=2..5。某配置在所选标签中都没有可行记录时
按单核（加速比 1.0）计。CV_LOSS = 全部问题、两折中折外损失的最大值。
输出 results/cv_select.json。
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from npu import paths, plots, stats                              # noqa: E402

N_SELECT = 4


def is_main(label):
    return ((label.startswith('c') and label[1:].isdigit())
            or (label.startswith('s') and label[1:].isdigit())
            or (label.startswith('sa') and label[2:].isdigit()))


def load(problem):
    """{(case, n): {label: speedup}}"""
    table = defaultdict(dict)
    for r in plots.read_csv('pool.csv'):
        if int(r['problem']) != problem or not r['feasible'] or not r['speedup']:
            continue
        table[(r['case'], int(r['num_cores']))][r['label']] = r['speedup']
    return table


def score(table, configs, labels):
    vals = []
    for key in configs:
        row = table.get(key, {})
        got = [row[l] for l in labels if l in row]
        vals.append(max(got) if got else 1.0)
    return stats.amean(vals)


def greedy(table, configs, pool_labels, k):
    chosen = []
    for _ in range(k):
        best = None
        for l in pool_labels:
            if l in chosen:
                continue
            s = score(table, configs, chosen + [l])
            if best is None or s > best[0] + 1e-12:
                best = (s, l)
        if best is None:
            break
        chosen.append(best[1])
    return chosen


def main():
    cases = paths.all_cases()
    fold = {'A': [c for i, c in enumerate(cases) if i % 2 == 0],
            'B': [c for i, c in enumerate(cases) if i % 2 == 1]}
    out = {'rule': __doc__.strip().splitlines()[0], 'problems': {}}
    losses = []
    for problem in (1, 2, 3):
        table = load(problem)
        all_labels = sorted({l for row in table.values() for l in row})
        main_labels = [l for l in all_labels if is_main(l)]
        g_labels = [l for l in all_labels if l.startswith('g_')]
        res = {}
        for train, test in (('A', 'B'), ('B', 'A')):
            tr = [k for k in table if k[0] in fold[train]]
            te = [k for k in table if k[0] in fold[test]]
            sel = greedy(table, tr, main_labels, N_SELECT)
            sel_te = score(table, te, sel)
            full_te = score(table, te, all_labels)
            loss = 1 - sel_te / full_te
            losses.append(loss)
            betas = {l: score(table, tr, [l]) for l in g_labels}
            best_beta = max(betas, key=lambda l: (betas[l], l)) if betas else None
            beta_te = score(table, te, [best_beta]) if best_beta else None
            default_te = score(table, te, ['c0'])
            res[f'train_{train}'] = {
                'selected': sel,
                'selected_mean_test': round(sel_te, 4),
                'all_labels_mean_test': round(full_te, 4),
                'out_of_fold_loss': round(loss, 4),
                'block_cap_train_means': {l: round(v, 4) for l, v in betas.items()},
                'block_cap_selected': best_beta,
                'block_cap_selected_mean_test': round(beta_te, 4) if beta_te else None,
                'block_cap_default_mean_test': round(default_te, 4),
                'block_cap_rel_vs_default': (round(beta_te / default_te - 1, 4)
                                             if beta_te else None),
                'configs_train': len(tr), 'configs_test': len(te)}
        out['problems'][f'problem{problem}'] = res
    out['cv_loss_max'] = round(max(losses), 4)
    (paths.RESULTS_DIR / 'cv_select.json').write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
