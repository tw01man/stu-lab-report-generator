from lab_report.figures import attach_figure_captions, is_figure_caption
from lab_report.models import Figure, TextBlock

def test_caption_variants():
    assert is_figure_caption("图3－1  共射极单管放大器实验电路")
    assert is_figure_caption("图2—1  MF368外形图")
    assert is_figure_caption("图 3-1 电路")
    assert not is_figure_caption("图3－1为电阻分压式工作点稳定单管放大器实验电路图。")

def test_caption_after_figure_merges():
    blocks = [Figure(image_bytes=b"x", ext="png"), TextBlock(text="图3－1  电路")]
    out = attach_figure_captions(blocks)
    assert len(out) == 1 and out[0].caption == "图3－1  电路"

def test_caption_before_figure_merges():
    blocks = [TextBlock(text="图3－2  失真波形"), Figure(image_bytes=b"x", ext="png")]
    out = attach_figure_captions(blocks)
    assert len(out) == 1 and out[0].caption == "图3－2  失真波形"
