from docx import Document
from lxml import etree

from lab_report.models import RunStyle
from lab_report.omml import build_display_math_element, latex_to_omml
from lab_report.template import append_rich_text


def test_latex_to_omml_fraction_and_subscript():
    xml = latex_to_omml(r"N_{OL} = \frac{I_{OL}}{I_{IL}}")
    assert xml is not None
    assert "<m:oMath" in xml
    for tag in ("<m:sSub>", "<m:f>", "<m:num>", "<m:den>"):
        assert tag in xml
    assert "$" not in xml


def test_latex_to_omml_returns_none_for_empty():
    assert latex_to_omml("") is None
    assert latex_to_omml("   ") is None


def test_display_wrapper_is_centered():
    element = build_display_math_element(r"Q_{n+1} = SQ_{n}")
    assert element is not None
    xml = etree.tostring(element, encoding="unicode")
    assert "oMathPara" in xml
    assert 'm:val="center"' in xml


def test_append_rich_text_mixes_text_and_math():
    doc = Document()
    paragraph = doc.add_paragraph()
    append_rich_text(
        paragraph,
        "负载电流，则 $N_{OL} = \\frac{I_{OL}}{I_{IL}}$，通常 $N_{OL} ≥ 8$。",
        RunStyle("宋体", 12))
    xml = paragraph._p.xml
    assert xml.count("<m:oMath") >= 2
    assert "<m:f>" in xml
    assert "$" not in paragraph._p.xpath("string(.)")
    assert "负载电流" in paragraph._p.xpath("string(.)")


def test_pure_formula_line_is_centered_display_math():
    doc = Document()
    paragraph = doc.add_paragraph()
    append_rich_text(paragraph, "$Q_{n+1} = SQ_{n}$", RunStyle("宋体", 12))
    xml = paragraph._p.xml
    assert "oMathPara" in xml
    assert 'm:val="center"' in xml
    assert "$" not in xml


def test_plain_chinese_stays_a_normal_run():
    doc = Document()
    paragraph = doc.add_paragraph()
    append_rich_text(paragraph, "一、实验目的：观察静态工作点。", RunStyle("宋体", 12))
    xml = paragraph._p.xml
    assert "oMath" not in xml
    assert "一、实验目的" in paragraph.text


def test_conversion_failure_falls_back_without_dollar_signs(monkeypatch):
    import lab_report.template as template

    monkeypatch.setattr(template, "build_math_element", lambda latex: None)
    monkeypatch.setattr(template, "build_display_math_element", lambda latex: None)
    doc = Document()
    paragraph = doc.add_paragraph()
    append_rich_text(paragraph, "$x_{1}$ 说明", RunStyle("宋体", 12))
    assert "oMath" not in paragraph._p.xml
    assert "$" not in paragraph.text
    assert "x_{1}" in paragraph.text
