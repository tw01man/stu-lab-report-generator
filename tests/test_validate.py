from pathlib import Path
import shutil, pytest
from docx import Document
from lab_report.config import load_profile, load_template_config
from lab_report.models import Experiment
from lab_report.template import FillOptions, fill_report
from lab_report.validate import validate_report

from conftest import EXAMPLE_TEMPLATE_CONFIG, TEMPLATE, needs_template

@needs_template
def test_generated_report_is_clean(tmp_path):
    exp = Experiment(number="三", title="放大",
                     purpose=["甲"], equipment=["乙"],
                     principle=[], steps=[], questions=[], missing=["principle", "steps", "questions"])
    doc = fill_report(TEMPLATE, load_template_config(EXAMPLE_TEMPLATE_CONFIG),
                      exp, load_profile(Path("profiles/example.json")))
    out = tmp_path / "r.docx"; doc.save(out)
    assert validate_report(out, load_template_config(EXAMPLE_TEMPLATE_CONFIG), exp) == []

def test_title_leftover_is_reported(tmp_path):
    doc = Document(); doc.add_paragraph("实验X  XXXXXX")
    out = tmp_path / "bad.docx"; doc.save(out)
    issues = validate_report(out, load_template_config(EXAMPLE_TEMPLATE_CONFIG),
                             Experiment(number="三", title="放大"))
    assert any(i.code == "title" for i in issues)
