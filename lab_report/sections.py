import re

from .figures import attach_figure_captions, is_table_caption
from .models import Experiment, ParaBlock, SourceDoc, TableBlock, TextBlock

ZERO_WIDTH = "​‌‍﻿"
EXPERIMENT_RE = re.compile(r"^实验\s*([一二三四五六七八九十百\d]+)\s+(\S.*)$")
SUBTITLE_RE = re.compile(r"^[（(].*实验[）)]$")
NUM_PREFIX_RE = re.compile(r"^\s*(?:\d+|[（(]\d+[)）])\s*[、.．)]?\s*")
HEADING_PREFIX_RE = re.compile(r"^(?:[一二三四五六七八九十百]+|\d+)\s*[、.．)]\s*")
CN_NUMBERS = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10, "百": 100,
}

_CN_HEADING_RE = re.compile(r"^[一二三四五六七八九十百]+\s*[、.．)]")
_ARABIC_HEADING_RE = re.compile(r"^\s*(?:\d+|[（(]\d+[)）])")
_ITEM_START_RE = re.compile(r"^\s*(?:\d+\s*[、.．)]|[（(]\d+[)）])")
_REFERENCE_NAMES = {
    "实验目的", "目的与要求", "实验原理", "实验仪器", "实验设备", "实验器材",
    "实验内容", "实验步骤", "注意事项", "预习要求", "报告要求", "实验要求",
    "思考题", "讨论题", "问答题", "课后习题", "习题", "思考与练习",
    "收获和体会",
}

HEADING_RULES = (
    (r"^(?:实验目的|目的与要求)", "purpose"),
    (r"^实验(?:仪器|设备|器材)", "equipment"),
    (r"^实验原理", "principle"),
    (r"^实验(?:内容|步骤|任务|方法)", "steps"),
    (r"^(?:实验|安全)?(?:注意事项|须知)[：:]?$", "guidance"),
    (r"^(?:实验)?(?:预习|报告)要求[：:]?$", "guidance"),
    (r"^实验要求[：:]?$", "guidance"),
    (r"^(?:思考题|讨论题|问答题|课后习题|习题|思考与练习)[：:]?$", "questions"),
)


class SectionError(Exception):
    pass


def normalize(text: str) -> str:
    for ch in ZERO_WIDTH:
        text = text.replace(ch, "")
    text = text.replace("　", " ")
    return re.sub(r"\s+", " ", text).strip()


def classify_heading(text: str) -> str | None:
    t = normalize(text)
    if not t or len(t) > 30:
        return None
    stripped = HEADING_PREFIX_RE.sub("", t)
    for pattern, slot in HEADING_RULES:
        if re.search(pattern, stripped):
            return slot
    return None


def split_experiments(doc: SourceDoc) -> list[tuple[str, str, int, int]]:
    starts = []
    for index, block in enumerate(doc.blocks):
        if isinstance(block, ParaBlock):
            match = EXPERIMENT_RE.match(normalize(block.text))
            if match:
                starts.append((match.group(1), match.group(2).strip(), index))
    result = []
    for position, (number, title, start) in enumerate(starts):
        end = starts[position + 1][2] if position + 1 < len(starts) else len(doc.blocks)
        result.append((number, title, start, end))
    return result


def _number_value(value: str) -> int | None:
    if value.isdigit():
        return int(value)
    if value in CN_NUMBERS:
        return CN_NUMBERS[value]
    return None


def _number_matches(number: str, selector: str) -> bool:
    if number == selector:
        return True
    left, right = _number_value(number), _number_value(selector)
    return left is not None and left == right


def _strip_number(text: str) -> str:
    return NUM_PREFIX_RE.sub("", text.strip()).strip()


def _embedded_heading(line: str) -> str | None:
    """识别与正文合并在一段里的章节标题。

    只接受中文序号标题或无序号标题；报告要求里的“1.实验目的”这类
    阿拉伯数字条目不能被误当成章节标题。
    """
    text = normalize(line)
    slot = classify_heading(text)
    if slot is None:
        return None
    if _CN_HEADING_RE.match(text):
        return slot
    if _ARABIC_HEADING_RE.match(text):
        return None
    return slot


def _is_reference_name(line: str) -> bool:
    return _strip_number(normalize(line)) in _REFERENCE_NAMES


def _append_question(lines: list[str], line: str) -> None:
    if lines and not _ITEM_START_RE.match(line):
        lines[-1] = f"{lines[-1]}\n{line}"
    else:
        lines.append(line)


