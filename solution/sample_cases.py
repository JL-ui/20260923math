"""分层抽样：为子集实验（试点、粒度、敏感性、L2 专项）确定可复现的用例样本。

    python solution/sample_cases.py

分层依据为最大连通分量占比 ρmax（``stats.strata``，阈值与论文表 10-2 一致），
层内再按算子数 n_ops 升序等分为三档。结果写入 ``results/samples.json``。
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from npu import paths, stats                                    # noqa: E402

SEED = 20260924

# (序号 i, 键, 三层分配, 是否强制包含 n_ops 最大的 3 个用例)
SAMPLES = [
    (0, 'pilot20', (12, 2, 6), True),
    (1, 'study30', (18, 4, 8), False),
]

RULE = (
    '分层：按最大连通分量占比 ρmax 分为 rho<0.2 / 0.2<=rho<0.5 / rho>=0.5 三层；'
    '层内按 n_ops 升序（并列按用例名）等分为三档，档大小不整除时余数分给 n_ops 最大的一档。'
    '抽样：第 i 个样本使用独立的 random.Random(20260924 + i)；层内在三档间轮流抽取'
    '（第 k 次取第 k mod 3 档，该档已空则顺延到下一档），档内均匀无放回抽取。'
    'i=0 pilot20：三层按 12/2/6 分配；最后强制包含全体 n_ops 最大的 3 个用例，'
    '若不在样本内，替换同层中 n_ops 最小的已抽用例。'
    'i=1 study30：三层按 18/4/8 分配，不强制大图。'
    'i=2 l2_strata：由 T17.1 按 L2 收益分层填充。'
    '样本内用例按用例名升序存储。种子 20260924。'
)


def tiers(cases, feats):
    """层内按 n_ops 升序等分三档，余数并入最大档。"""
    ordered = sorted(cases, key=lambda c: (feats[c]['n_ops'], c))
    size = len(ordered) // 3
    return [ordered[:size], ordered[size:2 * size], ordered[2 * size:]]


def draw(strata_cases, feats, alloc, rng):
    picked = []
    for stratum, k in zip(stats.STRATA, alloc):
        pools = [list(t) for t in tiers(strata_cases[stratum], feats)]
        got = []
        for j in range(k):
            for step in range(3):
                pool = pools[(j + step) % 3]
                if pool:
                    got.append(pool.pop(rng.randrange(len(pool))))
                    break
        picked.extend(got)
    return picked


def force_largest(sample, all_cases, feats, count=3):
    largest = sorted(all_cases, key=lambda c: (-feats[c]['n_ops'], c))[:count]
    sample = list(sample)
    for big in largest:
        if big in sample:
            continue
        same = [c for c in sample
                if stats.strata(c) == stats.strata(big) and c not in largest]
        victim = min(same, key=lambda c: (feats[c]['n_ops'], c))
        sample[sample.index(victim)] = big
    return sample


def l2_gain_n4():
    """{case: P2 makespan / P3 makespan}：p3_compare.csv 中 N=4 的 _best 方案在
    两种评估下的 Makespan 之比（同一方案，纯 L2 收益）。"""
    import csv
    ms = {}
    with open(paths.RESULTS_DIR / 'p3_compare.csv', encoding='utf-8') as f:
        for r in csv.DictReader(f):
            if (r['num_cores'] == '4' and r['variant'] == '_best'
                    and r['feasible'] == 'True' and r['makespan']):
                ms[(r['case'], r['eval_problem'])] = float(r['makespan'])
    return {c: ms[(c, '2')] / ms[(c, '3')]
            for c, ep in list(ms) if ep == '2' and (c, '3') in ms}


def l2_strata():
    """>1.05 全取；1.01–1.05 抽 10（种子 20260926）；<=1.01 抽 10（种子 20260927）。"""
    gain = l2_gain_n4()
    hi = sorted(c for c, x in gain.items() if x > 1.05)
    mid = sorted(c for c, x in gain.items() if 1.01 < x <= 1.05)
    lo = sorted(c for c, x in gain.items() if x <= 1.01)
    pick_mid = random.Random(20260926).sample(mid, min(10, len(mid)))
    pick_lo = random.Random(20260927).sample(lo, min(10, len(lo)))
    print('l2 gain strata sizes: >1.05={} 1.01-1.05={} <=1.01={}'.format(
        len(hi), len(mid), len(lo)))
    return sorted(hi + pick_mid + pick_lo)


def main():
    feats = {f['case']: f for f in json.loads(
        (paths.RESULTS_DIR / 'features.json').read_text(encoding='utf-8'))}
    cases = [c for c in paths.all_cases() if c in feats]
    strata_cases = {s: [] for s in stats.STRATA}
    for c in cases:
        strata_cases[stats.strata(c)].append(c)

    path = paths.RESULTS_DIR / 'samples.json'
    out = {}
    for i, key, alloc, force in SAMPLES:
        rng = random.Random(SEED + i)
        sample = draw(strata_cases, feats, alloc, rng)
        if force:
            sample = force_largest(sample, cases, feats)
        out[key] = sorted(sample)
    out['l2_strata'] = l2_strata()         # T17.1：按 N=4 同方案 L2 收益分层
    out['rule'] = RULE
    # 纯 ASCII 输出：Windows 下不指定编码的 open() 也能读取
    path.write_text(json.dumps(out, ensure_ascii=True, indent=1) + '\n',
                    encoding='utf-8')
    for key in ('pilot20', 'study30', 'l2_strata'):
        print(key, len(out[key]), ' '.join(out[key]))
    print('samples ->', path)


if __name__ == '__main__':
    main()
