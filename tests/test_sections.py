from pathlib import Path
import pytest
from lab_report.models import ParaBlock, SourceDoc
from lab_report.sections import (SectionError, classify_heading, filter_questions,
                                 parse_experiment, split_experiments)

from conftest import (DIGITAL_GUIDE, EXAMPLE_TEMPLATE_CONFIG, GUIDE,
                      needs_digital_guide, needs_guide)

@pytest.mark.parametrize("text,expected", [
    ("一、实验目的", "purpose"),
    ("二、实验仪器", "equipment"),
    ("三、实验原理", "principle"),
    ("1、实验原理描述", "principle"),
    ("四、实验内容", "steps"),
    ("2、实验步骤（含实验仪器操作步骤）", "steps"),
    ("四、实验报告要求", "guidance"),
    ("五、预习要求", "guidance"),
    ("六、注意事项", "guidance"),
    ("一、实验要求", "guidance"),
    ("八、思考题", "questions"),
    ("七、课后习题", "questions"),
])
def test_classify_heading(text, expected):
    assert classify_heading(text) == expected


def test_guidance_sections_are_dropped_and_questions_kept():
    doc = SourceDoc(blocks=[
        ParaBlock(text="实验九  测试"),
        ParaBlock(text="四、实验内容"),
        ParaBlock(text="1、接好电路并测量。"),
        ParaBlock(text="六、注意事项"),
        ParaBlock(text="1、实验前请认真预习，注意安全。"),
        ParaBlock(text="八、思考题"),
        ParaBlock(text="1、为什么静态工作点会漂移？"),
    ])
    exp = parse_experiment(doc, None, ["讨论", "思考", "为什么", "如何", "分析"])
    step_texts = [b.text for b in exp.steps if b.kind == "text"]
    assert step_texts == ["1、接好电路并测量。"]
    assert exp.principle == []
    assert exp.questions == ["1、为什么静态工作点会漂移？"]


def test_guidance_question_lines_are_salvaged():
    doc = SourceDoc(blocks=[
        ParaBlock(text="实验九  测试"),
        ParaBlock(text="四、实验内容"),
        ParaBlock(text="1、接好电路并测量。"),
        ParaBlock(text="五、预习要求"),
        ParaBlock(text="1、复习有关OTL工作原理部分内容。"),
        ParaBlock(text="2、为什么引入自举电路能够扩大输出电压的动态范围？"),
        ParaBlock(text="四、实验报告要求"),
        ParaBlock(text="1、记录实验数据，填写数据表。"),
        ParaBlock(text="2、讨论并总结工作点变化对输出波形的影响。"),
    ])
    exp = parse_experiment(doc, None, ["讨论", "思考", "为什么", "如何", "分析"])
    assert exp.questions == [
        "2、为什么引入自举电路能够扩大输出电压的动态范围？",
        "2、讨论并总结工作点变化对输出波形的影响。",
    ]
    assert all("复习" not in b.text for b in exp.steps if b.kind == "text")
    assert all("记录实验数据" not in b.text for b in exp.steps if b.kind == "text")

def test_split_handles_zero_width_and_title():
    doc = SourceDoc(blocks=[
        ParaBlock(text="实验一​   常用电子仪器的使用"),
        ParaBlock(text="（验证性实验）"),
        ParaBlock(text="一、实验目的"),
    ])
    assert split_experiments(doc)[0][:2] == ("一", "常用电子仪器的使用")

def test_filter_questions_keeps_discussion_only():
    lines = ["1、认真做实验，记录实验数据。", "2、讨论并总结静态工作点变化对放大器输出波形的影响。"]
    assert filter_questions(lines, ["讨论", "思考", "为什么", "如何", "分析"]) == [
        "2、讨论并总结静态工作点变化对放大器输出波形的影响。"]

def test_subtitle_and_purpose_heading_in_one_block():
    doc = SourceDoc(blocks=[
        ParaBlock(text="实验一  集成逻辑门电路参数测试"),
        ParaBlock(text="（验证性实验）\n一、实验目的"),
        ParaBlock(text="1、掌握仪器使用\n2、学习芯片辨识\n3、测试直流参数\n4、验证逻辑功能"),
        ParaBlock(text="二、实验仪器"),
        ParaBlock(text="1、数字式万用表\n88E\n1 台\n2、数字式示波器\nTBS1102C\n1 台"),
    ])
    exp = parse_experiment(doc, None, [])
    assert exp.subtitle == "（验证性实验）"
    assert exp.purpose == [
        "掌握仪器使用", "学习芯片辨识", "测试直流参数", "验证逻辑功能"]
    assert exp.equipment == [
        "数字式万用表\n88E\n1 台", "数字式示波器\nTBS1102C\n1 台"]


