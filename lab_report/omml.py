"""把 LaTeX 转成 Word 原生公式（OMML）。"""

import re

from docx.oxml import parse_xml

MATH_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
_OMATH_OPEN_RE = re.compile(r"<m:oMath(\s|>)")


def _declare_namespace(xml: str) -> str:
    if "xmlns:m=" in xml[:200]:
        return xml
    return _OMATH_OPEN_RE.sub(
        lambda match: f'<m:oMath xmlns:m="{MATH_NS}"{match.group(1)}', xml, count=1)


def latex_to_omml(latex: str) -> str | None:
    """返回带命名空间声明的 <m:oMath> 字符串；转换失败返回 None。"""
    latex = (latex or "").strip()
    if not latex:
        return None
    try:
        from latex2mathml.converter import convert as latex_to_mathml
        from mathml2omml import convert as mathml_to_omml
    except ImportError:
        return None
    try:
        mathml = latex_to_mathml(latex)
        omml = mathml_to_omml(mathml)
    except Exception:
        return None
    if not omml or "<m:oMath" not in omml:
        return None
    return _declare_namespace(omml.strip())


def build_math_element(latex: str):
    xml = latex_to_omml(latex)
    if xml is None:
        return None
    try:
        return parse_xml(xml)
    except Exception:
        return None


def build_display_math_element(latex: str):
    omml = latex_to_omml(latex)
    if omml is None:
        return None
    inner = omml.replace(f' xmlns:m="{MATH_NS}"', "", 1)
    xml = (
        f'<m:oMathPara xmlns:m="{MATH_NS}">'
        '<m:oMathParaPr><m:jc m:val="center"/></m:oMathParaPr>'
        f"{inner}"
        "</m:oMathPara>"
    )
    try:
        return parse_xml(xml)
    except Exception:
        return None
