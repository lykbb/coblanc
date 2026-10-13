"""主 agent（小囍）：以项目经理身份和用户沟通，负责一头一尾，加上中间的最终提示词。

intake：识别意图、检查照片，和用户确认婚礼风格、成片规格、物料需求，资料齐了写 brief，不齐就写 questions 追问。
妆容、发型、服饰由妆造师和用户细聊，互动、场景、灯光由摄影师和用户细聊，小囍不用问。
compose：汇总妆造师的 look 和摄影师的 shot，写出最终提示词和参考图清单，交给生图 agent。
reveal：交付时写一句揭幕寄语。
现在只有 fake 实现，真实实现按 TODO 补。
"""

import re
from pathlib import Path

from app.common.config import settings
from app.state import Brief, WeddingState

PROMPTS = Path(__file__).parent / "prompts"

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


def compose(state: WeddingState) -> dict:
    look = state.get("look") or {}
    shot = state.get("shot") or {}
    plan = state.get("retouch_plan") or {}
    if settings.fake_for("intake"):
        opening = (PROMPTS / "opening.md").read_text(encoding="utf-8").strip()
        parts = [opening, look.get("text", ""), shot.get("text", "")]
        if plan.get("target") == "prompt" and plan.get("patch"):
            parts.append(f"特别注意：{plan['patch']}。")
        # 姿势参考图优先，其次婚纱、妆容等；总数不超过生图服务能接受的张数
        refs = sorted(shot.get("references", []) + look.get("references", []), key=lambda ref: ref["role"] != "pose")
        unique = list({ref["url"]: ref for ref in refs}.values())
        return {"prompt": "".join(part for part in parts if part), "references": unique[: settings.max_reference_images]}
    # TODO(主 agent)：用 get_llm("agent") 把需求单、look、shot 写成适合生图模型的一段提示词：
    #   两人五官和身高差不变的要求放最前；look 和 shot 有矛盾时由小囍取舍（比如拖尾婚纱配坐姿）；
    #   retouch_plan 的 target 为 prompt 时按 patch 改写；参考图最多 settings.max_reference_images 张
    raise NotImplementedError("小囍写提示词的真实实现还没写，见《小囍模块接入规范》模块卡片 2")


def reveal(state: WeddingState) -> dict:
    if settings.fake_for("intake"):
        return {"message": "照片里你们笑得很自然，愿你们的婚礼也像这组照片一样，温柔又闪闪发光。"}
    # TODO(主 agent)：根据照片和需求单写 50 字以内的寄语，只用真实信息，不编造经历
    raise NotImplementedError("小囍的揭幕寄语还没写，见《小囍模块接入规范》模块卡片 2")


def _fake_intake(state: WeddingState) -> dict:
    answers = {item["question_id"]: item for item in state.get("answers", []) if item.get("asker", "intake") == "intake"}
    if not answers:
        return {
            "questions": FAKE_QUESTIONS,
            "brief": Brief(missing=["style", "heights_cm"]).model_dump(),
            "step_text": "我是小囍，你们这次拍摄的项目经理。先确认两件事，后面妆造师和摄影师还会跟你们细聊。",
        }

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
