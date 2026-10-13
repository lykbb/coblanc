"""主 agent（小囍）。

intake：识别意图、检查照片和资料，资料齐了写 brief，不齐就写 questions 追问。
reveal：交付时写一句揭幕寄语。
现在只有 fake 实现，真实实现按 TODO 补。
"""

import re

from app.common.config import settings
from app.state import Brief, WeddingState

# 追问格式见《小囍接口约定》的 questions
FAKE_QUESTIONS = [
    {
        "question_id": "q_style",
        "type": "single_choice",
        "title": "想要哪种风格？",
        "options": [
            {"value": "korean_studio", "label": "韩式影棚", "image": None},
            {"value": "keep_original", "label": "保留原图场景", "image": None},
        ],
        "recommended": "korean_studio",
        "allow_skip": True,
    },
    {
        "question_id": "q_height",
        "type": "text",
        "title": "两人身高大概多少？",
        "placeholder": "例如 175 / 162",
        "allow_skip": True,
    },
]


def intake(state: WeddingState) -> dict:
    if settings.fake_for("intake"):
        return _fake_intake(state)
    # TODO(主 agent)：真实实现
    #   1. get_llm("vision") 检查照片：是否 2 个人、正脸、清晰、无遮挡，不合格抛 ModuleError("PHOTO_INVALID", 原因)
    #   2. 识别意图，再用 get_llm("agent").with_structured_output(Brief) 生成需求单
    #   3. 缺必填项就写 questions（每轮最多 3 个、最多 2 轮），2 轮后仍缺的填默认值
    #   提示词放 prompts/
    raise NotImplementedError("小囍的真实实现还没写，见《小囍模块接入规范》模块卡片 2")


def reveal(state: WeddingState) -> dict:
    if settings.fake_for("intake"):
        return {"message": "照片里你们笑得很自然，愿你们的婚礼也像这组照片一样，温柔又闪闪发光。"}
    # TODO(主 agent)：根据照片和需求单写 50 字以内的寄语，只用真实信息，不编造经历
    raise NotImplementedError("小囍的揭幕寄语还没写，见《小囍模块接入规范》模块卡片 2")


def _fake_intake(state: WeddingState) -> dict:
    answers = {item["question_id"]: item for item in state.get("answers", [])}
    if not answers:
        return {"questions": FAKE_QUESTIONS, "brief": Brief(missing=["style", "heights_cm"]).model_dump()}

    style_answer = answers.get("q_style", {})
    style = "korean_studio" if style_answer.get("skipped") else style_answer.get("value") or "korean_studio"
    heights = _parse_heights((answers.get("q_height") or {}).get("value"))
    brief = Brief(
        style=style,
        background="keep_original" if style == "keep_original" else "studio",
        heights_cm=heights,
        invitation={"names": "小林 & 小周", "date": "2026-12-20", "place": "示例酒店"},
    )
    return {"questions": [], "brief": brief.model_dump()}


def _parse_heights(text: str | None) -> list[int]:
    numbers = [int(n) for n in re.findall(r"\d{3}", text or "")]
    return numbers[:2] if len(numbers) >= 2 else []
