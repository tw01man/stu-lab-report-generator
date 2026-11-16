import json, pytest
from lab_report.ai import AiConfig, AiError, load_ai_config, rewrite_experiment
from lab_report.models import Experiment, Figure, TableData, TextBlock

CFG = AiConfig(provider="anthropic", model="claude-sonnet-4-6",
               base_url="https://api.anthropic.com", api_key_env="ANTHROPIC_API_KEY")

def test_load_ai_config(tmp_path):
    p = tmp_path / "ai.json"
    p.write_text(json.dumps({"provider": "openai", "model": "m",
                             "base_url": "http://x", "api_key_env": "K"}), encoding="utf-8")
    cfg = load_ai_config(p)
    assert (cfg.provider, cfg.model, cfg.base_url, cfg.api_key_env) == ("openai", "m", "http://x", "K")

def _anthropic_body(payload):
    return json.dumps({"content": [{"type": "text", "text": json.dumps(payload)}]}).encode()

def test_rewrite_replaces_text_keeps_figures_and_tables():
    exp = Experiment(number="三", title="放大",
                     purpose=["原始目的"], equipment=["原始设备"],
                     principle=[TextBlock(text="原始原理"), Figure(image_bytes=b"x", ext="png", caption="图3－1")],
                     steps=[TextBlock(text="原始步骤")], questions=["原始题"])
    def transport(request, timeout):
        return _anthropic_body({
            "purpose": ["改写目的"], "equipment": ["改写设备"],
            "principle": ["改写原理"], "steps": ["改写步骤"],
            "questions": ["改写题"], "principle_figures": ["图3－1"]})
    out = rewrite_experiment(exp, CFG, "key", transport=transport)
    assert out.purpose == ["改写目的"] and out.steps[0].text == "改写步骤"
    assert [b.kind for b in out.principle] == ["text", "figure"]
    assert out.principle[1].caption == "图3－1"

def test_invalid_json_raises_ai_error():
    exp = Experiment(number="三", title="放大")
    def transport(request, timeout):
        return json.dumps({"content": [{"type": "text", "text": "not json"}]}).encode()
    with pytest.raises(AiError, match="JSON"):
        rewrite_experiment(exp, CFG, "key", transport=transport)

def test_network_error_becomes_ai_error():
    exp = Experiment(number="三", title="放大")
    def transport(request, timeout):
        raise OSError("connection refused")
    with pytest.raises(AiError, match="请求失败"):
        rewrite_experiment(exp, CFG, "key", transport=transport)

def test_missing_key_raises():
    with pytest.raises(AiError, match="API key"):
        rewrite_experiment(Experiment(number="三", title="放大"), CFG, "")

def test_missing_sections_stay_empty():
    exp = Experiment(number="三", title="放大", missing=["principle"])
    def transport(request, timeout):
        return _anthropic_body({"purpose": ["甲"], "equipment": [], "principle": [],
                               "steps": [], "questions": [], "principle_figures": []})
    out = rewrite_experiment(exp, CFG, "key", transport=transport)
    assert out.principle == [] and "principle" in out.missing
