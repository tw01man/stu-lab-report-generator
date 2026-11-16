import copy
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.image.image import Image
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from docx.table import Table
from docx.text.paragraph import Paragraph

from .config import REQUIRED_ANCHORS, Profile, TemplateConfig
from .formulas import latexify_text
from .ingest import paragraph_text
from .models import Experiment, Figure, RunStyle, TableData, TextBlock
from .omml import build_display_math_element, build_math_element
from .sections import normalize


class TemplateError(Exception):
    pass


def find_after_heading(doc, heading: str, target: str):
    found = False
    wanted = qn("w:tbl") if target == "next_table" else qn("w:p")
    for child in doc.element.body.iterchildren():
        if not found:
            if child.tag == qn("w:p") and normalize(paragraph_text(child)) == normalize(heading):
                found = True
            continue
        if child.tag == wanted:
            if wanted == qn("w:tbl"):
                return Table(child, doc)
            return Paragraph(child, doc)
    raise TemplateError(f"模板中找不到标题：{heading}")


def _heading_position(doc, heading: str) -> int | None:
    wanted = normalize(heading)
    for index, child in enumerate(doc.element.body.iterchildren()):
        if child.tag == qn("w:p") and normalize(paragraph_text(child)) == wanted:
            return index
    return None


def validate_anchor_order(doc, cfg: TemplateConfig) -> None:
    positions = []
    for name in REQUIRED_ANCHORS:
        heading = cfg.anchors[name].after_heading
        position = _heading_position(doc, heading)
        if position is None:
            raise TemplateError(f"模板中找不到标题：{heading}")
        positions.append(position)
    if any(later <= earlier for earlier, later in zip(positions, positions[1:])):
        expected = " → ".join(cfg.anchors[name].after_heading for name in REQUIRED_ANCHORS)
        raise TemplateError(f"模板章节顺序不正确，应依次为：{expected}")


def _apply_style(run, style: RunStyle) -> None:
    run.font.name = style.font_name
    run.font.size = Pt(style.size_pt)
    run.bold = style.bold
    rpr = run._element.get_or_add_rPr()
    rpr.get_or_add_rFonts().set(qn("w:eastAsia"), style.font_name)


_MATH_SEGMENT_RE = re.compile(r"(\$[^$\n]+\$)")
_PURE_MATH_RE = re.compile(r"^\s*\$([^$\n]+)\$\s*$")
_COURSE_TITLE_RE = re.compile(r"^\s*《[^》]*》\s*$")
_COURSE_RUBRIC_RE = re.compile(r"^(\s*)《[^》]*》(.*)$")


def _add_styled_run(paragraph, text: str, style: RunStyle) -> None:
    if text:
        _apply_style(paragraph.add_run(text), style)


def _append_inline_math(paragraph, latex: str) -> bool:
    element = build_math_element(latex)
    if element is None:
        return False
    paragraph._p.append(element)
    return True


def append_rich_text(paragraph, text: str, style: RunStyle) -> None:
    """把 $...$ 公式写成 Word 原生公式，其余文字仍为普通文本。"""
    stripped = text.strip()
    pure = _PURE_MATH_RE.match(stripped)
    if pure and "\n" not in stripped:
        element = build_display_math_element(pure.group(1))
        if element is not None:
            paragraph._p.append(element)
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            return
    for line_number, line in enumerate(text.split("\n")):
        if line_number:
            break_run = paragraph.add_run()
            _apply_style(break_run, style)
            break_run.add_break()
        for part in _MATH_SEGMENT_RE.split(line):
            if not part:
                continue
            if part.startswith("$") and part.endswith("$") and len(part) > 2:
                if not _append_inline_math(paragraph, part[1:-1]):
                    _add_styled_run(paragraph, part[1:-1], style)
            else:
                _add_styled_run(paragraph, part, style)


def _replace_paragraph_text(paragraph, text: str) -> None:
    if paragraph.runs:
        paragraph.runs[0].text = text
        for run in list(paragraph.runs[1:]):
            run._element.getparent().remove(run._element)
    else:
        paragraph.add_run(text)


