from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class RunStyle:
    font_name: str = "宋体"
    size_pt: float = 12.0
    bold: bool = False


@dataclass
class Figure:
    image_bytes: bytes
    ext: str = "png"
    caption: str = ""
    order: int = 0
    kind: str = field(default="figure", init=False)


@dataclass
class TextBlock:
    text: str
    style: RunStyle = field(default_factory=RunStyle)
    kind: str = field(default="text", init=False)


@dataclass
class TableData:
    element: Any = None
    media: dict[str, bytes] = field(default_factory=dict)
    rows: list[list[str]] | None = None
    caption: str = ""
    kind: str = field(default="table", init=False)


@dataclass
class ParaBlock:
    text: str
    style: RunStyle = field(default_factory=RunStyle)
    figures: list[Figure] = field(default_factory=list)
    kind: str = field(default="paragraph", init=False)


@dataclass
class TableBlock:
    table: TableData
    kind: str = field(default="table", init=False)


@dataclass
class SourceDoc:
    blocks: list = field(default_factory=list)
    path: Path | None = None


@dataclass
class Experiment:
    number: str = ""
    title: str = ""
    subtitle: str = ""
    purpose: list[str] = field(default_factory=list)
    equipment: list[str] = field(default_factory=list)
    principle: list = field(default_factory=list)
    steps: list = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
