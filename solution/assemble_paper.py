"""把论文各部分拼装成一份完整 Markdown，再填数字、再导出 Word。

    python solution/assemble_paper.py

流程：
    paper/论文.md（骨架，含 @@EXPERIMENTS@@ 标记）
      + paper/04_实验章节.md   -> 替换 @@EXPERIMENTS@@
      + paper/05_附录.md       -> 追加到参考文献之后
      + paper/tables/*.md      -> 替换 @@APPENDIX_P*@@
      -> paper/论文_完整.md
    再由 fill_paper.py 注入实验数字，md2docx.py 导出 Word。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from npu import paths                                            # noqa: E402

MAX_APPENDIX_ROWS = 100


def _table(path: Path, limit=MAX_APPENDIX_ROWS) -> str:
    if not path.is_file():
        return '（表格尚未生成，请先运行 `python solution/make_report.py`）'
    lines = path.read_text(encoding='utf-8').splitlines()
    if len(lines) > limit + 2:
        lines = lines[:limit + 2] + ['| … | 其余见 `{}` | | | | | | | | | | | |'
                                     .format(path.name)]
    return '\n'.join(lines)


def main():
    src = paths.PAPER_DIR / '论文.md'
    text = src.read_text(encoding='utf-8')

    exp = (paths.PAPER_DIR / '04_实验章节.md').read_text(encoding='utf-8')
    text = text.replace('@@EXPERIMENTS@@', exp.strip())

    appendix = (paths.PAPER_DIR / '05_附录.md').read_text(encoding='utf-8')
    for p in (1, 2, 3):
        appendix = appendix.replace(
            f'@@APPENDIX_P{p}@@',
            _table(paths.PAPER_DIR / 'tables' / f'appendix_problem{p}.md'))
    text = text.rstrip() + '\n\n---\n\n' + appendix.strip() + '\n'

    out = paths.PAPER_DIR / '论文_完整.md'
    out.write_text(text, encoding='utf-8')
    print('assembled ->', out, '({} 行)'.format(len(text.splitlines())))
    return out


if __name__ == '__main__':
    main()
