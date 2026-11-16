from pathlib import Path
import pytest
from lab_report.config import (
    ConfigError, load_profile, load_template_config, resolve_profile_path,
    resolve_template_path)


def test_resolve_profile_path_prefers_local_override(tmp_path):
    default = tmp_path / "profile.json"
    local = tmp_path / "profile.local.json"
    default.write_text("{}", encoding="utf-8")
    local.write_text("{}", encoding="utf-8")
    assert resolve_profile_path(None, default, local) == local
    assert resolve_profile_path(str(default), default, local) == default


def test_resolve_profile_path_falls_back_to_default(tmp_path):
    default = tmp_path / "profile.json"
    local = tmp_path / "profile.local.json"
    default.write_text("{}", encoding="utf-8")
    assert resolve_profile_path(None, default, local) == default

def test_load_modian_template():
    cfg = load_template_config(Path("templates/模电.example.json"))
    assert cfg.name == "模拟电路设计"
    assert cfg.title.pattern == r"^实验X\s+XXXXXX$"
    assert cfg.title.font_name == "黑体" and cfg.title.size_pt == 15.0
    assert set(cfg.anchors) == {"purpose", "equipment", "principle", "steps", "results"}
    assert cfg.anchors["principle"].cell == (0, 0)
    assert cfg.anchors["results"].subsections["questions"] == "2、思考题"
    assert cfg.screenshot_columns == ["波形", "观察波形", "实测波形", "截图"]
    assert "讨论" in cfg.question_keywords

def test_missing_required_anchor_raises(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"name":"x","title":{"pattern":"X"},"anchors":{},"profile_replace":{}}', encoding="utf-8")
    with pytest.raises(ConfigError, match="purpose"):
        load_template_config(bad)

def test_profile_roundtrip():
    p = load_profile(Path("profiles/example.json"))
    assert (p.name, p.student_id, p.department, p.major) == (
        "张三", "2023000000", "某学院", "某专业")


def test_example_config_has_relative_template_path():
    cfg = load_template_config(Path("templates/模电.example.json"))
    assert cfg.template_docx == "实验报告模板.docx"


def test_missing_template_config_mentions_example(tmp_path):
    with pytest.raises(ConfigError, match="模电.example.json"):
        load_template_config(tmp_path / "模电.json")


def test_missing_profile_mentions_example(tmp_path):
    with pytest.raises(ConfigError, match="profiles/example.json"):
        load_profile(tmp_path / "profile.json")


def test_anchor_without_after_heading_raises_config_error(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(
        '{"name":"x","template_docx":"t.docx","anchors":{'
        '"purpose":{"target":"next_paragraph"},'
        '"equipment":{"after_heading":"二"},'
        '"principle":{"after_heading":"三"},'
        '"steps":{"after_heading":"四"},'
        '"results":{"after_heading":"五"}}}', encoding="utf-8")
    with pytest.raises(ConfigError, match="after_heading"):
        load_template_config(bad)


def test_bad_size_pt_raises_config_error(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(
        '{"name":"x","title":{"pattern":"X","size_pt":"大"},'
        '"template_docx":"t.docx","anchors":{'
        '"purpose":{"after_heading":"一"},'
        '"equipment":{"after_heading":"二"},'
        '"principle":{"after_heading":"三"},'
        '"steps":{"after_heading":"四"},'
        '"results":{"after_heading":"五"}}}', encoding="utf-8")
    with pytest.raises(ConfigError, match="size_pt"):
        load_template_config(bad)


def test_invalid_profile_json_raises_config_error(tmp_path):
    bad = tmp_path / "profile.json"
    bad.write_text('{"name":"张三",}', encoding="utf-8")
    with pytest.raises(ConfigError, match="JSON"):
        load_profile(bad)


def test_resolve_template_path_relative_to_config(tmp_path):
    cfg_dir = tmp_path / "templates"
    cfg_dir.mkdir()
    assert resolve_template_path(cfg_dir / "课.json", "模板.docx") == (
        cfg_dir / "模板.docx")
