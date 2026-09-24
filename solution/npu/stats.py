"""跨用例聚合的统计工具：算术/几何平均、bootstrap 区间、配对检验、Holm 校正。

口径约定（全文遵守）：赛题定义的平均加速比为**算术平均**；几何平均与中位数
只作为补充字段。所有统计量都只忽略 ``None`` 与非正数，不做其他剔除。
"""

from __future__ import annotations

import json
import math
import random
import statistics as st

from . import paths

SEED = 20260924


def _clean(xs):
    return [float(x) for x in xs if x is not None and x > 0]


def amean(xs) -> float:
    v = _clean(xs)
    if not v:
        return float('nan')
    return sum(v) / len(v)


def gmean(xs) -> float:
    v = _clean(xs)
    if not v:
        return float('nan')
    return math.exp(sum(math.log(x) for x in v) / len(v))


def _quantile(sorted_xs, q):
    """线性插值分位数（与 numpy.percentile 的默认方法一致）。"""
    n = len(sorted_xs)
    if n == 0:
        return float('nan')
    pos = (n - 1) * q
    lo = int(math.floor(pos))
    hi = min(lo + 1, n - 1)
    return sorted_xs[lo] + (sorted_xs[hi] - sorted_xs[lo]) * (pos - lo)


def bootstrap_ci(xs, stat='amean', n_boot=10000, alpha=0.05, seed=SEED):
    """对用例做有放回重采样，返回统计量的百分位区间 (lo, hi)。"""
    v = _clean(xs)
    if not v:
        return (float('nan'), float('nan'))
    fn = amean if stat == 'amean' else gmean
    rng = random.Random(seed)
    n = len(v)
    boots = sorted(fn(rng.choices(v, k=n)) for _ in range(n_boot))
    return (_quantile(boots, alpha / 2), _quantile(boots, 1 - alpha / 2))


def paired(a: dict, b: dict, tie=0.001) -> dict:
    """配对比较 a 与 b（键为 (case, n)，值为加速比），只用两者共有的键。"""
    keys = sorted(k for k in set(a) & set(b)
                  if a[k] is not None and b[k] is not None
                  and a[k] > 0 and b[k] > 0)
    win = tie_n = loss = 0
    diffs = []
    for k in keys:
        r = a[k] / b[k] - 1
        if r > tie:
            win += 1
        elif r < -tie:
            loss += 1
        else:
            tie_n += 1
        diffs.append(math.log(a[k]) - math.log(b[k]))
    mean_a = amean([a[k] for k in keys])
    mean_b = amean([b[k] for k in keys])
    if not diffs or all(d == 0 for d in diffs):
        p = 1.0
    else:
        from scipy.stats import wilcoxon
        try:
            p = float(wilcoxon(diffs, zero_method='wilcox').pvalue)
        except ValueError:
            p = 1.0
        if math.isnan(p):
            p = 1.0
    return {'n': len(keys), 'win': win, 'tie': tie_n, 'loss': loss,
            'mean_a': round(mean_a, 4) if keys else float('nan'),
            'mean_b': round(mean_b, 4) if keys else float('nan'),
            'rel': round(mean_a / mean_b - 1, 4) if keys else float('nan'),
            'p': p}


def holm(pvals: dict) -> dict:
    """Holm–Bonferroni 校正（step-down，保证单调，截断到 1）。"""
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(items)
    out, running = {}, 0.0
    for i, (name, p) in enumerate(items):
        adj = min(1.0, (m - i) * p)
        running = max(running, adj)
        out[name] = running
    return out


_FEATS = None


def _features() -> dict:
    global _FEATS
    if _FEATS is None:
        _FEATS = {f['case']: f for f in json.loads(
            (paths.RESULTS_DIR / 'features.json').read_text(encoding='utf-8'))}
    return _FEATS


STRATA = ('rho<0.2', '0.2<=rho<0.5', 'rho>=0.5')


def strata(case) -> str:
    """按最大连通分量占比 ρmax 分三层（阈值与论文表 10-2 一致）。"""
    rho = _features()[case]['largest_component_frac']
    if rho < 0.2:
        return STRATA[0]
    if rho < 0.5:
        return STRATA[1]
    return STRATA[2]


def describe(xs) -> dict:
    v = sorted(_clean(xs))
    if not v:
        nan = float('nan')
        return {'amean': nan, 'gmean': nan, 'median': nan, 'min': nan,
                'max': nan, 'p90': nan, 'n': 0, 'ci_lo': nan, 'ci_hi': nan}
    lo, hi = bootstrap_ci(v, 'amean')
    return {'amean': round(amean(v), 4), 'gmean': round(gmean(v), 4),
            'median': round(st.median(v), 4), 'min': round(v[0], 4),
            'max': round(v[-1], 4), 'p90': round(_quantile(v, 0.9), 4),
            'n': len(v), 'ci_lo': round(lo, 4), 'ci_hi': round(hi, 4)}
