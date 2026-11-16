from pathlib import Path
import pytest
from docx import Document
from lab_report.config import load_profile
from lab_report.models import Experiment
from lab_report.template import TemplateError, default_output_name, save_report

def test_default_name_sanitizes():
    prof = load_profile(Path("profiles/example.json"))
    name = default_output_name(prof, Experiment(number="三", title="放大器:测试/一"))
    assert name == "2023000000 张三 实验三 放大器_测试_一.docx"

def test_save_does_not_overwrite(tmp_path):
    prof = load_profile(Path("profiles/example.json"))
    exp = Experiment(number="三", title="放大器")
    first = save_report(Document(), tmp_path, prof, exp)
    second = save_report(Document(), tmp_path, prof, exp)
    assert first != second and second.exists()
    assert second.stem.startswith(first.stem)

def test_permission_error_is_explained(tmp_path, monkeypatch):
    prof = load_profile(Path("profiles/example.json"))
    exp = Experiment(number="三", title="放大器")
    doc = Document()
    monkeypatch.setattr(doc, "save", lambda p: (_ for _ in ()).throw(PermissionError()))
    with pytest.raises(TemplateError, match="关闭"):
        save_report(doc, tmp_path, prof, exp)
