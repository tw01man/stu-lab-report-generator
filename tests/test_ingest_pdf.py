from pathlib import Path
import pytest
import fitz
from lab_report.ingest import ingest_pdf

def test_pdf_text_image_and_table(tmp_path, tiny_png):
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "实验一 测试", fontname="china-s", fontsize=12)
    page.insert_image(fitz.Rect(300, 80, 350, 130), stream=tiny_png)
    for x in (72, 172, 272):
        page.draw_line((x, 160), (x, 220))
    for y in (160, 190, 220):
        page.draw_line((72, y), (272, y))
    page.insert_text((80, 180), "Ui", fontname="china-s", fontsize=10)
    page.insert_text((180, 180), "Uo", fontname="china-s", fontsize=10)
    page.insert_text((80, 210), "10mV", fontname="china-s", fontsize=10)
    path = tmp_path / "g.pdf"; pdf.save(path); pdf.close()
    sd = ingest_pdf(path)
    assert any(getattr(b, "text", "") == "实验一 测试" for b in sd.blocks)
    figures = [f for b in sd.blocks for f in getattr(b, "figures", [])]
    assert len(figures) == 1 and figures[0].image_bytes[:8] == b"\x89PNG\r\n\x1a\n"
    tables = [b for b in sd.blocks if b.kind == "table"]
    assert tables and "Ui" in tables[0].table.rows[0][0]

def test_pdf_line_text_marks_sub_and_superscripts():
    from lab_report.ingest import _pdf_line_text
    spans = [
        {"text": "U", "size": 12.0, "origin": (0, 100)},
        {"text": "CE", "size": 6.0, "origin": (7, 101.5)},
        {"text": "2", "size": 7.0, "origin": (15, 98.5)},
    ]
    assert _pdf_line_text(spans) == "U_{CE}^{2}"


def test_pdf_line_text_ignores_padding_spaces():
    from lab_report.ingest import _pdf_line_text
    spans = [
        {"text": "I", "size": 12.0, "origin": (0, 100)},
        {"text": " ", "size": 6.0, "origin": (5, 100)},
        {"text": "CCL", "size": 6.0, "origin": (7, 101.7)},
    ]
    assert _pdf_line_text(spans) == "I_{CCL}"


def test_pdf_line_text_keeps_mixed_size_body_text():
    from lab_report.ingest import _pdf_line_text
    spans = [
        {"text": "基本RS，其", "size": 10.5, "origin": (0, 100)},
        {"text": "R", "size": 12.6, "origin": (50, 101)},
        {"text": "、", "size": 10.5, "origin": (58, 100)},
        {"text": "S", "size": 13.0, "origin": (66, 101)},
        {"text": "端", "size": 10.5, "origin": (72, 100)},
    ]
    assert _pdf_line_text(spans) == "基本RS，其R、S端"


def test_pdf_subscript_spans_become_markers(tmp_path):
    pdf = fitz.open()
    page = pdf.new_page()
    parts = [("I", 12, 100), ("CCL", 6, 101.7), ("=", 12, 100),
             ("V", 12, 100), ("CC", 6, 101.7), ("I", 12, 100),
             ("CCL", 6, 101.7)]
    x = 72
    for text, size, y in parts:
        page.insert_text((x, y), text, fontname="helv", fontsize=size)
        x += 3 if size < 10 else 8
    path = tmp_path / "sub.pdf"
    pdf.save(path)
    pdf.close()
    sd = ingest_pdf(path)
    blob = "\n".join(b.text for b in sd.blocks if getattr(b, "text", ""))
    assert "I_{CCL}=V_{CC}I_{CCL}" in blob


def test_pdf_vertical_formula_becomes_single_line(tmp_path):
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "实验一 测试", fontname="china-s", fontsize=12)
    for index, part in enumerate(["N", "OL", "=", "I", "OL", "/", "I", "IL"]):
        page.insert_text((72, 100 + index * 16), part,
                         fontname="helv", fontsize=10)
    path = tmp_path / "formula.pdf"
    pdf.save(path)
    pdf.close()
    sd = ingest_pdf(path)
    texts = [b.text for b in sd.blocks if getattr(b, "text", "")]
    assert any("N_OL = I_OL / I_IL" in text for text in texts)
    fragments = {"N", "I", "OL", "IL", "=", "/"}
    assert not any(line.strip() in fragments
                   for text in texts for line in text.split("\n"))


def test_pdf_isolated_letter_line_is_dropped(tmp_path):
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "实验一 测试", fontname="china-s", fontsize=12)
    page.insert_text((72, 110), "I", fontname="helv", fontsize=10)
    page.insert_text((72, 140), "第一段正文", fontname="china-s", fontsize=12)
    path = tmp_path / "isolated.pdf"
    pdf.save(path)
    pdf.close()
    sd = ingest_pdf(path)
    lines = [line.strip() for block in sd.blocks
             if getattr(block, "text", "") for line in block.text.split("\n")]
    assert "I" not in lines
    assert "第一段正文" in "\n".join(lines)


def test_blocks_with_overlapping_geometry_are_grouped():
    from lab_report.ingest import _group_blocks
    entries = [
        ((90.0, 124.0, 200.7, 139.4), [], []),
        ((193.4, 141.1, 199.6, 148.8), [], []),
        ((155.4, 116.4, 284.8, 146.8), [], []),
    ]
    assert len(_group_blocks(entries)) == 1


