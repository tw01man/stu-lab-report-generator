from lxml import etree
from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.opc.packuri import PackURI
from docx.opc.part import Part
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from lab_report.ingest import ingest_docx
from lab_report.template import clone_table

V_NS = "urn:schemas-microsoft-com:vml"


def test_table_with_wmf_and_ole_media_clones_without_crashing(tmp_path):
    src = Document()
    table = src.add_table(rows=1, cols=1)
    paragraph = table.cell(0, 0).paragraphs[0]

    wmf = Part(PackURI("/word/media/image9.wmf"), "image/x-wmf",
               b"\xd7\xcd\xc6\x9a", src.part.package)
    wmf_rid = src.part.relate_to(wmf, RT.IMAGE)
    ole = Part(PackURI("/word/embeddings/oleObject1.bin"),
               "application/vnd.openxmlformats-officedocument.oleObject",
               b"\x00", src.part.package)
    ole_rid = src.part.relate_to(ole, RT.OLE_OBJECT)

    drawing = OxmlElement("w:drawing")
    blip = OxmlElement("a:blip")
    blip.set(qn("r:embed"), wmf_rid)
    drawing.append(blip)
    paragraph._p.append(drawing)

    pict = etree.SubElement(paragraph._p, qn("w:pict"))
    shape = etree.SubElement(pict, f"{{{V_NS}}}shape")
    imagedata = etree.SubElement(shape, f"{{{V_NS}}}imagedata")
    imagedata.set(qn("r:id"), ole_rid)

    src_path = tmp_path / "src.docx"
    src.save(src_path)
    table_data = [b for b in ingest_docx(src_path).blocks if b.kind == "table"][0].table

    clone = clone_table(table_data, Document())
    assert clone is not None
    assert not clone.findall(".//" + qn("a:blip"))
    assert not clone.findall(".//{%s}imagedata" % V_NS)
    assert table_data.media == {}
