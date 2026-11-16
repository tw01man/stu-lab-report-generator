from pathlib import Path
import shutil, pytest
from docx import Document
from docx.oxml.ns import qn
from lab_report.ingest import ingest_docx
from lab_report.models import Experiment, RunStyle, TableData
from lab_report.template import (clear_cell, clone_table, insert_paragraph_after,
                                 set_profile_line, set_title_line)
from lab_report.config import load_profile, load_template_config

from conftest import EXAMPLE_TEMPLATE_CONFIG, TEMPLATE, needs_template

@pytest.fixture
def tpl_doc(tmp_path):
    dst = tmp_path / "template.docx"
    shutil.copy(TEMPLATE, dst)
    return Document(dst)

@needs_template
def test_set_title_preserves_hei_ti_15(tpl_doc):
    cfg = load_template_config(EXAMPLE_TEMPLATE_CONFIG)
    set_title_line(tpl_doc, cfg, Experiment(number="三", title="晶体管单管放大器"))
    title = next(p for p in tpl_doc.paragraphs if p.text.startswith("实验三"))
    assert title.text == "实验三  晶体管单管放大器"
    assert title.runs[0].font.name == "黑体"
    assert title.runs[0].font.size.pt == 15.0

@needs_template
def test_profile_line_rebuilt(tpl_doc):
    set_profile_line(tpl_doc, load_profile(Path("profiles/example.json")),
                     load_template_config(EXAMPLE_TEMPLATE_CONFIG))
    line = next(p for p in tpl_doc.paragraphs if "学号" in p.text)
    assert all(s in line.text for s in ("某学院", "某专业", "张三", "2023000000"))

@needs_template
def test_clear_cell_removes_hint(tpl_doc):
    cell = tpl_doc.tables[2].rows[0].cells[0]
    assert "请分点列明" in cell.text
    clear_cell(cell)
    assert cell.text == ""

@needs_template
def test_insert_paragraph_after(tpl_doc):
    anchor = next(p for p in tpl_doc.paragraphs if p.text.strip() == "一、实验目的")
    insert_paragraph_after(anchor, "1、目的甲", RunStyle(font_name="宋体", size_pt=12))
    assert anchor._p.getnext().xpath("string(.)").strip() == "1、目的甲"

def test_unsupported_image_inserts_hint_instead_of_crashing():
    from lab_report.models import Figure
    from lab_report.template import UNSUPPORTED_IMAGE_HINT, add_picture_block
    doc = Document()
    cell = doc.add_table(rows=1, cols=1).cell(0, 0)
    fig = Figure(image_bytes=b"\xd7\xcd\xc6\x9a\x00\x00", ext="wmf")
    add_picture_block(cell, fig, doc)
    assert UNSUPPORTED_IMAGE_HINT in cell.text

def test_clone_table_preserves_text_merges_and_images(tmp_path, tiny_png):
    from io import BytesIO
    src = Document()
    src.add_paragraph("表1-1")
    t = src.add_table(rows=2, cols=2)
    t.cell(0, 0).merge(t.cell(0, 1))
    t.cell(0, 0).text = "合并表头"
    t.cell(1, 0).text = "Af=-10"
    t.cell(1, 1).paragraphs[0].add_run().add_picture(BytesIO(tiny_png))
    src_path = tmp_path / "src.docx"; src.save(src_path)
    table_data = [b for b in ingest_docx(src_path).blocks if b.kind == "table"][0].table

    dst = Document()
    cell = dst.add_table(rows=1, cols=1).cell(0, 0)
    cell._tc.append(clone_table(table_data, dst))
    text = cell._tc.xpath("string(.)")
    assert "合并表头" in text and "Af=-10" in text
    assert len(cell._tc.findall(".//" + qn("w:gridSpan"))) == 1
    blips = cell._tc.findall(".//" + qn("a:blip"))
    assert len(blips) == 1
    assert blips[0].get(qn("r:embed")) in dst.part.related_parts

def test_clone_table_from_rows():
    dst = Document()
    cell = dst.add_table(rows=1, cols=1).cell(0, 0)
    cell._tc.append(clone_table(TableData(element=None, media={}, rows=[["Ui", "Uo"], ["10mV", ""]]), dst))
    assert cell.tables[0].cell(0, 0).text == "Ui"