def test_geometry_text_orders_scrambled_equation():
    from lab_report.ingest import _geometry_text
    spans = [
        {"text": "1", "size": 8, "origin": (118, 203), "bbox": (118, 201, 122, 205)},
        {"text": "n", "size": 8, "origin": (110, 203), "bbox": (110, 201, 114, 205)},
        {"text": "Q", "size": 14, "origin": (100, 200), "bbox": (100, 191, 110, 205)},
        {"text": "\uf02b", "size": 8, "origin": (114, 203), "bbox": (114, 201, 118, 205)},
        {"text": "\uf03d", "size": 14, "origin": (126, 200), "bbox": (126, 192, 134, 204)},
        {"text": "SQ", "size": 14, "origin": (136, 200), "bbox": (136, 192, 153, 204)},
        {"text": "n", "size": 8, "origin": (153, 203), "bbox": (153, 201, 157, 205)},
    ]
    assert _geometry_text(spans) == "Q_{n+1} = SQ_{n}"


def test_geometry_text_splits_side_by_side_equations():
    from lab_report.ingest import _geometry_text
    spans = [
        {"text": "Q", "size": 14, "origin": (100, 200), "bbox": (100, 191, 110, 205)},
        {"text": "n", "size": 8, "origin": (110, 203), "bbox": (110, 201, 114, 205)},
        {"text": "\uf02b", "size": 8, "origin": (114, 203), "bbox": (114, 201, 118, 205)},
        {"text": "1", "size": 8, "origin": (118, 203), "bbox": (118, 201, 122, 205)},
        {"text": "\uf03d", "size": 14, "origin": (126, 200), "bbox": (126, 192, 134, 204)},
        {"text": "S", "size": 14, "origin": (136, 200), "bbox": (136, 192, 144, 204)},
        {"text": "Q", "size": 14, "origin": (144, 200), "bbox": (144, 192, 154, 204)},
        {"text": "n", "size": 8, "origin": (154, 203), "bbox": (154, 201, 158, 205)},
        {"text": "Q", "size": 14, "origin": (220, 200), "bbox": (220, 191, 230, 205)},
        {"text": "n", "size": 8, "origin": (230, 203), "bbox": (230, 201, 234, 205)},
        {"text": "\uf02b", "size": 8, "origin": (234, 203), "bbox": (234, 201, 238, 205)},
        {"text": "1", "size": 8, "origin": (238, 203), "bbox": (238, 201, 242, 205)},
        {"text": "\uf03d", "size": 14, "origin": (246, 200), "bbox": (246, 192, 254, 204)},
        {"text": "R", "size": 14, "origin": (256, 200), "bbox": (256, 192, 264, 204)},
        {"text": "Q", "size": 14, "origin": (264, 200), "bbox": (264, 192, 274, 204)},
        {"text": "n", "size": 8, "origin": (274, 203), "bbox": (274, 201, 278, 205)},
    ]
    assert _geometry_text(spans) == "Q_{n+1} = SQ_{n}\nQ_{n+1} = RQ_{n}"


def test_geometry_text_merges_stacked_fraction():
    from lab_report.ingest import _geometry_text
    spans = [
        {"text": "N", "size": 12, "origin": (120, 200), "bbox": (120, 188, 128, 202)},
        {"text": "OL", "size": 7, "origin": (129, 203), "bbox": (129, 201, 138, 206)},
        {"text": "\uf03d", "size": 12, "origin": (150, 200), "bbox": (150, 192, 158, 204)},
        {"text": "I", "size": 12, "origin": (170, 190), "bbox": (170, 178, 175, 192)},
        {"text": "OL", "size": 7, "origin": (176, 193), "bbox": (176, 191, 186, 196)},
        {"text": "I", "size": 12, "origin": (170, 210), "bbox": (170, 198, 175, 212)},
        {"text": "IL", "size": 7, "origin": (176, 213), "bbox": (176, 211, 186, 216)},
        {"text": "，通常", "size": 10.5, "origin": (200, 200), "bbox": (200, 188, 236, 202)},
        {"text": "N", "size": 12, "origin": (240, 200), "bbox": (240, 188, 248, 202)},
        {"text": "OL", "size": 7, "origin": (249, 203), "bbox": (249, 201, 258, 206)},
        {"text": "≥8。", "size": 10.5, "origin": (264, 200), "bbox": (264, 188, 284, 202)},
    ]
    assert _geometry_text(spans) == "N_{OL} = I_{OL}/I_{IL}，通常 N_{OL} ≥8。"


def test_pdf_without_text_layer_raises(tmp_path, tiny_png):
    from lab_report.ingest import IngestError
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_image(fitz.Rect(72, 72, 172, 172), stream=tiny_png)
    path = tmp_path / "scan.pdf"; pdf.save(path); pdf.close()
    with pytest.raises(IngestError, match="OCR"):
        ingest_pdf(path)

def test_encrypted_pdf_raises(tmp_path):
    from lab_report.ingest import IngestError
    pdf = fitz.open()
    pdf.new_page().insert_text((72, 72), "secret")
    path = tmp_path / "locked.pdf"
    pdf.save(path, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="pw", owner_pw="pw")
    pdf.close()
    with pytest.raises(IngestError, match="加密"):
        ingest_pdf(path)
