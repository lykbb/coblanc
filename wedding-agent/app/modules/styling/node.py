"""妆造师（agent）：负责妆容、发型、服饰、配饰，写出造型描述 look。

在小囍之后、摄影师之前上场：先从资产库按分类找参考图（search_assets），以妆造师身份展示给用户，
用 questions 和用户确认妆容、发型、服饰、配饰，确认后写 look。框架负责暂停、收集回答，回答后再调用一次本函数。
每次调用都要返回一版 look（还在问问题时给的是按推荐选项写的草稿）。
fake 模式用下面的模板填空版；真实实现是一个 agent，按 TODO 补。
"""

from pathlib import Path

from app.common.config import settings
from app.modules.assets import search_assets
from app.state import Brief, WeddingState

PROMPTS = Path(__file__).parent / "prompts"
DEFAULT_STYLE = "keep_original"
# 资产库里还没有物料时，用文字选项兜底
FALLBACK_OPTIONS = {
    "makeup": [("natural", "自然淡妆"), ("korean", "清透韩妆"), ("retro", "复古红唇")],
    "outfit": [("satin", "缎面抹胸婚纱"), ("lace", "蕾丝长袖婚纱"), ("mermaid", "鱼尾拖尾婚纱")],
}


def available_styles() -> list[str]:
    return sorted(path.stem for path in PROMPTS.glob("*.md"))


def style(state: WeddingState) -> dict:
    if settings.fake_for("styling"):
        return _template_look(state)
    # TODO(妆造师)：用 get_llm("agent") 做一个 agent，工具是 search_assets（kind 用 makeup / outfit / style），
    #   按需求单找参考图，以妆造师身份写 step_text 和 questions（选项带参考图），和用户确认妆容、发型、服饰、配饰；
    #   最多调用 settings.max_agent_steps 次工具；每次都返回一版 look；
    #   必须保留 keep_features；beautify 不是 "light" 时不写瘦身、改五官、年轻化；
    #   retouch_plan 的 target 为 look 时按 patch 调整，不再问用户。返回格式和 _template_look 一样。
    raise NotImplementedError("妆造师的真实实现还没写，见《小囍模块接入规范》模块卡片 3")


def _options(kind: str, style_id: str) -> list[dict]:
    assets = search_assets(kind, [style_id])[:4]
    if assets:
        return [{"value": item["asset_id"], "label": item["name"], "image": item["url"]} for item in assets]
    return [{"value": value, "label": label, "image": None} for value, label in FALLBACK_OPTIONS[kind]]


def _questions(style_id: str) -> list[dict]:
    makeup, outfit = _options("makeup", style_id), _options("outfit", style_id)
    return [
        {"question_id": "q_makeup", "type": "single_choice", "title": "想要什么样的妆容？", "options": makeup, "recommended": makeup[0]["value"], "allow_skip": True},
        {"question_id": "q_outfit", "type": "single_choice", "title": "婚纱想要哪种款式？", "options": outfit, "recommended": outfit[0]["value"], "allow_skip": True},
    ]


def _choose(question: dict, answer: dict | None) -> dict:
    """用户选了就用用户选的，跳过或没回答就用推荐项。"""
    if answer and not answer.get("skipped"):
        for option in question["options"]:
            if option["value"] == answer.get("value"):
                return option
    return next(option for option in question["options"] if option["value"] == question["recommended"])


def _template_look(state: WeddingState) -> dict:
    brief = Brief(**state.get("brief", {}))
    style_id = brief.style if (PROMPTS / f"{brief.style}.md").is_file() else DEFAULT_STYLE
    questions = _questions(style_id)
    answers = {item["question_id"]: item for item in state.get("answers", []) if item.get("asker") == "styling"}
    makeup, outfit = (_choose(question, answers.get(question["question_id"])) for question in questions)

    fields = {key: value for key, value in brief.model_dump().items() if isinstance(value, str)}
    fields.update(makeup=makeup["label"], outfit_bride=outfit["label"])
    text = (PROMPTS / f"{style_id}.md").read_text(encoding="utf-8").strip().format_map(fields)
    if brief.keep_features:
        text += f"保留：{'、'.join(brief.keep_features)}。"
    plan = state.get("retouch_plan") or {}
    if plan.get("target") == "look" and plan.get("patch"):
        text += f"调整：{plan['patch']}。"

    references = [{"url": option["image"], "role": role} for option, role in ((makeup, "makeup"), (outfit, "outfit")) if option["image"]]
    look = {"text": text, "style": style_id, "references": references}
    if answers or state.get("candidates"):  # 已经和用户确认过，或已经在修图阶段：不再问
        return {"look": look}
    return {"look": look, "questions": questions, "step_text": "我是妆造师，按你们选的风格挑了几款妆容和婚纱，选一个最喜欢的吧。"}
