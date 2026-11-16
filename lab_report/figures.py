import re

from .models import Figure, TextBlock

_FIGURE_CAPTION_RE = re.compile(r"^\s*图\s*\d+\s*[－—\-–]\s*\d+")
_TABLE_CAPTION_RE = re.compile(r"^\s*表\s*[\d一二三四五六七八九十]+\s*(?:[－—\-–]\s*\d+)?\s*$")


def is_figure_caption(text: str) -> bool:
    t = text.strip()
    if not t or len(t) > 40 or t.endswith("。"):
        return False
    match = _FIGURE_CAPTION_RE.match(t)
    if not match:
        return False
    rest = t[match.end():].lstrip()
    return not rest.startswith(("为", "所", "如", "中", "是"))


def is_table_caption(text: str) -> bool:
    t = text.strip()
    return bool(t) and len(t) <= 40 and bool(_TABLE_CAPTION_RE.match(t))


def _is_figure_label(block) -> bool:
    if not isinstance(block, TextBlock):
        return False
    t = re.sub(r"\s+", " ", block.text.strip())
    return (0 < len(t) <= 20
            and not is_figure_caption(t)
            and not t.endswith(("。", "；", "！", "？")))


def attach_figure_captions(blocks: list) -> list:
    result: list = []
    i = 0
    while i < len(blocks):
        block = blocks[i]
        if isinstance(block, TextBlock) and is_figure_caption(block.text):
            j = len(result) - 1
            while j >= 0 and _is_figure_label(result[j]):
                j -= 1
            if j >= 0 and isinstance(result[j], Figure):
                if not result[j].caption:
                    result[j].caption = block.text.strip()
                i += 1
                continue
            if i + 1 < len(blocks) and isinstance(blocks[i + 1], Figure):
                fig = blocks[i + 1]
                if not fig.caption:
                    fig.caption = block.text.strip()
                result.append(fig)
                i += 2
                continue
        result.append(block)
        i += 1
    return result