def test_question_heading_merged_into_report_requirement_block():
    doc = SourceDoc(blocks=[
        ParaBlock(text="实验一  测试"),
        ParaBlock(text="七、报告要求"),
        ParaBlock(text="1.实验目的\n2.实验原理\n3.测试结果\n6.思考题\n八、思考题"),
        ParaBlock(text="1、试用与非门实现F＝A，"),
        ParaBlock(text="画出电路图。"),
        ParaBlock(text="2、列出实测数据表格，"),
        ParaBlock(text="与出厂参数相比，判断是否及格。"),
        ParaBlock(text="3、总结多余输入端的处理方法。"),
    ])
    exp = parse_experiment(doc, None, [])
    assert exp.questions == [
        "1、试用与非门实现F＝A，\n画出电路图。",
        "2、列出实测数据表格，\n与出厂参数相比，判断是否及格。",
        "3、总结多余输入端的处理方法。",
    ]
    assert not any("报告要求" in q or "实验目的" in q for q in exp.questions)


@needs_digital_guide
def test_digital_guide_experiment_one_purpose_and_questions():
    from lab_report.config import load_template_config
    from lab_report.ingest import ingest
    keywords = load_template_config(EXAMPLE_TEMPLATE_CONFIG).question_keywords
    exp = parse_experiment(ingest(DIGITAL_GUIDE), "1", keywords)
    assert len(exp.purpose) == 4
    assert "实验仪器的使用" in exp.purpose[0]
    assert len(exp.questions) == 3
    assert "试用与非门" in exp.questions[0]
    assert "画出电路图" in exp.questions[0]


def test_missing_principle_detected():
    from lab_report.models import Experiment
    exp = parse_experiment(SourceDoc(blocks=[
        ParaBlock(text="实验九  测试"),
        ParaBlock(text="一、实验目的"), ParaBlock(text="1、目的甲"),
        ParaBlock(text="二、实验仪器"), ParaBlock(text="1、万用表"),
        ParaBlock(text="四、实验内容"), ParaBlock(text="1、接电路"),
        ParaBlock(text="四、实验报告要求"), ParaBlock(text="1、讨论结果"),
    ]), None, ["讨论"])
    assert "principle" in exp.missing

def test_unknown_selector_lists_titles():
    doc = SourceDoc(blocks=[ParaBlock(text="实验一  甲"), ParaBlock(text="实验二  乙")])
    with pytest.raises(SectionError, match="实验二"):
        parse_experiment(doc, "实验七", [])

@needs_guide
def test_real_guide_guidance_never_becomes_body():
    from lab_report.config import load_template_config
    from lab_report.ingest import ingest_docx
    doc = ingest_docx(GUIDE)
    keywords = load_template_config(EXAMPLE_TEMPLATE_CONFIG).question_keywords
    exp1 = parse_experiment(doc, "1", keywords)
    assert exp1.questions == []
    exp6 = parse_experiment(doc, "6", keywords)
    joined = "\n".join(q for q in exp6.questions)
    assert "为什么引入自举电路" in joined
    assert "交越失真" in joined
    assert "复习有关OTL" not in joined
    assert "比较Pom" not in joined
    body = [b.text for slot in (exp6.principle, exp6.steps)
            for b in slot if b.kind == "text"]
    assert all("OTL 工作原理" not in t for t in body)

@needs_guide
def test_real_guide_experiment_three():
    from lab_report.ingest import ingest_docx
    exp = parse_experiment(ingest_docx(GUIDE), "3", ["讨论", "思考", "分析"])
    assert exp.number == "三" and "晶体管" in exp.title
    assert len(exp.purpose) == 2 and len(exp.equipment) == 4
    figures = [b for b in exp.principle if b.kind == "figure"]
    tables = [b for b in exp.steps if b.kind == "table"]
    assert len(figures) >= 3 and len(tables) == 3
    assert len(exp.questions) == 1 and "讨论" in exp.questions[0]

@needs_guide
def test_real_guide_missing_sections():
    from lab_report.ingest import ingest_docx
    doc = ingest_docx(GUIDE)
    assert "principle" in parse_experiment(doc, "1", []).missing
    assert "steps" in parse_experiment(doc, "2", []).missing