def blank_course_title(doc) -> None:
    """把标题行和评分标准里的课程名清空为《》，保留原格式方便后续填写。"""
    for paragraph in doc.paragraphs:
        text = paragraph.text
        if _COURSE_TITLE_RE.match(text):
            _replace_paragraph_text(paragraph, "《》")
        elif "课程大纲评分标准" in text:
            replaced = _COURSE_RUBRIC_RE.sub(r"\g<1>《》\g<2>", text, count=1)
            if replaced != text:
                _replace_paragraph_text(paragraph, replaced)


def insert_paragraph_after(anchor: Paragraph, text: str, style: RunStyle) -> Paragraph:
    p = OxmlElement("w:p")
    anchor._p.addnext(p)
    paragraph = Paragraph(p, anchor._parent)
    _apply_style(paragraph.add_run(text), style)
    return paragraph


def set_title_line(doc, cfg: TemplateConfig, exp: Experiment) -> None:
    title = None
    for paragraph in doc.paragraphs:
        if re.fullmatch(cfg.title.pattern, paragraph.text):
            title = paragraph
            break
    if title is None:
        raise TemplateError("模板中找不到标题行（实验X XXXXXX）")
    text = f"实验{exp.number}  {exp.title}"
    if title.runs:
        title.runs[0].text = text
        for run in list(title.runs[1:]):
            run._element.getparent().remove(run._element)
    else:
        _apply_style(title.add_run(text), RunStyle(cfg.title.font_name, cfg.title.size_pt))
    if exp.subtitle:
        sub = insert_paragraph_after(title, exp.subtitle, RunStyle("宋体", 12))
        sub.alignment = WD_ALIGN_PARAGRAPH.CENTER


def set_profile_line(doc, profile: Profile, cfg: TemplateConfig) -> None:
    target = None
    for paragraph in doc.paragraphs:
        if "姓名" in paragraph.text and "学号" in paragraph.text:
            target = paragraph
            break
    if target is None:
        raise TemplateError("模板中找不到个人信息行")
    for run in list(target.runs):
        run._element.getparent().remove(run._element)
    values = {
        "name": profile.name,
        "student_id": profile.student_id,
        "department": profile.department,
        "major": profile.major,
    }
    separator = ""
    for field_name, label in cfg.profile_replace.items():
        if field_name not in values:
            continue
        if separator:
            _apply_style(target.add_run(separator), RunStyle("宋体", 12))
        _apply_style(target.add_run(label), RunStyle("宋体", 12, bold=True))
        _apply_style(target.add_run(values[field_name]), RunStyle("宋体", 12))
        separator = "  "


def clear_cell(cell) -> None:
    tc = cell._tc
    for child in list(tc):
        if child.tag != qn("w:tcPr"):
            tc.remove(child)
    tc.append(OxmlElement("w:p"))


def _set_single_borders(tbl) -> None:
    tbl_pr = tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        element = OxmlElement(f"w:{edge}")
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), "4")
        element.set(qn("w:space"), "0")
        element.set(qn("w:color"), "000000")
        borders.append(element)
    tbl_pr.append(borders)


_MEDIA_WRAPPERS = (qn("w:drawing"), qn("w:pict"), qn("w:object"))


def _drop_media_wrapper(element) -> None:
    node = element
    while node is not None and node.tag not in _MEDIA_WRAPPERS:
        node = node.getparent()
    target = node if node is not None else element
    parent = target.getparent()
    if parent is not None:
        parent.remove(target)


def clone_table(table: TableData, doc):
    if table.element is not None:
        clone = copy.deepcopy(table.element)
        slots = [(el, attr, el.get(attr)) for el in clone.iter()
                 for attr in (qn("r:embed"), qn("r:id"), qn("r:link"))]
        dropped = set()
        for element, attr, rid in slots:
            if rid not in table.media:
                continue
            if rid in dropped:
                _drop_media_wrapper(element)
                continue
            try:
                new_rid, _ = doc.part.get_or_add_image(BytesIO(table.media[rid]))
            except Exception:
                dropped.add(rid)
                print(f"警告：表格中有无法嵌入的图片，已跳过（{rid}）", file=sys.stderr)
                _drop_media_wrapper(element)
                continue
            element.set(attr, new_rid)
        return clone

    rows = table.rows or []
    cols = max((len(row) for row in rows), default=1)
    built = doc.add_table(rows=max(len(rows), 1), cols=cols)
    for row_index, row in enumerate(rows):
        for col_index in range(cols):
            built.cell(row_index, col_index).text = (
                row[col_index] if col_index < len(row) else "")
    try:
        built.style = "Table Grid"
    except (KeyError, ValueError):
        _set_single_borders(built._tbl)
    tbl = built._tbl
    tbl.getparent().remove(tbl)
    return tbl


