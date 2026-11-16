import re

_OPERATORS = set("=+-−×·*/÷≈<>≤≥")
_TOKEN_RE = re.compile(
    r"^[A-Za-z0-9α-ωΑ-Ω.,=+\-−×·*/÷()（）\[\]{}²³_^%<>≤≥:：]+$")
_SINGLE_LETTER_RE = re.compile(r"^[A-Za-zα-ωΑ-Ω]$")
_SUBSCRIPT_RE = re.compile(r"^[A-Za-z0-9α-ωΑ-Ω]{1,4}$")


def is_isolated_letter(text: str) -> bool:
    return bool(_SINGLE_LETTER_RE.match(text.strip()))


def is_math_line(text: str) -> bool:
    t = text.strip()
    if not t or " " in t or len(t) > 12:
        return False
    return bool(_TOKEN_RE.match(t))


def _is_operator(token: str) -> bool:
    return token in _OPERATORS


def _has_structure(tokens: list[str]) -> bool:
    if any(_is_operator(t) for t in tokens):
        return True
    singles = sum(1 for t in tokens if _SINGLE_LETTER_RE.match(t))
    if singles >= 2:
        return True
    return singles >= 1 and any(len(t) > 1 for t in tokens)


def _join_tokens(tokens: list[str]) -> str:
    pieces = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if _is_operator(token):
            pieces.append(f" {token} ")
            index += 1
        elif (_SINGLE_LETTER_RE.match(token) and index + 1 < len(tokens)
              and _SUBSCRIPT_RE.match(tokens[index + 1])
              and not _is_operator(tokens[index + 1])):
            pieces.append(f"{token}_{tokens[index + 1]}")
            index += 2
        else:
            pieces.append(token)
            index += 1
    return re.sub(r"\s+", " ", "".join(pieces)).strip()


_SCRIPT_PATTERN = r"(?:[A-Za-z0-9α-ωΑ-Ω+\-−]+|\{[A-Za-z0-9α-ωΑ-Ω+\-−]+\})"
_TERM_PATTERN = (
    r"(?:[A-Za-zα-ωΑ-Ω][A-Za-z0-9α-ωΑ-Ω]*|\d+(?:\.\d+)?)"
    rf"(?:[_^]{_SCRIPT_PATTERN})*")
_OPERATOR_PATTERN = r"[=+\-−×·*/÷<>≤≥≈]"
_FORMULA_SPAN_RE = re.compile(
    rf"(?<![A-Za-z0-9_\\${{^]){_TERM_PATTERN}"
    rf"(?:(?:\s*{_OPERATOR_PATTERN}\s*{_TERM_PATTERN})|{_TERM_PATTERN})*"
    rf"(?![A-Za-z0-9_])")
_MATH_SEGMENT_RE = re.compile(r"(\$[^$]*\$)")
_SUBSUP_FIX_RE = re.compile(
    r"([A-Za-zα-ωΑ-Ω0-9}])([_^])(?!\{)([A-Za-z0-9α-ωΑ-Ω]+)")


def _needs_latex(expr: str) -> bool:
    return "_" in expr or "^" in expr


def _convert_atoms(expr: str) -> str:
    expr = _SUBSUP_FIX_RE.sub(r"\1\2{\3}", expr)
    expr = re.sub(rf"\s*({_OPERATOR_PATTERN})\s*", r" \1 ", expr)
    return re.sub(r"\s+", " ", expr).strip()


def _convert_side(side: str) -> str:
    side = side.strip()
    if side.count("/") == 1 and not re.search(r"[=+\-−×·*÷]", side):
        numerator, denominator = side.split("/", 1)
        return (f"\\frac{{{_convert_atoms(numerator)}}}"
                f"{{{_convert_atoms(denominator)}}}")
    return _convert_atoms(side)


def _convert_formula(expr: str) -> str:
    expr = expr.strip()
    if "=" in expr:
        left, right = expr.split("=", 1)
        return f"{_convert_side(left)} = {_convert_side(right)}"
    return _convert_side(expr)


def _replace_formula(match: re.Match) -> str:
    expr = match.group(0)
    if not _needs_latex(expr):
        return expr
    return f"${_convert_formula(expr)}$"


def latexify_text(text: str) -> str:
    """Wrap recognised plain-text formulas in inline LaTeX ($...$)."""
    pieces = _MATH_SEGMENT_RE.split(text)
    for index in range(0, len(pieces), 2):
        pieces[index] = _FORMULA_SPAN_RE.sub(_replace_formula, pieces[index])
    return "".join(pieces)


def normalize_formula_lines(lines: list[str],
                            drop_isolated: bool = True) -> list[str]:
    """Merge vertically split formula fragments (N / OL / = ...) into one line."""
    result = []
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if is_math_line(line):
            end = index
            group = []
            while end < len(lines) and is_math_line(lines[end]):
                group.append(lines[end].strip())
                end += 1
            if len(group) >= 2 and _has_structure(group):
                result.append(_join_tokens(group))
            else:
                for token in group:
                    if drop_isolated and _SINGLE_LETTER_RE.match(token):
                        continue
                    result.append(token)
            index = end
            continue
        result.append(line)
        index += 1
    return result
