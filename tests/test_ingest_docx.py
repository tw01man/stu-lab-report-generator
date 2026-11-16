from lab_report.ingest import ingest_docx, iter_image_rids, paragraph_text
from lxml import etree

def test_order_text_image_table_and_table_caption(sample_docx):
    sd = ingest_docx(sample_docx)
    kinds = [type(b).__name__ for b in sd.blocks]
    assert kinds == ["ParaBlock", "ParaBlock", "ParaBlock", "ParaBlock", "TableBlock"]
    assert sd.blocks[0].text == "实验一 测试"
    assert len(sd.blocks[2].figures) == 1
    assert sd.blocks[2].figures[0].image_bytes[:8] == b"\x89PNG\r\n\x1a\n"
    assert sd.blocks[4].table.caption == "表1-1"
    assert sd.blocks[4].table.element.tag.endswith("tbl")

def test_iter_image_rids_supports_drawing_and_vml():
    ns = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
          'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
          'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
          'xmlns:v="urn:schemas-microsoft-com:vml"')
    el = etree.fromstring(
        f'<w:p {ns}><w:r><w:drawing><a:blip r:embed="rId1"/></w:drawing>'
        f'<w:pict><v:shape><v:imagedata r:id="rId2"/></v:shape></w:pict></w:r></w:p>')
    assert iter_image_rids(el) == ["rId1", "rId2"]

def test_paragraph_text_includes_omml():
    ns = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
          'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"')
    el = etree.fromstring(f'<w:p {ns}><w:r><w:t>Au=</w:t></w:r><m:oMath><m:t>-βR</m:t></m:oMath></w:p>')
    assert paragraph_text(el) == "Au=-βR"