def _cell_paragraph(cell) -> Paragraph:
    paragraphs = cell.paragraphs
    if len(paragraphs) == 1 and not paragraphs[0].text and not paragraphs[0].runs:
        return paragraphs[0]
    return cell.add_paragraph()


def add_picture_block(cell, fig: Figure, doc) -> Paragraph:
    paragraph = _cell_paragraph(cell)
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run()
    try:
        image = Image.from_blob(fig.image_bytes)
        width = Cm(14) if image.width > Cm(14) else image.width
        run.add_picture(BytesIO(fig.image_bytes), width=width)
    except Exception:
        print(f"警告：图片格式不支持，已插入文字提示（{fig.ext}）", file=sys.stderr)
        run.text = UNSUPPORTED_IMAGE_HINT
        _apply_style(run, RunStyle("宋体", 10.5))
        run.font.color.rgb = RGBColor(0x80, 0x80, 0x80)
    return paragraph


def append_blocks(cell, blocks: list, doc, cfg: TemplateConfig) -> None:
    for block in blocks:
        kind = getattr(block, "kind", None)
        if kind == "text":
            paragraph = _cell_paragraph(cell)
            append_rich_text(paragraph, latexify_text(block.text),
                             block.style or RunStyle())
        elif kind == "figure":
            add_picture_block(cell, block, doc)
            if block.caption:
                paragraph = _cell_paragraph(cell)
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                _apply_style(paragraph.add_run(block.caption), RunStyle("宋体", 10.5))
        elif kind == "table":
            table = getattr(block, "table", block)
            if getattr(table, "caption", ""):
                paragraph = _cell_paragraph(cell)
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                _apply_style(paragraph.add_run(table.caption), RunStyle("宋体", 10.5))
            cell._tc.append(clone_table(table, doc))


@dataclass
class FillOptions:
    table_placement: str = "preserve"
    blank_policy: str = "placeholder"


SLOT_LABELS = {
    "purpose": "实验目的",
    "equipment": "实验设备",
    "principle": "实验原理",
    "steps": "实验步骤",
    "questions": "思考题",
}
NUMBERED_RE = re.compile(r"^\s*(?:\d+|[一二三四五六七八九十]+)\s*[、.．)]")
SCREENSHOT_HINT = "（此处插入示波器截图）"
UNSUPPORTED_IMAGE_HINT = "[图片格式不支持，请手动补充]"


def _gray_paragraph(container, text: str, size_pt: float = 12.0):
    paragraph = container.add_paragraph() if hasattr(container, "add_paragraph") else container
    run = paragraph.add_run(text)
    _apply_style(run, RunStyle("宋体", size_pt))
    run.font.color.rgb = RGBColor(0x80, 0x80, 0x80)
    return paragraph


def _write_numbered_lines(doc, anchor: Paragraph, items: list[str]) -> None:
    target = anchor
    for run in list(anchor.runs):
        run._element.getparent().remove(run._element)
    for index, item in enumerate(items, start=1):
        if index == 1:
            _apply_style(target.add_run(f"{index}、"), RunStyle("宋体", 12))
        else:
            target = insert_paragraph_after(
                target, f"{index}、", RunStyle("宋体", 12))
        append_rich_text(target, latexify_text(item), RunStyle("宋体", 12))


def _fill_line_slot(doc, cfg: TemplateConfig, slot: str, items: list[str]) -> None:
    spec = cfg.anchors[slot]
    anchor = find_after_heading(doc, spec.after_heading, spec.target)
    if items:
        _write_numbered_lines(doc, anchor, items)
    else:
        for run in list(anchor.runs):
            run._element.getparent().remove(run._element)
        _apply_style(anchor.add_run(
            cfg.missing_text.format(slot=SLOT_LABELS[slot])), RunStyle("宋体", 12))
        anchor.runs[0].font.color.rgb = RGBColor(0x80, 0x80, 0x80)


