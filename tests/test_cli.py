import json
from pathlib import Path

from lab_report.cli import main

from conftest import GUIDE, needs_assets

@needs_assets
def test_end_to_end_experiment_three(tmp_path):
    rc = main(["--guide", str(GUIDE), "--experiment", "3",
               "--template", "templates/模电.json",
               "--profile", "profiles/example.json", "--out", str(tmp_path)])
    assert rc == 0
    files = list(tmp_path.glob("2023000000 张三 实验三 *.docx"))
    assert len(files) == 1

@needs_assets
def test_empty_experiment_selects_first(tmp_path):
    rc = main(["--guide", str(GUIDE), "--experiment", "",
               "--template", "templates/模电.json",
               "--profile", "profiles/example.json", "--out", str(tmp_path)])
    assert rc == 0
    assert list(tmp_path.glob("*.docx"))

@needs_assets
def test_unknown_experiment_exits_nonzero(tmp_path, capsys):
    rc = main(["--guide", str(GUIDE), "--experiment", "99",
               "--template", "templates/模电.json",
               "--profile", "profiles/example.json", "--out", str(tmp_path)])
    assert rc == 1
    assert "实验三" in capsys.readouterr().err  # lists detected titles

def test_bad_input_path_exits_nonzero(tmp_path, capsys):
    rc = main(["--guide", str(tmp_path / "nope.pdf"),
               "--template", "templates/模电.example.json",
               "--profile", "profiles/example.json"])
    assert rc == 1 and "找不到" in capsys.readouterr().err


@needs_assets
def test_missing_template_docx_file_exits_nonzero(tmp_path, capsys):
    cfg = json.loads(Path("templates/模电.example.json").read_text(encoding="utf-8"))
    cfg["template_docx"] = "不存在的模板.docx"
    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    rc = main(["--guide", str(GUIDE), "--template", str(cfg_path),
               "--profile", "profiles/example.json", "--out", str(tmp_path)])
    assert rc == 1
    assert "模板" in capsys.readouterr().err


def test_default_profile_uses_generic_filename():
    from lab_report.cli import DEFAULT_PROFILE
    assert DEFAULT_PROFILE.name == "profile.json"
