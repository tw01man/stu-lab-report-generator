import copy
import re
import sys
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.text.run import Run

from .formulas import (is_isolated_letter, is_math_line,
                       normalize_formula_lines)
from .models import Figure, ParaBlock, RunStyle, SourceDoc, TableBlock, TableData


class IngestError(Exception):
    pass


TABLE_CAPTION_RE = re.compile(r"^表\s*[\d一二三四五六七八九十]+")
VML_NS = "urn:schemas-microsoft-com:vml"
VML_IMAGEDATA = f"{{{VML_NS}}}imagedata"
VML_SHAPE = f"{{{VML_NS}}}shape"

# Symbol-font private-use glyphs used by Word/WPS math in this PDF.
_PUA_GLYPHS = {
    "\uf028": "(", "\uf029": ")", "\uf02b": "+", "\uf02d": "-",
    "\uf02f": "/", "\uf03d": "=", "\uf0a3": "\u2264",
    "\uf0b1": "\u00b1", "\uf0b3": "\u2265", "\uf0b4": "\u00d7",
    "\uf0b8": "\u00f7", "\uf0b9": "\u2260", "\uf0bb": "\u2248",
}
_CJK_RE = re.compile(
    r"[\u3400-\u4dbf\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]")


def paragraph_text(p_el) -> str:
    parts = []
    for el in p_el.iter(qn("w:t"), qn("m:t")):
        parts.append(el.text or "")
    return "".join(parts)


def iter_image_rids(element) -> list[str]:
    rids: list[str] = []
    for el in element.iter():
        tag = el.tag
        if tag == qn("a:blip"):
            rid = el.get(qn("r:embed"))
            if rid:
                rids.append(rid)
        elif tag == VML_IMAGEDATA:
            rid = el.get(qn("r:id"))
            if rid:
                rids.append(rid)
        elif tag == VML_SHAPE:
            rid = el.get(qn("r:id"))
            if rid:
                rids.append(rid)
    return rids


def _run_style(p_el) -> RunStyle:
    r_els = p_el.findall(qn("w:r"))
    if not r_els:
        return RunStyle()
    run = Run(r_els[0], None)
    font = run.font
    east_asian = None
    rpr = r_els[0].find(qn("w:rPr"))
    if rpr is not None:
        rfonts = rpr.find(qn("w:rFonts"))
        if rfonts is not None:
            east_asian = rfonts.get(qn("w:eastAsia"))
    size_pt = font.size.pt if font.size is not None else 12.0
    return RunStyle(font_name=font.name or east_asian or "宋体",
                    size_pt=size_pt,
                    bold=bool(font.bold))


def _part_ext(part) -> str:
    return str(part.partname).rsplit(".", 1)[-1].lower()


def _resolve_figures(p_el, doc) -> list[Figure]:
    figures = []
    for order, rid in enumerate(iter_image_rids(p_el)):
        part = doc.part.related_parts.get(rid)
        if part is None:
            continue
        ext = _part_ext(part)
        if ext in ("wmf", "emf"):
            print(f"警告：跳过不支持的图片格式 {ext}（{part.partname}）", file=sys.stderr)
            continue
        figures.append(Figure(image_bytes=part.blob, ext=ext, order=order))
    return figures


_IMAGE_RID_TAGS = (
    (qn("a:blip"), qn("r:embed")),
    (VML_IMAGEDATA, qn("r:id")),
    (VML_SHAPE, qn("r:id")),
)
_MEDIA_WRAPPERS = (qn("w:drawing"), qn("w:pict"), qn("w:object"))


def _collect_media(element, doc_part) -> dict[str, bytes]:
    media: dict[str, bytes] = {}
    for el in element.iter():
        for tag, attr in _IMAGE_RID_TAGS:
            if el.tag != tag:
                continue
            rid = el.get(attr)
            if rid and rid not in media:
                part = doc_part.related_parts.get(rid)
                if part is not None and part.content_type.startswith("image/"):
                    media[rid] = part.blob
    return media


