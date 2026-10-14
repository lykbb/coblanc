"""妆造师 agent。

妆造师只负责两件事：确认一种婚礼风格，并从该风格下挑一套新娘和新郎
共同的妆造。场景、灯光、姿势和身高等问题交给摄影师或小囍处理。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.common.config import settings
from app.common.errors import ModuleError
from app.contracts import Look
from app.modules.assets import search_assets
from app.state import Brief, WeddingState

PROMPTS = Path(__file__).parent / "prompts"
DEFAULT_STYLE = "keep_original"

# 资产库未准备好时的文字选项。每个套系都明确写出男女两人的造型，避免
# 兜底方案只描述新娘而让生图模型自行猜测新郎造型。
FALLBACK_STYLES = (
    ("chinese_red_gold", "中式红金"),
    ("korean_studio", "韩式影棚"),
    ("french_editorial", "法式 editorial"),
    ("forest", "森系"),
    ("retro", "复古"),
    ("cinematic", "电影感"),
    ("keep_original", "保留原图场景"),
)

FALLBACK_LOOK_SETS = {
    "chinese_red_gold": (
        ("look_set_chinese_red_gold_classic", "中式红金·经典", "新娘清透底妆与端庄红唇，利落低盘发，刺绣红金礼服与精致发饰；新郎干净短发，深色中式礼服与简洁胸针。"),
        ("look_set_chinese_red_gold_modern", "中式红金·现代", "新娘自然光泽妆、简洁盘发，现代剪裁红色礼服与小巧耳饰；新郎自然妆感，黑色立领礼服与低调胸针。"),
    ),
    "korean_studio": (
        ("look_set_korean_studio_satin", "韩式影棚·缎面", "新娘清透底妆、柔和眉眼与低盘发，缎面抹胸婚纱、长头纱和珍珠耳饰；新郎自然干净妆感、利落短发，黑色修身西装与白衬衫。"),
        ("look_set_korean_studio_lace", "韩式影棚·蕾丝", "新娘清透底妆与自然唇色，半扎发，细腻蕾丝长袖婚纱和小巧耳饰；新郎干净短发，深灰西装、白衬衫和简洁领结。"),
        ("look_set_korean_studio_minimal", "韩式影棚·极简", "新娘自然光泽妆、松弛低发髻，极简无装饰婚纱与细链耳饰；新郎自然妆感、整洁短发，纯黑西装与白衬衫。"),
    ),
    "french_editorial": (
        ("look_set_french_editorial_silk", "法式 editorial·真丝", "新娘自然有质感的底妆、松弛低发髻，简洁真丝婚纱与少量金属耳饰；新郎自然妆感、利落短发，深色剪裁西装与窄领带。"),
        ("look_set_french_editorial_clean", "法式 editorial·极简", "新娘轻薄底妆、自然微卷短发，线条简洁的婚纱与极简耳饰；新郎整洁短发，炭灰西装、白衬衫和低调腕表。"),
    ),
    "forest": (
        ("look_set_forest_flower", "森系·花意", "新娘清新柔和妆容、自然编发，轻盈婚纱与细小花材头饰；新郎自然妆感、蓬松短发，浅色西装与小花胸针。"),
        ("look_set_forest_linen", "森系·亚麻", "新娘淡雅底妆、松弛低马尾，轻薄婚纱与温和色彩耳饰；新郎干净短发，亚麻色西装与简洁胸花。"),
    ),
    "retro": (
        ("look_set_retro_wave", "复古·波浪", "新娘复古红唇与清晰轮廓，经典波浪发，复古剪裁婚纱与珍珠耳饰；新郎自然妆感、整洁侧分短发，深色复古西装与窄领带。"),
        ("look_set_retro_classic", "复古·经典", "新娘干净红唇、低盘发，经典礼服和小巧复古耳饰；新郎自然妆感、利落短发，黑色礼服与白色胸花。"),
    ),
    "cinematic": (
        ("look_set_cinematic_mono", "电影感·黑白", "新娘自然立体妆、低发髻，线条简洁的白色婚纱与克制耳饰；新郎自然妆感、利落短发，黑色西装与白衬衫。"),
        ("look_set_cinematic_warm", "电影感·暖调", "新娘柔和底妆、自然微卷发，质感缎面婚纱与细致耳饰；新郎自然妆感、整洁短发，深棕西装与简洁领带。"),
    ),
    "keep_original": (
        ("look_set_keep_original_classic", "保留原图·经典婚礼", "新娘保持原图五官与体型，采用自然妆容、整洁发型、简洁婚纱和克制配饰；新郎保持原图五官与体型，采用自然妆容、整洁短发、经典西装和简洁胸花。"),
        ("look_set_keep_original_natural", "保留原图·自然", "新娘保持原图发型基础与真实质感，加入轻薄妆容、简洁婚纱和小巧配饰；新郎保持原图发型基础与真实质感，加入自然妆容、干净西装和简洁胸花。"),
    ),
}

# 用户描述中的常见风格说法，用于判断是否可以跳过第一轮风格问题。
STYLE_ALIASES = {
    "korean_studio": ("韩式", "韩国", "korean", "影棚"),
    "chinese_red_gold": ("中式", "红金", "国风"),
    "french_editorial": ("法式", "法风", "editorial"),
    "forest": ("森系", "自然", "花园"),
    "retro": ("复古", "retro"),
    "cinematic": ("电影感", "电影", "cinematic"),
    "keep_original": ("原图", "保持原样", "保留原图"),
}


def available_styles() -> list[str]:
    """返回已提供风格模板的编号，供模块测试和管理工具使用。"""

    return sorted(path.stem for path in PROMPTS.glob("*.md") if path.stem != "agent")


def style(state: WeddingState) -> dict:
    """生成妆造方案；fake 分支完全本地运行，真实分支使用通用 agent。"""

    if settings.fake_for("styling"):
        return _build_look(state)
    try:
        context = _selection_context(state)
        prompt = _render_agent_prompt(context)
        raw = _invoke_agent(prompt)
        look = _normalise_look(raw, context)
        return _with_questions(state, context, look)
    except ModuleError:
        raise
    except Exception as error:
        raise ModuleError("GENERATION_FAILED", "妆造师暂时无法生成方案，请稍后再试") from error


def _build_look(state: WeddingState) -> dict:
    context = _selection_context(state)
    look = _normalise_look(None, context)
    return _with_questions(state, context, look)


def _selection_context(state: WeddingState) -> dict[str, Any]:
    try:
        brief = Brief(**state.get("brief", {}))
    except Exception as error:
        raise ModuleError("PHOTO_INVALID", "需求单还不完整，暂时无法设计妆造") from error

    answers = [
        item for item in state.get("answers", [])
        if item.get("asker") == "styling"
    ]
    q_answers = {item.get("question_id"): item for item in answers if item.get("question_id")}
    description = str(state.get("description") or "").strip()

    style_assets = _load_assets("style")
    style_options = _style_options(style_assets)
    clear_style = _description_style(description, style_options)
    style_answer = q_answers.get("q_style")
    style_id = _answer_style(style_answer, style_options)
    if not style_id:
        style_id = clear_style or style_options[0]["value"]

    look_assets = _load_assets("look_set", [style_id])
    look_options, look_meta = _look_options(style_id, look_assets)
    look_answer = q_answers.get("q_look_set")
    look_id = _answer_value(look_answer, {item["value"] for item in look_options})
    if not look_id:
        look_id = look_options[0]["value"]

    selected_style = next((item for item in style_options if item["value"] == style_id), style_options[0])
    selected_look = look_meta.get(look_id, {})
    return {
        "brief": brief,
        "description": description,
        "answers": q_answers,
        "style_options": style_options,
        "look_options": look_options,
        "style_id": style_id,
        "style_choice": selected_style,
        "look_id": look_id,
        "look_choice": selected_look,
        "clear_style": bool(clear_style),
        "retouch_plan": state.get("retouch_plan") or {},
        "candidates": bool(state.get("candidates")),
    }


def _load_assets(kind: str, tags: list[str] | None = None) -> list[dict]:
    """资产库未支持某种类时视为空库；资产库错误不应阻塞对话。"""

    try:
        assets = search_assets(kind, tags)
    except Exception:
        return []
    return [dict(item) for item in assets if isinstance(item, dict)]


def _style_options(assets: list[dict]) -> list[dict]:
    options = []
    for item in assets:
        asset_id = str(item.get("asset_id") or "")
        if not asset_id:
            continue
        value = asset_id.removeprefix("style_")
        options.append({"value": value, "label": str(item.get("name") or value), "image": item.get("url")})
    if options:
        return options
    return [{"value": value, "label": label, "image": None} for value, label in FALLBACK_STYLES]


def _look_options(style_id: str, assets: list[dict]) -> tuple[list[dict], dict[str, dict]]:
    options: list[dict] = []
    meta: dict[str, dict] = {}
    for item in assets[:3]:
        asset_id = str(item.get("asset_id") or "")
        if not asset_id:
            continue
        option = {
            "value": asset_id,
            "label": str(item.get("name") or asset_id),
            "image": item.get("url"),
        }
        options.append(option)
        meta[asset_id] = item
    if options:
        return options, meta
    fallback = FALLBACK_LOOK_SETS.get(style_id, FALLBACK_LOOK_SETS[DEFAULT_STYLE])
    for asset_id, label, description in fallback[:3]:
        options.append({"value": asset_id, "label": label, "image": None})
        meta[asset_id] = {"asset_id": asset_id, "name": label, "description": description, "url": None}
    return options, meta


def _description_style(description: str, options: list[dict]) -> str | None:
    if not description:
        return None
    lowered = description.casefold()
    for option in options:
        value = option["value"]
        aliases = STYLE_ALIASES.get(value, ())
        if any(alias.casefold() in lowered for alias in aliases):
            return value
        if value.casefold() in lowered or option["label"].casefold() in lowered:
            return value
    return None


def _answer_style(answer: dict | None, options: list[dict]) -> str | None:
    if not answer or answer.get("skipped"):
        return None
    value = answer.get("value")
    if isinstance(value, list):
        value = value[0] if value else None
    value = str(value or "")
    value = value.removeprefix("style_")
    return next((item["value"] for item in options if item["value"] == value), None)


def _answer_value(answer: dict | None, allowed: set[str]) -> str | None:
    if not answer or answer.get("skipped"):
        return None
    value = answer.get("value")
    if isinstance(value, list):
        value = value[0] if value else None
    value = str(value or "")
    return value if value in allowed else None


def _answered(answer: dict | None) -> bool:
    """跳过也算回答；这保证用户不选时仍能进入下一轮。"""

    return bool(answer is not None)


def _pending_questions(state: WeddingState, context: dict[str, Any]) -> list[dict]:
    plan = context["retouch_plan"]
    if context["candidates"] or plan.get("target") == "look":
        return []
    rounds = (state.get("question_rounds") or {}).get("styling", 0)
    if rounds >= settings.max_question_rounds:
        return []
    answers = context["answers"]
    # 已明确的描述相当于回答了风格问题，直接进入第二轮。
    if not context["clear_style"] and not _answered(answers.get("q_style")):
        return [_style_question(context["style_options"])]
    if not _answered(answers.get("q_look_set")):
        return [_look_question(context["look_options"])]
    return []


def _style_question(options: list[dict]) -> dict:
    return {
        "question_id": "q_style",
        "type": "single_choice",
        "title": "你喜欢哪种婚礼风格？",
        "options": options,
        "recommended": options[0]["value"],
        "allow_skip": True,
    }


def _look_question(options: list[dict]) -> dict:
    return {
        "question_id": "q_look_set",
        "type": "single_choice",
        "title": "想选哪一套新娘和新郎的妆造？",
        "options": options,
        "recommended": options[0]["value"],
        "allow_skip": True,
    }


def _with_questions(state: WeddingState, context: dict[str, Any], look: dict) -> dict:
    update = {"look": look}
    questions = _pending_questions(state, context)
    if questions:
        update["questions"] = questions
        if questions[0]["question_id"] == "q_style":
            update["step_text"] = "我是妆造师，先确认你们喜欢的婚礼风格。"
        else:
            update["step_text"] = "我是妆造师，按这个风格准备了几套新娘和新郎一起的妆造，请选一套。"
    return update


def _render_agent_prompt(context: dict[str, Any]) -> str:
    template = (PROMPTS / "agent.md").read_text(encoding="utf-8")
    style_id = context["style_id"]
    style_file = PROMPTS / f"{style_id}.md"
    style_template = style_file.read_text(encoding="utf-8").strip() if style_file.is_file() else ""
    fields = {
        "style_id": style_id,
        "style_template": style_template,
        "look_set_description": str(context["look_choice"].get("description") or ""),
        "keep_features": "、".join(context["brief"].keep_features),
        "beautify": context["brief"].beautify,
        "retouch_patch": context["retouch_plan"].get("patch", "") if context["retouch_plan"].get("target") == "look" else "",
        "user_description": context["description"],
    }
    try:
        return template.format_map(fields)
    except (KeyError, ValueError) as error:
        raise ModuleError("GENERATION_FAILED", "妆造师提示词配置有误，请联系开发者") from error


def _invoke_agent(prompt: str) -> Any:
    """使用通用 agent，并把 search_assets 作为唯一工具，严格限制轮数。"""

    from langchain_core.messages import HumanMessage, ToolMessage
    from langchain_core.tools import StructuredTool

    from app.common.llm import get_llm

    if settings.max_agent_steps < 1:
        raise ModuleError("GENERATION_FAILED", "妆造师暂时无法生成方案，请稍后再试")
    def asset_search(kind: str, tags: list[str] | None = None) -> list[dict]:
        return _load_assets(kind, list(tags or []))

    tool = StructuredTool.from_function(
        asset_search,
        name="search_assets",
        description="查找婚纱馆已登记的 style 或 look_set 参考素材。",
    )
    llm = get_llm("agent")
    messages: list[Any] = [HumanMessage(content=prompt)]
    for _ in range(settings.max_agent_steps):
        response = llm.bind_tools([tool]).invoke(messages)
        messages.append(response)
        calls = (getattr(response, "tool_calls", []) or [])[:1]
        if not calls:
            break
        for call in calls:
            try:
                result = tool.invoke(call.get("args", {}))
            except Exception as error:
                result = {"error": str(error)}
            messages.append(ToolMessage(content=json.dumps(result, ensure_ascii=False), tool_call_id=call["id"]))
    return llm.with_structured_output(Look).invoke(messages)


def _normalise_look(result: Any, context: dict[str, Any]) -> dict:
    if isinstance(result, Look):
        raw = result.model_dump()
    elif isinstance(result, dict):
        raw = result
    elif hasattr(result, "model_dump"):
        raw = result.model_dump()
    else:
        raw = {}

    brief: Brief = context["brief"]
    style_id = context["style_id"]
    style_file = PROMPTS / f"{style_id}.md"
    style_template = style_file.read_text(encoding="utf-8").strip() if style_file.is_file() else ""
    set_description = str(context["look_choice"].get("description") or "")
    text = str(raw.get("text") or "").strip()
    if not text:
        text = "；".join(part for part in (style_template, set_description) if part)
    if not text:
        text = str(context["style_choice"].get("label") or style_id)
    user_description = context["description"]
    if user_description and user_description not in text:
        text += f"用户描述中的要求：{user_description}。"
    # 这些约束由妆造师代码补齐，防止模型或兜底模板漏写其中一人。
    if "新娘" not in text or "新郎" not in text:
        text = f"{text}；{set_description}" if set_description else text
    if brief.keep_features:
        keep = "、".join(brief.keep_features)
        if keep not in text:
            text += f"必须保留：{keep}。"
    if brief.beautify != "light":
        guard = "保持真实年龄和五官，不瘦身、不改脸型、不年轻化。"
        if guard not in text:
            text += guard
    plan = context["retouch_plan"]
    patch = str(plan.get("patch") or "") if plan.get("target") == "look" else ""
    if patch and patch not in text:
        text += f"调整：{patch}。"

    references = []
    style_image = context["style_choice"].get("image")
    look_image = context["look_choice"].get("url") or context["look_choice"].get("image")
    if look_image:
        references.append({"url": look_image, "role": "outfit"})
    if style_image:
        references.append({"url": style_image, "role": "style"})
    return {"text": text, "style": style_id, "references": references}
