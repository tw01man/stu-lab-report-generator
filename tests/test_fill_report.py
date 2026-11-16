from pathlib import Path
import shutil, pytest
from docx import Document
from lab_report.config import load_profile, load_template_config
from lab_report.models import Experiment, Figure, TableData, TextBlock
from lab_report.template import FillOptions, fill_report

from conftest import EXAMPLE_TEMPLATE_CONFIG, TEMPLATE, needs_template

def cell_text(cell):
    return cell._tc.xpath("string(.)")

def make_exp(tmp_path, tiny_png):
    from docx import Document as D
    d = D(); d.add_paragraph("表1-1"); t = d.add_table(rows=2, cols=2)
    t.cell(0, 0).text = "Ui"; t.cell(0, 1).text = "波形"
    t.cell(1, 0).text = "10mV"; t.cell(1, 1).text = ""
    p = tmp_path / "t.docx"; d.save(p)
    from lab_report.ingest import ingest_docx
    td = [b for b in ingest_docx(p).blocks if b.kind == "table"][0].table
    return Experiment(
        number="三", title="晶体管单管放大器", subtitle="（验证性实验）",
        purpose=["熟悉实验箱", "学习测量静态工作点"],
        equipment=["数字万用表", "示波器"],
        principle=[TextBlock(text="原理段落甲"), Figure(image_bytes=tiny_png, ext="png", caption="图3－1  电路")],
        steps=[TextBlock(text="步骤甲"), td],
        questions=["讨论静态工作点对波形的影响"],
        missing=[])

@needs_template
def test_fill_all_slots(tmp_path, tiny_png):
    exp = make_exp(tmp_path, tiny_png)
    doc = fill_report(TEMPLATE, load_template_config(EXAMPLE_TEMPLATE_CONFIG),
                      exp, load_profile(Path("profiles/example.json")))
    texts = "\n".join(p.text for p in doc.paragraphs)
    assert "实验三  晶体管单管放大器" in texts
    assert "（验证性实验）" in texts
    assert "1、熟悉实验箱" in texts and "2、学习测量静态工作点" in texts
    assert "1、数字万用表" in texts
    assert "请分点列明" not in texts
    assert "1、实验结果" in doc.tables[3].rows[0].cells[0].text
    assert "讨论静态工作点对波形的影响" in doc.tables[3].rows[1].cells[0].text
    steps_cell = doc.tables[2].rows[0].cells[0]
    assert "步骤甲" in cell_text(steps_cell) and "10mV" in cell_text(steps_cell)
    assert "（此处插入示波器截图）" in cell_text(steps_cell)
    assert "原理段落甲" in doc.tables[1].rows[0].cells[0].text

@needs_template
def test_formulas_are_written_as_native_equations(tmp_path, tiny_png):
    exp = make_exp(tmp_path, tiny_png)
    exp.principle[0] = TextBlock(text="N_OL = I_OL / I_IL")
    doc = fill_report(TEMPLATE, load_template_config(EXAMPLE_TEMPLATE_CONFIG),
                      exp, load_profile(Path("profiles/example.json")))
    principle_cell = doc.tables[1].rows[0].cells[0]
    xml = principle_cell._tc.xml
    assert "<m:oMath" in xml and "<m:f>" in xml and "<m:sSub>" in xml
    assert "$" not in cell_text(principle_cell)
    assert "N" in cell_text(principle_cell)


@needs_template
def test_course_title_left_blank_with_brackets(tmp_path, tiny_png):
    exp = make_exp(tmp_path, tiny_png)
    doc = fill_report(TEMPLATE, load_template_config(EXAMPLE_TEMPLATE_CONFIG),
                      exp, load_profile(Path("profiles/example.json")))
    texts = [p.text for p in doc.paragraphs]
    assert "《》" in texts
    assert "《》课程大纲评分标准：" in texts
    assert not any("模拟电路设计" in t for t in texts)


@needs_template
def test_course_title_kept_when_blanking_disabled(tmp_path, tiny_png):
    exp = make_exp(tmp_path, tiny_png)
    cfg = load_template_config(EXAMPLE_TEMPLATE_CONFIG)
    cfg.blank_course_title = False
    doc = fill_report(TEMPLATE, cfg, exp, load_profile(Path("profiles/example.json")))
    assert "《模拟电路设计》" in [p.text for p in doc.paragraphs]


@needs_template
def test_report_is_upgraded_to_modern_compatibility_mode(tmp_path, tiny_png):
    exp = make_exp(tmp_path, tiny_png)
    doc = fill_report(TEMPLATE, load_template_config(EXAMPLE_TEMPLATE_CONFIG),
                      exp, load_profile(Path("profiles/example.json")))
    value = doc.settings.element.xpath(
        "string(.//w:compatSetting[@w:name='compatibilityMode']/@w:val)")
    assert value == "15"


@needs_template
def test_missing_section_writes_marker(tmp_path, tiny_png):
    exp = make_exp(tmp_path, tiny_png); exp.principle = []; exp.missing = ["principle"]
    doc = fill_report(TEMPLATE, load_template_config(EXAMPLE_TEMPLATE_CONFIG),
                      exp, load_profile(Path("profiles/example.json")))
    assert "（指导书未提供实验原理，请自行补充）" in doc.tables[1].rows[0].cells[0].text

@needs_template
def test_tables_results_option_moves_tables(tmp_path, tiny_png):
    exp = make_exp(tmp_path, tiny_png)
    doc = fill_report(TEMPLATE, load_template_config(EXAMPLE_TEMPLATE_CONFIG),
                      exp, load_profile(Path("profiles/example.json")),
                      FillOptions(table_placement="results"))
    steps_cell = doc.tables[2].rows[0].cells[0]
    results_cell = doc.tables[3].rows[0].cells[0]
    assert "Ui" not in cell_text(steps_cell)
    assert "Ui" in cell_text(results_cell)

@needs_template
def test_table_override_moves_single_table(tmp_path, tiny_png):
    exp = make_exp(tmp_path, tiny_png)
    cfg = load_template_config(EXAMPLE_TEMPLATE_CONFIG)
    cfg.tables = {"表1-1": "results"}
    doc = fill_report(TEMPLATE, cfg, exp, load_profile(Path("profiles/example.json")))
    assert "Ui" not in cell_text(doc.tables[2].rows[0].cells[0])
    assert "Ui" in cell_text(doc.tables[3].rows[0].cells[0])
