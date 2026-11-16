from pathlib import Path
import shutil, pytest
from docx import Document
from lab_report.template import TemplateError, find_after_heading

from conftest import EXAMPLE_TEMPLATE_CONFIG, TEMPLATE, needs_template

@pytest.fixture
def tpl(tmp_path):
    dst = tmp_path / "template.docx"
    shutil.copy(TEMPLATE, dst)
    return Document(dst)

@needs_template
def test_find_purpose_paragraph(tpl):
    p = find_after_heading(tpl, "一、实验目的", "next_paragraph")
    assert p.text == ""

@needs_template
def test_find_principle_table(tpl):
    t = find_after_heading(tpl, "1、实验原理描述", "next_table")
    assert len(t.rows) == 1 and len(t.columns) == 1

@needs_template
def test_missing_heading_raises(tpl):
    with pytest.raises(TemplateError, match="不存在的标题"):
        find_after_heading(tpl, "不存在的标题", "next_table")

@needs_template
def test_reordered_anchor_headings_raise(tmp_path):
    from lab_report.config import load_profile, load_template_config
    from lab_report.models import Experiment
    from lab_report.template import fill_report
    doc = Document(TEMPLATE)
    paragraphs = {p.text.strip(): p for p in doc.paragraphs}
    principle = paragraphs["1、实验原理描述"]._p
    steps = paragraphs["2、实验步骤（含实验仪器操作步骤）"]._p
    principle.addprevious(steps)
    swapped = tmp_path / "swapped.docx"
    doc.save(swapped)
    with pytest.raises(TemplateError, match="顺序"):
        fill_report(swapped, load_template_config(EXAMPLE_TEMPLATE_CONFIG),
                    Experiment(number="三", title="x"),
                    load_profile(Path("profiles/example.json")))
