import base64
import os
from pathlib import Path

import pytest

from lab_report.config import (
    ConfigError, load_template_config, resolve_template_path)

LOCAL_TEMPLATE_CONFIG = Path("templates/模电.json")
EXAMPLE_TEMPLATE_CONFIG = Path("templates/模电.example.json")


def _local_template_path() -> Path:
    env = os.environ.get("LAB_REPORT_TEMPLATE")
    if env:
        return Path(env)
    if LOCAL_TEMPLATE_CONFIG.exists():
        try:
            cfg = load_template_config(LOCAL_TEMPLATE_CONFIG)
            return resolve_template_path(LOCAL_TEMPLATE_CONFIG, cfg.template_docx)
        except ConfigError:
            pass
    return Path("templates/实验报告模板.docx")


TEMPLATE = _local_template_path()
GUIDE = Path(os.environ.get("LAB_REPORT_GUIDE", "指导书.docx"))
DIGITAL_GUIDE = Path(os.environ.get(
    "LAB_REPORT_DIGITAL_GUIDE", "数字逻辑实验指导书.pdf"))
needs_template = pytest.mark.skipif(
    not TEMPLATE.exists(), reason="template not on this machine")
needs_assets = pytest.mark.skipif(
    not (GUIDE.exists() and TEMPLATE.exists()), reason="assets missing")
needs_guide = pytest.mark.skipif(
    not GUIDE.exists(), reason="guide not on this machine")
needs_digital_guide = pytest.mark.skipif(
    not DIGITAL_GUIDE.exists(), reason="digital guide not on this machine")

TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")

@pytest.fixture
def tiny_png():
    return TINY_PNG

@pytest.fixture
def sample_docx(tmp_path, tiny_png):
    from docx import Document
    from io import BytesIO
    doc = Document()
    doc.add_paragraph("实验一 测试")
    doc.add_paragraph("正文段落")
    p = doc.add_paragraph()
    p.add_run().add_picture(BytesIO(tiny_png))
    doc.add_paragraph("表1-1")
    t = doc.add_table(rows=2, cols=2)
    t.cell(0, 0).text = "A"; t.cell(0, 1).text = "B"
    path = tmp_path / "guide.docx"
    doc.save(path)
    return path
