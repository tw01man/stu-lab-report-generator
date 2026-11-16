import json
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(Exception):
    pass


@dataclass
class TitleSpec:
    pattern: str = ""
    font_name: str = "黑体"
    size_pt: float = 15.0


@dataclass
class AnchorSpec:
    after_heading: str
    target: str = "next_paragraph"
    cell: tuple[int, int] | None = None
    clear_placeholder: str | None = None
    subsections: dict[str, str] = field(default_factory=dict)


@dataclass
class TemplateConfig:
    name: str = ""
    title: TitleSpec = field(default_factory=TitleSpec)
    profile_replace: dict[str, str] = field(default_factory=dict)
    anchors: dict[str, AnchorSpec] = field(default_factory=dict)
    blank_policy: str = "placeholder"
    blank_course_title: bool = False
    missing_text: str = "（指导书未提供{slot}，请自行补充）"
    tables: dict[str, str] = field(default_factory=dict)
    template_docx: str = ""
    screenshot_columns: list[str] = field(
        default_factory=lambda: ["波形", "观察波形", "实测波形", "截图"])
    question_keywords: list[str] = field(
        default_factory=lambda: ["讨论", "思考", "为什么", "如何", "怎样",
                                 "什么是", "有哪些", "是否", "试述", "简述"])


@dataclass
class Profile:
    name: str = ""
    student_id: str = ""
    department: str = ""
    major: str = ""


REQUIRED_ANCHORS = ("purpose", "equipment", "principle", "steps", "results")


def resolve_template_path(config_path: Path, template_docx: str) -> Path:
    path = Path(template_docx)
    return path if path.is_absolute() else Path(config_path).parent / path


def resolve_profile_path(profile_arg: str | None, default: Path,
                         local: Path) -> Path:
    if profile_arg:
        return Path(profile_arg)
    return local if local.exists() else default


def _anchor_from_json(name: str, raw: dict) -> AnchorSpec:
    if "after_heading" not in raw:
        raise ConfigError(f"模板配置的锚点 {name} 缺少 after_heading")
    cell = raw.get("cell")
    return AnchorSpec(
        after_heading=raw["after_heading"],
        target=raw.get("target", "next_paragraph"),
        cell=tuple(cell) if cell is not None else None,
        clear_placeholder=raw.get("clear_placeholder"),
        subsections=dict(raw.get("subsections", {})),
    )


def load_template_config(path: Path) -> TemplateConfig:
    path = Path(path)
    if not path.exists():
        raise ConfigError(
            f"找不到模板配置：{path}\n"
            "首次使用请复制 templates/模电.example.json 为 templates/模电.json，"
            "并把 template_docx 指向你的 Word 模板。")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"模板配置不是合法 JSON：{path}（{exc}）") from exc

    title_raw = raw.get("title", {})
    try:
        size_pt = float(title_raw.get("size_pt", 15.0))
    except (TypeError, ValueError) as exc:
        raise ConfigError(
            f"模板配置的 size_pt 不是数字：{title_raw.get('size_pt')!r}") from exc
    title = TitleSpec(
        pattern=title_raw.get("pattern", ""),
        font_name=title_raw.get("font_name", "黑体"),
        size_pt=size_pt,
    )

    anchors = {name: _anchor_from_json(name, spec)
               for name, spec in raw.get("anchors", {}).items()}
    for name in REQUIRED_ANCHORS:
        if name not in anchors:
            raise ConfigError(f"模板配置缺少必需锚点：{name}")

    return TemplateConfig(
        name=raw.get("name", ""),
        title=title,
        profile_replace=dict(raw.get("profile_replace", {})),
        anchors=anchors,
        blank_policy=raw.get("blank_policy", "placeholder"),
        blank_course_title=bool(raw.get("blank_course_title", False)),
        missing_text=raw.get("missing_text", "（指导书未提供{slot}，请自行补充）"),
        tables=dict(raw.get("tables", {})),
        template_docx=raw.get("template_docx", ""),
        screenshot_columns=list(raw.get("screenshot_columns",
                                        ["波形", "观察波形", "实测波形", "截图"])),
        question_keywords=list(raw.get("question_keywords",
                                       ["讨论", "思考", "为什么", "如何", "怎样",
                                        "什么是", "有哪些", "是否", "试述", "简述"])),
    )


def load_profile(path: Path) -> Profile:
    path = Path(path)
    if not path.exists():
        raise ConfigError(
            f"找不到个人信息配置：{path}\n"
            "首次使用请复制 profiles/example.json 为 profiles/profile.json，"
            "并填写姓名、学号、院系、专业。")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"个人信息配置不是合法 JSON：{path}（{exc}）") from exc
    return Profile(
        name=raw.get("name", ""),
        student_id=raw.get("student_id", ""),
        department=raw.get("department", ""),
        major=raw.get("major", ""),
    )
