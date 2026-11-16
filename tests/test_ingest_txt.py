import pytest
from lab_report.ingest import ingest_txt

def test_txt_lines_become_paragraphs(tmp_path):
    p = tmp_path / "g.txt"
    p.write_text("实验一  测试\n一、实验目的\n1、目的甲\n", encoding="utf-8")
    sd = ingest_txt(p)
    assert [b.text for b in sd.blocks] == ["实验一  测试", "一、实验目的", "1、目的甲"]
