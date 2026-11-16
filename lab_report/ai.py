import json
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .models import Experiment, TextBlock

SLOT_KEYS = ("purpose", "equipment", "principle", "steps", "questions")
CONFIG_KEYS = ("provider", "model", "base_url", "api_key_env")

SYSTEM_PROMPT = (
    "你是实验报告排版助手。你只能改写用户提供的指导书原文，使其更接近报告语言；"
    "不得添加书外知识，不得编造数据、器件型号或结论。"
    "所有数值、单位、公式必须原样保留。指导书没有的章节必须返回空列表。"
    "只允许从提供的图片题注中选择插图。"
    "必须只输出一个 JSON 对象，键为 purpose、equipment、principle、steps、"
    "questions、principle_figures。"
)


class AiError(Exception):
    pass


@dataclass
class AiConfig:
    provider: str
    model: str
    base_url: str
    api_key_env: str


def load_ai_config(path: Path) -> AiConfig:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AiError(f"AI 配置读取失败：{exc}") from exc
    if not isinstance(raw, dict) or set(raw) != set(CONFIG_KEYS):
        raise AiError("AI 配置必须且只能包含 provider、model、base_url、api_key_env")
    return AiConfig(provider=raw["provider"], model=raw["model"],
                    base_url=raw["base_url"], api_key_env=raw["api_key_env"])


def _figure_captions(exp: Experiment) -> list[str]:
    return [block.caption for block in exp.principle
            if block.kind == "figure" and block.caption]


def _build_prompt(exp: Experiment) -> str:
    def text_blocks(blocks):
        return "\n".join(f"- {b.text}" for b in blocks if b.kind == "text")

    return (
        f"实验：实验{exp.number}  {exp.title}\n\n"
        "【实验目的】\n" + "\n".join(f"- {line}" for line in exp.purpose) + "\n\n"
        "【实验设备】\n" + "\n".join(f"- {line}" for line in exp.equipment) + "\n\n"
        "【实验原理】\n" + text_blocks(exp.principle) + "\n\n"
        "【实验步骤】\n" + text_blocks(exp.steps) + "\n\n"
        "【思考题】\n" + "\n".join(f"- {line}" for line in exp.questions) + "\n\n"
        "【可用图片题注】\n" + "\n".join(f"- {c}" for c in _figure_captions(exp)) + "\n\n"
        "请改写上面已存在的内容；缺失的章节返回空列表；只从题注列表选择插图。"
    )


def _make_request(cfg: AiConfig, api_key: str, prompt: str):
    base = cfg.base_url.rstrip("/")
    if cfg.provider == "anthropic":
        url = f"{base}/v1/messages"
        payload = {
            "model": cfg.model,
            "max_tokens": 4096,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
    elif cfg.provider == "openai":
        url = f"{base}/chat/completions"
        payload = {
            "model": cfg.model,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                         {"role": "user", "content": prompt}],
        }
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {api_key}",
        }
    else:
        raise AiError(f"不支持的 AI provider：{cfg.provider}")
    request = urllib.request.Request(
        url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers, method="POST")
    return request


def _default_transport(request, timeout):
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _extract_text(cfg: AiConfig, raw: bytes) -> str:
    try:
        data = json.loads(raw.decode("utf-8"))
        if cfg.provider == "anthropic":
            return data["content"][0]["text"]
        return data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise AiError(f"AI 响应不是预期的 JSON 结构：{exc}") from exc


def _parse_payload(text: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise AiError(f"AI 返回内容不是合法 JSON：{exc}") from exc
    if not isinstance(payload, dict) or any(key not in payload for key in
                                            SLOT_KEYS + ("principle_figures",)):
        raise AiError("AI JSON 缺少必需字段")
    for key in SLOT_KEYS + ("principle_figures",):
        value = payload[key]
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise AiError(f"AI JSON 字段 {key} 必须是字符串列表")
    return payload


def rewrite_experiment(exp: Experiment, cfg: AiConfig, api_key: str,
                       transport=None) -> Experiment:
    if not api_key:
        raise AiError("缺少 API key，无法调用 AI")
    transport = transport or _default_transport
    request = _make_request(cfg, api_key, _build_prompt(exp))
    try:
        raw = transport(request, 60)
    except OSError as exc:
        raise AiError(f"AI 请求失败：{exc}") from exc
    payload = _parse_payload(_extract_text(cfg, raw))

    captions = set(_figure_captions(exp))
    unknown = [caption for caption in payload["principle_figures"] if caption not in captions]
    if unknown:
        raise AiError(f"AI JSON 选择了不存在的图片题注：{unknown[0]}")

    purpose = [] if "purpose" in exp.missing else list(payload["purpose"])
    equipment = [] if "equipment" in exp.missing else list(payload["equipment"])
    question_list = [] if "questions" in exp.missing else list(payload["questions"])
    if "steps" in exp.missing:
        step_blocks = []
    else:
        step_blocks = [TextBlock(text=text) for text in payload["steps"]]
        step_blocks.extend(block for block in exp.steps if block.kind == "table")

    if "principle" in exp.missing:
        principle_blocks = []
    else:
        principle_blocks = [TextBlock(text=text) for text in payload["principle"]]
        chosen = [block for block in exp.principle
                  if block.kind == "figure" and block.caption in payload["principle_figures"]]
        principle_blocks.extend(chosen)
        principle_blocks.extend(block for block in exp.principle if block.kind == "table")

    missing = list(exp.missing)
    empties = {
        "purpose": purpose,
        "equipment": equipment,
        "principle": principle_blocks,
        "steps": step_blocks,
        "questions": question_list,
    }
    for slot, value in empties.items():
        if not value and slot not in missing:
            missing.append(slot)

    return Experiment(
        number=exp.number, title=exp.title, subtitle=exp.subtitle,
        purpose=purpose, equipment=equipment,
        principle=principle_blocks, steps=step_blocks,
        questions=question_list, missing=missing)