def _drop_media_wrapper(element) -> None:
    node = element
    while node is not None and node.tag not in _MEDIA_WRAPPERS:
        node = node.getparent()
    target = node if node is not None else element
    parent = target.getparent()
    if parent is not None:
        parent.remove(target)


def _prune_unsupported_media(element, doc_part) -> None:
    for el in list(element.iter()):
        for attr in (qn("r:embed"), qn("r:id"), qn("r:link")):
            rid = el.get(attr)
            if not rid:
                continue
            part = doc_part.related_parts.get(rid)
            if (part is None or not part.content_type.startswith("image/")
                    or _part_ext(part) in ("wmf", "emf")):
                print(f"警告：跳过表格中不支持的媒体 {rid}"
                      f"（{getattr(part, 'partname', '未知')}）", file=sys.stderr)
                _drop_media_wrapper(el)
            break


def ingest_docx(path: Path) -> SourceDoc:
    doc = Document(str(path))
    blocks = []
    last_text = ""
    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            text = paragraph_text(child)
            blocks.append(ParaBlock(text=text, style=_run_style(child),
                                    figures=_resolve_figures(child, doc)))
            if text.strip():
                last_text = text
        elif child.tag == qn("w:tbl"):
            caption = last_text.strip() if TABLE_CAPTION_RE.match(last_text.strip()) else ""
            element = copy.deepcopy(child)
            _prune_unsupported_media(element, doc.part)
            blocks.append(TableBlock(table=TableData(
                element=element,
                media=_collect_media(element, doc.part),
                caption=caption)))
    return SourceDoc(blocks=blocks, path=Path(path))


def _pdf_style(span: dict) -> RunStyle:
    font = span.get("font", "") or "宋体"
    if "+" in font:
        font = font.split("+", 1)[1]
    try:
        size_pt = float(span.get("size", 12.0))
    except (TypeError, ValueError):
        size_pt = 12.0
    return RunStyle(font_name=font, size_pt=size_pt,
                    bold=bool(span.get("flags", 0) & 16))


def _pdf_line_text(spans: list[dict]) -> str:
    """Rebuild a line, encoding smaller lowered/raised spans as _{} / ^{}."""
    parts: list[str] = []
    mode: str | None = None
    buffer: list[str] = []
    base_size: float | None = None
    base_y = 0.0

    def flush() -> None:
        nonlocal mode, buffer
        if mode == "sub" and buffer:
            parts.append("_{" + "".join(buffer) + "}")
        elif mode == "sup" and buffer:
            parts.append("^{" + "".join(buffer) + "}")
        buffer = []
        mode = None

    for span in spans:
        text = span.get("text", "")
        if not text.strip():
            continue
        size = float(span.get("size") or 0) or (base_size or 12.0)
        origin = span.get("origin") or (0.0, 0.0)
        y = float(origin[1]) if len(origin) > 1 else 0.0
        if base_size is None:
            base_size, base_y = size, y
        tolerance = max(0.8, base_size * 0.08)
        small = size < base_size * 0.85 and not _CJK_RE.search(text)
        if small and y > base_y + tolerance:
            if mode != "sub":
                flush()
                mode = "sub"
            buffer.append(text)
        elif small and y < base_y - tolerance:
            if mode != "sup":
                flush()
                mode = "sup"
            buffer.append(text)
        else:
            flush()
            parts.append(text)
    flush()
    return "".join(parts)


def _map_glyphs(text: str) -> str:
    return "".join(_PUA_GLYPHS.get(ch, ch) for ch in text)