def _number_steps(blocks: list) -> list:
    numbered = []
    count = 0
    for block in blocks:
        if block.kind == "text":
            count += 1
            if NUMBERED_RE.match(block.text.strip()):
                numbered.append(block)
            else:
                numbered.append(TextBlock(text=f"{count}、{block.text.strip()}",
                                          style=block.style))
        else:
            numbered.append(block)
    return numbered


def _place_tables(exp: Experiment, cfg: TemplateConfig, options: FillOptions):
    principle = list(exp.principle)
    steps = list(exp.steps)
    results: list = []

    def caption_of(block) -> str:
        data = getattr(block, "table", block)
        return getattr(data, "caption", "") or ""

    def destination(caption: str) -> str:
        override = cfg.tables.get(caption)
        if override:
            return override
        return "results" if options.table_placement == "results" else "steps"

    new_steps = []
    for block in steps:
        if block.kind == "table":
            dest = destination(caption_of(block))
            if dest == "results":
                results.append(block)
                continue
            if dest == "principle":
                principle.append(block)
                continue
        new_steps.append(block)
    new_principle = []
    for block in principle:
        if block.kind == "table" and cfg.tables.get(caption_of(block)) == "results":
            results.append(block)
        else:
            new_principle.append(block)
    return new_principle, new_steps, results


def _anchor_cell(anchor: Table, spec):
    row, col = spec.cell or (0, 0)
    return anchor.rows[row].cells[col]


def _fill_block_slot(doc, cfg: TemplateConfig, slot: str, blocks: list,
                     number_steps: bool = False) -> None:
    spec = cfg.anchors[slot]
    anchor = find_after_heading(doc, spec.after_heading, spec.target)
    cell = _anchor_cell(anchor, spec)
    clear_cell(cell)
    if number_steps:
        blocks = _number_steps(blocks)
    if not blocks:
        _gray_paragraph(cell, cfg.missing_text.format(slot=SLOT_LABELS[slot]))
        return
    append_blocks(cell, blocks, doc, cfg)


def _cell_containing(table: Table, label: str):
    seen = set()
    for row in table.rows:
        for cell in row.cells:
            key = id(cell._tc)
            if key in seen:
                continue
            seen.add(key)
            if normalize(label) in normalize(cell.text):
                return cell
    return None


def _strip_empty_after_label(cell, label: str) -> None:
    paragraphs = cell.paragraphs
    index = None
    for position, paragraph in enumerate(paragraphs):
        if normalize(label) in normalize(paragraph.text):
            index = position
            break
    if index is None:
        return
    for paragraph in paragraphs[index + 1:]:
        if paragraph.text.strip():
            break
        paragraph._p.getparent().remove(paragraph._p)


def _add_numbered_lines(cell, items: list[str]) -> None:
    for index, item in enumerate(items, start=1):
        paragraph = cell.add_paragraph()
        if not NUMBERED_RE.match(item.strip()):
            _apply_style(paragraph.add_run(f"{index}、"), RunStyle("宋体", 12))
        append_rich_text(paragraph, latexify_text(item), RunStyle("宋体", 12))


def _add_screenshot_placeholders(cell, cfg: TemplateConfig) -> None:
    for table in cell.tables:
        rows = table.rows
        if not rows:
            continue
        header = [row_cell.text for row_cell in rows[0].cells]
        matched = [index for index, text in enumerate(header)
                   if any(keyword in text for keyword in cfg.screenshot_columns)]
        if not matched:
            _gray_paragraph(cell, SCREENSHOT_HINT, 10.5)
            continue
        for column in matched:
            seen = set()
            for row_index in range(1, len(rows)):
                target = rows[row_index].cells[column]
                if id(target._tc) in seen:
                    continue
                seen.add(id(target._tc))
                if not target.text.strip():
                    paragraph = target.add_paragraph()
                    run = paragraph.add_run(SCREENSHOT_HINT)
                    _apply_style(run, RunStyle("宋体", 10.5))
                    run.font.color.rgb = RGBColor(0x80, 0x80, 0x80)


