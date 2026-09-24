"""项目路径与官方固定配置的唯一来源。

所有脚本都从这里取路径，禁止在别处硬编码；官方 `data/config.txt` 通过官方
解析函数读取，保证与评估器使用完全相同的数值。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CODE_DIR = ROOT / 'code'
DATA_DIR = ROOT / 'data'
DOCS_DIR = ROOT / 'docs'
SOLUTION_DIR = ROOT / 'solution'
RESULTS_DIR = ROOT / 'results'
FIGURES_DIR = ROOT / 'figures'
PAPER_DIR = ROOT / 'paper'
CACHE_DIR = RESULTS_DIR / 'cache'
PLAN_DIR = RESULTS_DIR / 'plans'
CONFIG_PATH = DATA_DIR / 'config.txt'

for _d in (RESULTS_DIR, FIGURES_DIR, CACHE_DIR, PLAN_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# 官方评估脚本用绝对 import 互相引用，必须把 code/ 放进 sys.path。
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))


def case_path(case_id: str) -> Path:
    """`case_001` / `case_001.json` / 绝对路径 均可。"""
    p = Path(case_id)
    if p.is_file():
        return p
    if not str(case_id).endswith('.json'):
        case_id = str(case_id) + '.json'
    return DATA_DIR / case_id


def all_cases() -> list[str]:
    return sorted(p.stem for p in DATA_DIR.glob('case_*.json'))


_OFFICIAL = None
_OVERRIDE: dict = {}


def set_config_override(**kwargs):
    """**仅用于研究性敏感性实验**：覆盖部分硬件参数。

    正式比赛结果一律在空覆盖（即 data/config.txt 原值）下产生；
    任何使用覆盖的实验在结果文件中都带 `sensitivity` 标记。
    """
    global _OVERRIDE
    _OVERRIDE = dict(kwargs)


def clear_config_override():
    global _OVERRIDE
    _OVERRIDE = {}


def config_override() -> dict:
    return dict(_OVERRIDE)


def official_config() -> dict:
    """用官方解析器读取 config.txt，返回全部评估参数。"""
    global _OFFICIAL
    if _OFFICIAL is None:
        from evaluation_validation import read_evaluation_config
        from multicore_cut_evaluate_problem_1 import read_scene_a_config
        from multicore_cut_evaluate_problem_2 import read_scene_b_config
        from multicore_cut_evaluate_problem_3 import read_cache_config
        base = read_evaluation_config(str(CONFIG_PATH))
        cfg = {
            'capacity': base['capacity'],
            'bandwidth': base['bandwidth'],
            'L1': base['capacity']['L1'],
            'UB': base['capacity']['UB'],
        }
        cfg.update(read_scene_a_config(str(CONFIG_PATH)))
        cfg.update(read_scene_b_config(str(CONFIG_PATH)))
        cfg.update(read_cache_config(str(CONFIG_PATH)))
        _OFFICIAL = cfg
    cfg = dict(_OFFICIAL)
    if _OVERRIDE:
        cfg.update(_OVERRIDE)
        cfg['capacity'] = {'L1': cfg['L1'], 'UB': cfg['UB']}
    return cfg


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default
