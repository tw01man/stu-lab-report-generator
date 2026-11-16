from docx import Document
from lab_report.cli import main

from conftest import GUIDE, needs_assets

@needs_assets
def test_experiment_three_structure(tmp_path):
    assert main(["--guide", str(GUIDE), "--experiment", "3",
                 "--template", "templates/模电.json",
                 "--profile", "profiles/example.json", "--out", str(tmp_path)]) == 0
    out = next(tmp_path.glob("*.docx"))
    doc = Document(out)
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "实验三" in text and "晶体管单管放大器" in text
    assert "（验证性实验）" in text
    assert "1、实验结果" in doc.tables[3].rows[0].cells[0].text
    assert "2、思考题" in doc.tables[3].rows[1].cells[0].text
    assert "讨论" in doc.tables[3].rows[1].cells[0].text
    principle = doc.tables[1].rows[0].cells[0]
    assert len(principle._tc.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}blip")) >= 1
    steps = doc.tables[2].rows[0].cells[0]
    assert "请分点列明" not in steps.text
    assert len(steps.tables) >= 3

@needs_assets
def test_all_seven_experiments_generate(tmp_path):
    for number in range(1, 8):
        rc = main(["--guide", str(GUIDE), "--experiment", str(number),
                   "--template", "templates/模电.json",
                   "--profile", "profiles/example.json", "--out", str(tmp_path)])
        assert rc == 0, f"实验{number} 生成失败"