def _fill_results(doc, cfg: TemplateConfig, exp: Experiment, tables: list,
                  blank_policy: str) -> None:
    spec = cfg.anchors["results"]
    anchor = find_after_heading(doc, spec.after_heading, spec.target)
    results_label = spec.subsections.get("results", "1、实验结果")
    questions_label = spec.subsections.get("questions", "2、思考题")
    results_cell = _cell_containing(anchor, results_label)
    questions_cell = _cell_containing(anchor, questions_label)
    if results_cell is None or questions_cell is None:
        raise TemplateError("模板实验结果区缺少“1、实验结果”或“2、思考题”标签")

    _strip_empty_after_label(results_cell, results_label)
    _strip_empty_after_label(questions_cell, questions_label)
    if tables:
        append_blocks(results_cell, tables, doc, cfg)
        if blank_policy == "placeholder":
            _add_screenshot_placeholders(results_cell, cfg)

    if exp.questions:
        _add_numbered_lines(questions_cell, exp.questions)
    else:
        _gray_paragraph(questions_cell, "（指导书未列出思考题）")


ILLEGAL_FILENAME_CHARS = '<>:"/\\|?*'


def default_output_name(profile: Profile, exp: Experiment) -> str:
    title = re.sub(r"\s+", " ", exp.title).strip()
    for char in ILLEGAL_FILENAME_CHARS:
        title = title.replace(char, "_")
    return f"{profile.student_id} {profile.name} 实验{exp.number} {title}.docx"


def save_report(doc, out_dir: Path, profile: Profile, exp: Experiment) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / default_output_name(profile, exp)
    if target.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        candidate = out_dir / f"{target.stem}-{stamp}{target.suffix}"
        counter = 2
        while candidate.exists():
            candidate = out_dir / f"{target.stem}-{stamp}-{counter}{target.suffix}"
            counter += 1
        target = candidate
    try:
        doc.save(str(target))
    except PermissionError as exc:
        raise TemplateError("请关闭已在 WPS 中打开的报告文件后重试") from exc
    return target


def ensure_compatibility_mode(doc) -> None:
    """把文档升级到 Word 2013+ 兼容级别，避免 WPS/Office 弹兼容转换提示。"""
    settings = doc.settings.element
    compat = settings.find(qn("w:compat"))
    if compat is None:
        compat = OxmlElement("w:compat")
        settings.append(compat)
    for setting in compat.findall(qn("w:compatSetting")):
        if setting.get(qn("w:name")) == "compatibilityMode":
            setting.set(qn("w:val"), "15")
            return
    setting = OxmlElement("w:compatSetting")
    setting.set(qn("w:name"), "compatibilityMode")
    setting.set(qn("w:uri"), "http://schemas.microsoft.com/office/word")
    setting.set(qn("w:val"), "15")
    compat.append(setting)


def fill_report(template_path: Path, cfg: TemplateConfig, exp: Experiment,
                profile: Profile, options: FillOptions | None = None) -> Document:
    options = options or FillOptions()
    blank_policy = options.blank_policy or cfg.blank_policy
    doc = Document(str(template_path))
    ensure_compatibility_mode(doc)
    validate_anchor_order(doc, cfg)
    set_title_line(doc, cfg, exp)
    set_profile_line(doc, profile, cfg)
    if cfg.blank_course_title:
        blank_course_title(doc)

    _fill_line_slot(doc, cfg, "purpose", exp.purpose)
    _fill_line_slot(doc, cfg, "equipment", exp.equipment)

    principle, steps, result_tables = _place_tables(exp, cfg, options)
    _fill_block_slot(doc, cfg, "principle", principle)
    _fill_block_slot(doc, cfg, "steps", steps, number_steps=True)
    _fill_results(doc, cfg, exp, result_tables, blank_policy)

    if blank_policy == "placeholder":
        steps_cell = _anchor_cell(
            find_after_heading(doc, cfg.anchors["steps"].after_heading,
                               cfg.anchors["steps"].target),
            cfg.anchors["steps"])
        _add_screenshot_placeholders(steps_cell, cfg)

    return doc
