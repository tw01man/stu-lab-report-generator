from lab_report.formulas import (is_isolated_letter, latexify_text,
                                 normalize_formula_lines)


def test_vertical_formula_fragments_merge_to_single_line():
    lines = ["N", "OL", "=", "I", "OL", "/", "I", "IL"]
    assert normalize_formula_lines(lines) == ["N_OL = I_OL / I_IL"]


def test_isolated_single_letters_are_dropped():
    lines = ["实验原理如下：", "I", "放大器由三极管组成。"]
    assert normalize_formula_lines(lines) == ["实验原理如下：", "放大器由三极管组成。"]


def test_isolated_letters_can_be_kept_for_later_merging():
    assert normalize_formula_lines(["I"], drop_isolated=False) == ["I"]


def test_plain_text_is_untouched():
    lines = ["一、实验目的", "1、观察静态工作点。"]
    assert normalize_formula_lines(lines) == lines


def test_short_symbols_without_structure_are_kept():
    assert normalize_formula_lines(["Ui", "Uo"]) == ["Ui", "Uo"]


def test_isolated_letter_fragments_form_symbol():
    assert normalize_formula_lines(["I", "O", "L"]) == ["I_OL"]


def test_vertical_letter_fragments_form_full_formula():
    lines = ["I", "O", "L", "=", "I", "O", "L", "/", "I", "I", "L"]
    assert normalize_formula_lines(lines) == ["I_OL = I_OL / I_IL"]


def test_premerged_subscripts_join_around_operators():
    lines = ["N_OL", "=", "I_OL", "/", "I_IL"]
    assert normalize_formula_lines(lines) == ["N_OL = I_OL / I_IL"]


def test_is_isolated_letter():
    assert is_isolated_letter("I")
    assert is_isolated_letter(" n ")
    assert not is_isolated_letter("OL")
    assert not is_isolated_letter("1")


def test_latexify_expression_with_fraction():
    assert latexify_text("N_OL = I_OL / I_IL") == \
        "$N_{OL} = \\frac{I_{OL}}{I_{IL}}$"


def test_latexify_standalone_symbol_in_sentence():
    assert latexify_text("其中 I_OL 为输出电流。") == "其中 $I_{OL}$ 为输出电流。"


def test_latexify_keeps_existing_math():
    text = r"公式 $N_{OL} = \frac{I_{OL}}{I_{IL}}$ 已给出。"
    assert latexify_text(text) == text


def test_latexify_leaves_plain_chinese():
    text = "一、实验目的：观察静态工作点。"
    assert latexify_text(text) == text


def test_latexify_superscripts():
    assert latexify_text("x^2 + y^2") == "$x^{2} + y^{2}$"


def test_latexify_does_not_treat_units_as_fractions():
    assert latexify_text("最大取样速率 2 GS/s。") == "最大取样速率 2 GS/s。"


def test_latexify_joins_adjacent_subscripted_terms():
    assert latexify_text("P_{CCL}=V_{CC}I_{CCL}") == \
        "$P_{CCL} = V_{CC}I_{CCL}$"


def test_latexify_equation_with_operator_inside_subscript():
    assert latexify_text("Q_{n+1} = SQ_{n}") == "$Q_{n + 1} = SQ_{n}$"


def test_latexify_stacked_fraction_in_sentence():
    text = "负载电流，则 N_{OL} = I_{OL}/I_{IL}，通常 N_{OL} ≥8。"
    assert latexify_text(text) == (
        "负载电流，则 $N_{OL} = \\frac{I_{OL}}{I_{IL}}$，"
        "通常 $N_{OL} ≥ 8$。")
