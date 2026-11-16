import pytest
from lab_report.ingest import IngestError, prepare_doc

def test_doc_without_wps_raises_clear_error(tmp_path, monkeypatch):
    import lab_report.ingest as ing
    monkeypatch.setattr(ing, "_convert_doc_with_wps", lambda p: (_ for _ in ()).throw(IngestError("COM unavailable")))
    bad = tmp_path / "g.doc"; bad.write_bytes(b"\xd0\xcf\x11\xe0")
    with pytest.raises(IngestError, match="另存为 .docx"):
        prepare_doc(bad)