def is_guidance_question(text: str, keywords: list[str]) -> bool:
    t = _strip_number(normalize(text))
    if not t:
        return False
    if t.endswith(("？", "?")):
        return True
    return any(t.startswith(keyword) for keyword in keywords)


def filter_questions(lines: list[str], keywords: list[str]) -> list[str]:
    return [line for line in lines if is_guidance_question(line, keywords)]


def detect_missing(exp: Experiment) -> list[str]:
    missing = []
    if not exp.purpose:
        missing.append("purpose")
    if not exp.equipment:
        missing.append("equipment")
    if not exp.principle:
        missing.append("principle")
    if not exp.steps:
        missing.append("steps")
    if not exp.questions:
        missing.append("questions")
    return missing


def _drop_table_captions(blocks: list) -> list:
    cleaned = []
    for index, block in enumerate(blocks):
        if (isinstance(block, TextBlock) and is_table_caption(block.text)
                and index + 1 < len(blocks) and blocks[index + 1].kind == "table"):
            continue
        cleaned.append(block)
    return cleaned


def parse_experiment(doc: SourceDoc, selector: str | None,
                     question_keywords: list[str]) -> Experiment:
    experiments = split_experiments(doc)
    if not experiments:
        raise SectionError("未找到任何实验标题")
    chosen = None
    if selector is None:
        chosen = experiments[0]
    else:
        sel = normalize(str(selector))
        if sel.startswith("实验"):
            sel = sel[2:].strip()
        for experiment in experiments:
            number, title, _, _ = experiment
            if _number_matches(number, sel) or (sel and sel in title):
                chosen = experiment
                break
        if chosen is None:
            titles = "；".join(f"实验{number} {title}" for number, title, _, _ in experiments)
            raise SectionError(f"未找到实验：{selector}；检测到：{titles}")

    number, title, start, end = chosen
    exp = Experiment(number=number, title=title)
    blocks = doc.blocks
    index = start + 1
    while (index < end and isinstance(blocks[index], ParaBlock)
           and not blocks[index].text.strip()):
        index += 1
    if (index < end and isinstance(blocks[index], ParaBlock)
            and SUBTITLE_RE.match(normalize(blocks[index].text))):
        exp.subtitle = normalize(blocks[index].text)
        index += 1

    current = None
    guidance_lines: list[str] = []
    verbatim_questions: list[str] = []
    slot_blocks = {"principle": [], "steps": []}

    for block in blocks[index:end]:
        if isinstance(block, ParaBlock):
            if not block.text.strip():
                if current in ("principle", "steps") and block.figures:
                    slot_blocks[current].extend(block.figures)
                continue
            pending_slot = None
            pending_text: list[str] = []
            pending_items: list[str] = []

            def flush_pending():
                nonlocal pending_slot, pending_text, pending_items
                if pending_slot in ("principle", "steps") and pending_text:
                    slot_blocks[pending_slot].append(
                        TextBlock(text="\n".join(pending_text), style=block.style))
                elif pending_slot in ("purpose", "equipment") and pending_items:
                    getattr(exp, pending_slot).extend(pending_items)
                pending_slot = None
                pending_text = []
                pending_items = []

            for raw_line in block.text.split("\n"):
                line = raw_line.strip()
                if not line:
                    continue
                if SUBTITLE_RE.match(normalize(line)):
                    if not exp.subtitle:
                        exp.subtitle = normalize(line)
                    continue
                heading = _embedded_heading(line)
                if heading:
                    flush_pending()
                    current = heading
                    continue
                if current in ("purpose", "equipment"):
                    if pending_slot != current:
                        flush_pending()
                        pending_slot = current
                    if _ITEM_START_RE.match(line) or not pending_items:
                        pending_items.append(_strip_number(line))
                    else:
                        pending_items[-1] = f"{pending_items[-1]}\n{line}"
                elif current in ("principle", "steps"):
                    if pending_slot != current:
                        flush_pending()
                        pending_slot = current
                    pending_text.append(line)
                elif current == "guidance":
                    if not _is_reference_name(line):
                        guidance_lines.append(line)
                elif current == "questions":
                    _append_question(verbatim_questions, line)
            flush_pending()
            if current in ("principle", "steps") and block.figures:
                slot_blocks[current].extend(block.figures)
        elif isinstance(block, TableBlock) and current in ("principle", "steps"):
            slot_blocks[current].append(block)

    for slot in ("principle", "steps"):
        setattr(exp, slot, attach_figure_captions(_drop_table_captions(slot_blocks[slot])))

    exp.questions = verbatim_questions + filter_questions(guidance_lines, question_keywords)
    exp.missing = detect_missing(exp)
    return exp
