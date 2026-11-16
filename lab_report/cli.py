import argparse
import os
import sys
from pathlib import Path

from .config import (
    ConfigError, load_profile, load_template_config, resolve_template_path)
from .ingest import IngestError, ingest
from .sections import SectionError, parse_experiment
from .template import (SLOT_LABELS, FillOptions, TemplateError, fill_report,
                       save_report)
from .validate import validate_report

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TEMPLATE = PROJECT_ROOT / "templates" / "模电.json"
DEFAULT_PROFILE = PROJECT_ROOT / "profiles" / "profile.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lab_report", description="实验报告自动生成器")
    parser.add_argument("--guide", required=True, help="实验指导书（docx/pdf/doc/txt）")
    parser.add_argument("--experiment", help="实验编号，如 3 或 实验三")
    parser.add_argument("--template", default=str(DEFAULT_TEMPLATE), help="模板配置 JSON")
    parser.add_argument("--profile", default=str(DEFAULT_PROFILE),
                        help="个人信息 JSON（默认 profiles/profile.json，首次使用请从 example.json 复制）")
    parser.add_argument("--out", help="输出目录（默认为指导书所在目录）")
    parser.add_argument("--tables", choices=("preserve", "results"), default="preserve",
                        help="数据表放置：preserve 保持原文位置，results 移到实验结果")
    parser.add_argument("--blank", choices=("placeholder", "empty"), default="placeholder",
                        help="留空方式：placeholder 写入提示，empty 完全留空")
    parser.add_argument("--ai", action="store_true", help="用大模型改写指导书中已有的正文")
    parser.add_argument("--ai-config", help="AI 配置文件 JSON")
    parser.add_argument("--open", action="store_true", help="生成后用默认程序打开")
    parser.add_argument("--no-validate", action="store_true", help="跳过生成后自检")
    return parser


def _apply_ai(exp, args, cfg):
    try:
        from .ai import AiConfig, AiError, load_ai_config, rewrite_experiment
    except ImportError as exc:
        print(f"警告：AI 模块不可用，继续使用原文整理结果（{exc}）", file=sys.stderr)
        return exp

    try:
        ai_cfg = (load_ai_config(Path(args.ai_config)) if args.ai_config
                  else AiConfig(provider="anthropic", model="claude-sonnet-4-6",
                                base_url="https://api.anthropic.com",
                                api_key_env="ANTHROPIC_API_KEY"))
    except AiError as exc:
        print(f"警告：AI 配置无效，继续使用原文整理结果（{exc}）", file=sys.stderr)
        return exp

    api_key = os.environ.get(ai_cfg.api_key_env, "")
    if not api_key:
        print(f"警告：未设置环境变量 {ai_cfg.api_key_env}，跳过 AI 改写", file=sys.stderr)
        return exp
    try:
        return rewrite_experiment(exp, ai_cfg, api_key)
    except AiError as exc:
        print(f"警告：AI 改写失败，继续使用原文整理结果（{exc}）", file=sys.stderr)
        return exp


def _print_summary(exp, out_path: Path, issues: list) -> None:
    figures = sum(1 for b in list(exp.principle) + list(exp.steps) if b.kind == "figure")
    tables = sum(1 for b in list(exp.principle) + list(exp.steps) if b.kind == "table")
    missing = "、".join(SLOT_LABELS.get(slot, slot) for slot in exp.missing) or "无"
    print(f"实验：实验{exp.number}  {exp.title}")
    print(f"已填充：目的 {len(exp.purpose)} 项 / 设备 {len(exp.equipment)} 项 / "
          f"原理 {len(exp.principle)} 块 / 步骤 {len(exp.steps)} 块 / "
          f"图 {figures} 张 / 表 {tables} 张")
    print(f"缺失：{missing}")
    print(f"输出：{out_path}")
    if issues:
        print(f"校验：{len(issues)} 个提示")
        for issue in issues:
            print(f"  - [{issue.code}] {issue.message}")
    else:
        print("校验：通过")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        guide = Path(args.guide)
        template = Path(args.template)
        profile_path = Path(args.profile)
        cfg = load_template_config(template)
        profile = load_profile(profile_path)
        source = ingest(guide)
        selector = args.experiment or None
        exp = parse_experiment(source, selector, cfg.question_keywords)
        if args.ai:
            exp = _apply_ai(exp, args, cfg)
        if not cfg.template_docx:
            raise ConfigError(f"模板配置缺少 template_docx：{template}")
        docx_template = resolve_template_path(template, cfg.template_docx)
        if not docx_template.exists():
            raise ConfigError(
                f"找不到 Word 模板文件：{docx_template}\n"
                "请检查模板配置里的 template_docx 路径，或把模板放到该位置。")
        document = fill_report(docx_template, cfg, exp, profile,
                               FillOptions(table_placement=args.tables,
                                           blank_policy=args.blank))
        out_dir = Path(args.out) if args.out else guide.parent
        out_path = save_report(document, out_dir, profile, exp)
        issues = [] if args.no_validate else validate_report(out_path, cfg, exp)
        _print_summary(exp, out_path, issues)
        if args.open and hasattr(os, "startfile"):
            os.startfile(str(out_path))
        return 0
    except (IngestError, SectionError, TemplateError, ConfigError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
