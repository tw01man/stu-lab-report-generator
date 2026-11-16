from dataclasses import dataclass
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

from .config import TemplateConfig
from .ingest import VML_IMAGEDATA
from .models import Experiment
from .sections import normalize
from .template import TemplateError, find_after_heading


@dataclass
class ValidationIssue:
    code: str
    message: str


def _element_text(element) -> str:
    return element.xpath("string(.)")


def _slot_cell(doc, cfg: TemplateConfig, slot: str):
    spec = cfg.anchors[slot]
    anchor = find_after_heading(doc, spec.after_heading, spec.target)
    row, col = spec.cell or (0, 0)
    return anchor, anchor.rows[row].cells[col]


def _planned_figures(exp: Experiment) -> list:
    figures = []
    for block in list(exp.principle) + list(exp.steps):
        if getattr(block, "kind", None) == "figure":
            figures.append(block)
    return figures


def _count_images(doc) -> int:
    count = 0
    for element in doc.element.body.iter():
        if element.tag == qn("a:blip") or element.tag == VML_IMAGEDATA:
            count += 1
    return count


def _source_values(exp: Experiment) -> list[str]:
    values = []
    for block in list(exp.principle) + list(exp.steps):
        if getattr(block, "kind", None) != "table":
            continue
        table = getattr(block, "table", block)
        if table.element is not None:
            for node in table.element.iter(qn("w:t")):
                text = (node.text or "").strip()
                if len(text) >= 2 and text not in values:
                    values.append(text)
        for row in table.rows or []:
            for text in row:
                text = (text or "").strip()
                if len(text) >= 2 and text not in values:
                    values.append(text)
    return values


def validate_report(path: Path, cfg: TemplateConfig, exp: Experiment) -> list[ValidationIssue]:
    doc = Document(str(path))
    issues: list[ValidationIssue] = []
    all_text = _element_text(doc.element.body)

    if "实验X" in all_text:
        issues.append(ValidationIssue("title", "标题仍残留“实验X”，未替换为本次实验"))

    header_text = ""
    for section in doc.sections:
        header_text += _element_text(section.header._element)
    if "汕头大学实验报告" not in header_text:
        issues.append(ValidationIssue("header", "页眉未找到“汕头大学实验报告”"))

    if not doc.tables or "总评" not in _element_text(doc.tables[0]._tbl):
        issues.append(ValidationIssue("rubric", "评分表缺失或总评列不在首表"))

    if "请分点列明" in all_text:
        issues.append(ValidationIssue("hint", "模板提示语“请分点列明…”未被清除"))

    for slot, spec in cfg.anchors.items():
        try:
            find_after_heading(doc, spec.after_heading, spec.target)
        except TemplateError:
            issues.append(ValidationIssue("anchor", f"模板锚点缺失：{slot}（{spec.after_heading}）"))

    for slot in ("purpose", "equipment"):
        try:
            spec = cfg.anchors[slot]
            anchor = find_after_heading(doc, spec.after_heading, spec.target)
            if not anchor.text.strip():
                issues.append(ValidationIssue("slot", f"{slot} 槽位为空，且没有缺失标注"))
        except TemplateError:
            pass

    for slot in ("principle", "steps"):
        try:
            _, cell = _slot_cell(doc, cfg, slot)
            if not _element_text(cell._tc).strip():
                issues.append(ValidationIssue("slot", f"{slot} 槽位为空，且没有缺失标注"))
        except TemplateError:
            pass

    try:
        spec = cfg.anchors["results"]
        anchor = find_after_heading(doc, spec.after_heading, spec.target)
        table_text = _element_text(anchor._tbl)
        labels = spec.subsections.get("results", "1、实验结果"), spec.subsections.get(
            "questions", "2、思考题")
        missing_labels = [label for label in labels if normalize(label) not in normalize(table_text)]
        if missing_labels:
            issues.append(ValidationIssue(
                "slot", f"实验结果区缺少标签：{'、'.join(missing_labels)}"))
    except TemplateError:
        pass

    for figure in _planned_figures(exp):
        if not figure.caption.strip():
            issues.append(ValidationIssue("figure_caption", "有一个搬运的图片没有题注，请人工核对"))

    planned = len(_planned_figures(exp))
    actual = _count_images(doc)
    if actual < planned:
        issues.append(ValidationIssue("images", f"图片数量不足：计划 {planned}，实际 {actual}"))

    missing_values = [value for value in _source_values(exp) if value not in all_text]
    if missing_values:
        issues.append(ValidationIssue(
            "values", f"数据表原文内容缺失：{'、'.join(missing_values[:5])}"))

    return issues