def _span_size(span: dict) -> float:
    try:
        return float(span.get("size") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _span_pos(span: dict) -> tuple[float, float, tuple]:
    origin = span.get("origin") or (0.0, 0.0)
    x = float(origin[0]) if len(origin) > 0 else 0.0
    y = float(origin[1]) if len(origin) > 1 else 0.0
    bbox = span.get("bbox") or (x, y, x, y)
    return x, y, tuple(float(value) for value in bbox)


def _has_math_glyph(spans) -> bool:
    return any(ch in _PUA_GLYPHS for span in spans
               for ch in (span.get("text") or ""))


def _union_bbox(boxes: list[tuple]) -> tuple:
    return (min(box[0] for box in boxes), min(box[1] for box in boxes),
            max(box[2] for box in boxes), max(box[3] for box in boxes))


def _blocks_touch(left: tuple, right: tuple) -> bool:
    overlap = min(left[3], right[3]) - max(left[1], right[1])
    smallest = min(left[3] - left[1], right[3] - right[1])
    horizontal_gap = max(left[0] - right[2], right[0] - left[2])
    return overlap > 0.5 * max(1.0, smallest) and horizontal_gap <= 10.0


def _group_blocks(entries: list) -> list[list]:
    """Merge blocks that occupy the same visual line (fragment repair)."""
    groups = [[entry] for entry in entries]
    merged = True
    while merged:
        merged = False
        for left in range(len(groups)):
            for right in range(left + 1, len(groups)):
                box_left = _union_bbox([entry[0] for entry in groups[left]])
                box_right = _union_bbox([entry[0] for entry in groups[right]])
                if _blocks_touch(box_left, box_right):
                    groups[left].extend(groups.pop(right))
                    merged = True
                    break
            if merged:
                break
    groups.sort(key=lambda group: _union_bbox([e[0] for e in group])[1])
    return groups


def _cluster_rows(items: list[dict], tolerance: float) -> list[dict]:
    rows: list[dict] = []
    for item in sorted(items, key=lambda i: (i["y"], i["x"])):
        for row in rows:
            if abs(row["y"] - item["y"]) <= tolerance:
                row["items"].append(item)
                break
        else:
            rows.append({"y": item["y"], "items": [item]})
    for row in rows:
        row["items"].sort(key=lambda i: i["x"])
    rows.sort(key=lambda row: row["y"])
    return rows


def _starts_cjk(text: str) -> bool:
    stripped = text.lstrip()
    return bool(stripped) and bool(_CJK_RE.match(stripped[0]))


def _join_pieces(pieces: list[dict], base_size: float) -> str:
    output: list[str] = []
    previous_right = None
    for piece in pieces:
        if output and previous_right is not None:
            gap = piece["x0"] - previous_right
            if gap > max(1.0, base_size * 0.12) and not _starts_cjk(piece["text"]):
                output.append(" ")
        output.append(piece["text"])
        previous_right = piece["x1"]
    return "".join(output).strip()


def _row_lines(pieces: list[dict], base_size: float) -> list[str]:
    segments: list[list[dict]] = []
    current: list[dict] = []
    previous_right = None
    threshold = max(base_size * 1.2, 12.0)
    for piece in pieces:
        if (current and previous_right is not None
                and piece["x0"] - previous_right > threshold):
            segments.append(current)
            current = []
        current.append(piece)
        previous_right = piece["x1"]
    if current:
        segments.append(current)
    return [_join_pieces(segment, base_size) for segment in segments]


def _fraction_slot(pieces: list[dict], x0: float, x1: float):
    for index in range(len(pieces) + 1):
        left = pieces[index - 1]["x1"] if index > 0 else float("-inf")
        right = pieces[index]["x0"] if index < len(pieces) else float("inf")
        if left <= x0 + 1.0 and right >= x1 - 1.0:
            return index
    return None


def _geometry_text(spans) -> str:
    """Rebuild scrambled math blocks from span coordinates.

    PyMuPDF emits stacked fractions and single-row equations in arbitrary
    block/line order, so rows, sub/superscripts and fractions are rebuilt
    from x/y geometry instead.
    """
    items = []
    for span in spans:
        text = _map_glyphs(span.get("text") or "")
        if not text.strip():
            continue
        x, y, bbox = _span_pos(span)
        items.append({"text": text, "x": x, "y": y, "bbox": bbox,
                      "size": _span_size(span),
                      "cjk": bool(_CJK_RE.search(text))})
    if not items:
        return ""
    base_size = max((item["size"] for item in items), default=0.0) or 12.0
    for item in items:
        if item["size"] <= 0:
            item["size"] = base_size
    base_size = max(item["size"] for item in items)
    small_limit = base_size * 0.85
    row_tolerance = max(2.0, base_size * 0.45)
    for item in items:
        item["small"] = item["size"] < small_limit and not item["cjk"]

    rows = _cluster_rows([item for item in items if not item["small"]],
                         row_tolerance)
    for item in items:
        if not item["small"]:
            continue
        row = min(rows, key=lambda r: abs(r["y"] - item["y"]))
        left = [base for base in row["items"]
                if base["bbox"][0] <= item["x"] + 1.0]
        base = min(left or row["items"],
                   key=lambda b: abs(item["x"] - b["bbox"][2]))
        key = "subs" if item["y"] >= row["y"] else "sups"
        base.setdefault(key, []).append(item)

    rows_data = []
    for row in rows:
        pieces = []
        for base in row["items"]:
            text = base["text"]
            subs = sorted(base.get("subs", []), key=lambda s: s["x"])
            sups = sorted(base.get("sups", []), key=lambda s: s["x"])
            if subs:
                text += "_{" + "".join(s["text"] for s in subs) + "}"
            if sups:
                text += "^{" + "".join(s["text"] for s in sups) + "}"
            right = base["bbox"][2]
            for small in subs + sups:
                right = max(right, small["bbox"][2])
            pieces.append({"x0": base["bbox"][0], "x1": right, "text": text})
        pieces.sort(key=lambda p: p["x0"])
        rows_data.append({"y": row["y"], "pieces": pieces,
                          "x0": pieces[0]["x0"],
                          "x1": max(p["x1"] for p in pieces)})
    if not rows_data:
        return ""

    def row_text(row: dict) -> str:
        return _join_pieces(row["pieces"], base_size)

    max_width = max(row["x1"] - row["x0"] for row in rows_data)
    main_rows = [row for row in rows_data
                 if row["x1"] - row["x0"] >= 0.6 * max_width]
    consumed = set()
    for main in main_rows:
        width = main["x1"] - main["x0"]
        candidates = [row for row in rows_data
                      if row is not main and id(row) not in consumed
                      and abs(row["y"] - main["y"]) <= base_size * 1.5
                      and row["x1"] - row["x0"] <= 0.5 * width
                      and row["x0"] >= main["x0"] - 2
                      and row["x1"] <= main["x1"] + 2
                      and not _CJK_RE.search(row_text(row))]
        ups = [row for row in candidates
               if row["y"] < main["y"] - row_tolerance]
        downs = [row for row in candidates
                 if row["y"] > main["y"] + row_tolerance]
        for up in sorted(ups, key=lambda r: -r["y"]):
            up_center = (up["x0"] + up["x1"]) / 2
            for down in sorted(downs, key=lambda r: r["y"]):
                if id(down) in consumed:
                    continue
                down_center = (down["x0"] + down["x1"]) / 2
                if abs(up_center - down_center) > max(4.0, base_size * 0.8):
                    continue
                x0 = min(up["x0"], down["x0"])
                x1 = max(up["x1"], down["x1"])
                slot = _fraction_slot(main["pieces"], x0, x1)
                if slot is None:
                    continue
                text = row_text(up) + "/" + row_text(down)
                main["pieces"].insert(slot, {"x0": x0, "x1": x1, "text": text})
                consumed.add(id(up))
                consumed.add(id(down))
                break

    lines = []
    for row in rows_data:
        if id(row) in consumed:
            continue
        for text in _row_lines(row["pieces"], base_size):
            if text:
                lines.append((row["y"], text))
    lines.sort(key=lambda item: item[0])
    return "\n".join(text for _, text in lines)


def _pdf_text_blocks(page) -> list[tuple[float, str, RunStyle, tuple]]:
    items = []
    entries = []
    data = page.get_text("dict")
    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        bbox = block.get("bbox")
        if bbox is None:
            continue
        lines = block.get("lines", [])
        spans = [span for line in lines for span in line.get("spans", [])]
        if not any((span.get("text") or "").strip() for span in spans):
            continue
        entries.append((tuple(bbox), lines, spans))
    for group in _group_blocks(entries):
        bbox = _union_bbox([entry[0] for entry in group])
        spans = [span for _, _, group_spans in group for span in group_spans]
        first_span = next(span for span in spans
                          if (span.get("text") or "").strip())
        if _has_math_glyph(spans):
            text = _geometry_text(spans)
        else:
            line_entries = []
            for _, block_lines, _ in group:
                for line in block_lines:
                    line_text = _pdf_line_text(line.get("spans", []))
                    if not line_text.strip():
                        continue
                    line_span = next(span for span in line.get("spans", [])
                                     if (span.get("text") or "").strip())
                    line_entries.append((_span_pos(line_span)[1], line_text))
            ys = [y for y, _ in line_entries]
            if len(line_entries) > 1 and max(ys) - min(ys) <= 5.0:
                # Same visual row: separate columns/table cells, not a
                # vertically split formula.
                lines = [text for _, text in line_entries]
            else:
                lines = normalize_formula_lines(
                    [text for _, text in line_entries], drop_isolated=False)
            text = "\n".join(lines).strip()
        if not text:
            continue
        items.append((bbox[1], text, _pdf_style(first_span), bbox))
    return items


def _merge_formula_blocks(blocks: list) -> list:
    merged = []
    buffer: list[ParaBlock] = []

    def flush() -> None:
        if not buffer:
            return
        style = buffer[0].style
        for line in normalize_formula_lines([b.text for b in buffer]):
            merged.append(ParaBlock(text=line, style=style))
        buffer.clear()

    for block in blocks:
        text = getattr(block, "text", "")
        if (block.kind == "paragraph" and not block.figures and text
                and "\n" not in text and is_math_line(text)):
            buffer.append(block)
        else:
            flush()
            merged.append(block)
    flush()
    return merged


def _strip_isolated_letters(blocks: list) -> list:
    cleaned = []
    for block in blocks:
        if block.kind != "paragraph" or block.figures or not block.text:
            cleaned.append(block)
            continue
        lines = [line for line in block.text.split("\n")
                 if not is_isolated_letter(line)]
        text = "\n".join(lines).strip()
        if text:
            cleaned.append(ParaBlock(text=text, style=block.style))
    return cleaned


def _pdf_tables(path: Path) -> dict[int, list[tuple[tuple, list[list[str]], str]]]:
    import pdfplumber
    from .figures import is_table_caption

    try:
        pdf = pdfplumber.open(str(path))
    except Exception as exc:
        lowered = str(exc).lower()
        if "password" in lowered or "encrypt" in lowered:
            raise IngestError("PDF 已加密，请先解除密码后再使用") from exc
        raise IngestError(f"无法读取 PDF：{exc}") from exc
    result: dict[int, list[tuple[tuple, list[list[str]], str]]] = {}
    with pdf:
        for pageno, page in enumerate(pdf.pages):
            entries = []
            try:
                found = page.find_tables()
            except Exception:
                found = []
            try:
                lines = page.extract_text_lines() or []
            except Exception:
                lines = []
            for table in found:
                rect = tuple(table.bbox)
                try:
                    rows = table.extract() or []
                except Exception:
                    continue
                rows = [[cell or "" for cell in row] for row in rows]
                caption = ""
                above = [line for line in lines
                         if line.get("bottom", 0) <= rect[1] + 1]
                if above:
                    nearest = max(above, key=lambda line: line.get("bottom", 0))
                    if is_table_caption(nearest.get("text", "")):
                        caption = nearest["text"].strip()
                entries.append((rect, rows, caption))
            result[pageno] = entries
    return result


def ingest_pdf(path: Path) -> SourceDoc:
    import pymupdf

    path = Path(path)
    try:
        doc = pymupdf.open(str(path))
    except Exception as exc:
        lowered = str(exc).lower()
        if "password" in lowered or "encrypt" in lowered:
            raise IngestError("PDF 已加密，请先解除密码后再使用") from exc
        raise IngestError(f"无法打开 PDF：{exc}") from exc

    try:
        if doc.needs_pass:
            raise IngestError("PDF 已加密，请先解除密码后再使用")
        tables_by_page = _pdf_tables(path)
        blocks = []
        text_found = False
        order = 0
        for pageno, page in enumerate(doc):
            items = []
            table_rects = [rect for rect, _, _ in tables_by_page.get(pageno, [])]
            for y, text, style, bbox in _pdf_text_blocks(page):
                cy = (bbox[1] + bbox[3]) / 2
                cx = (bbox[0] + bbox[2]) / 2
                if any(_point_in_rect(cx, cy, rect) for rect in table_rects):
                    continue
                text_found = True
                items.append((y, ParaBlock(text=text, style=style)))
            for xref in _pdf_image_xrefs(page):
                try:
                    info = doc.extract_image(xref)
                except Exception:
                    continue
                if not info or not info.get("image"):
                    continue
                rects = page.get_image_rects(xref)
                y = rects[0].y0 if rects else 0.0
                figure = Figure(image_bytes=info["image"],
                                ext=info.get("ext", "png"), order=order)
                order += 1
                items.append((y, ParaBlock(text="", figures=[figure])))
            for rect, rows, caption in tables_by_page.get(pageno, []):
                items.append((rect[1], TableBlock(TableData(rows=rows, caption=caption))))
            items.sort(key=lambda item: item[0])
            page_blocks = _merge_formula_blocks([block for _, block in items])
            blocks.extend(_strip_isolated_letters(page_blocks))
        if not text_found:
            raise IngestError("PDF 没有文字层（可能是扫描件），暂不支持 OCR")
        return SourceDoc(blocks=blocks, path=path)
    finally:
        doc.close()


def _point_in_rect(x: float, y: float, rect: tuple) -> bool:
    x0, top, x1, bottom = rect
    return x0 <= x <= x1 and top <= y <= bottom


def _pdf_image_xrefs(page) -> list[int]:
    xrefs = []
    for info in page.get_images(full=True):
        xref = info[0]
        if xref not in xrefs:
            xrefs.append(xref)
    return xrefs


def ingest_txt(path: Path) -> SourceDoc:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            text = path.read_text(encoding="gbk")
        except UnicodeDecodeError as exc:
            raise IngestError("文本文件编码无法识别，请另存为 UTF-8") from exc
    blocks = [ParaBlock(text=line.rstrip("\r")) for line in text.splitlines()]
    return SourceDoc(blocks=blocks, path=path)


def _convert_doc_with_wps(path: Path) -> Path:
    try:
        import win32com.client
    except ImportError as exc:
        raise IngestError("未安装 pywin32，无法转换 .doc 文件") from exc
    path = Path(path).resolve()
    out = path.with_suffix(".docx")
    app = win32com.client.Dispatch("Kwps.Application")
    app.Visible = False
    try:
        doc = app.Documents.Open(str(path))
        doc.SaveAs2(str(out), FileFormat=16)
        doc.Close(False)
    finally:
        app.Quit()
    return out


def prepare_doc(path: Path) -> Path:
    try:
        return _convert_doc_with_wps(Path(path))
    except Exception as exc:
        raise IngestError(
            "无法转换 .doc 文件：请用 WPS 打开并另存为 .docx 后重试") from exc


def ingest(path: Path) -> SourceDoc:
    path = Path(path)
    if not path.exists():
        raise IngestError(f"找不到文件：{path}")
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return ingest_docx(path)
    if suffix == ".pdf":
        return ingest_pdf(path)
    if suffix == ".doc":
        return ingest_docx(prepare_doc(path))
    if suffix in (".txt", ".md"):
        return ingest_txt(path)
    raise IngestError("不支持的文件格式")
