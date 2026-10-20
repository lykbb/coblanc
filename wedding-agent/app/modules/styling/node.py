"""妆造师 agent。

只和用户确认三件事：风格、妆容、衣服（新娘和新郎共用一个风格、一个妆容方向、一套婚纱 + 西装，选项见 choices.py），
再写出两人完整的妆容、发型、服装、配饰方案。场景、灯光、姿势和身高交给摄影师或小囍。
第 1 轮问风格（描述里已说清风格就跳过），第 2 轮同时问妆容和衣服。
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

from . import choices

PROMPTS = Path(__file__).parent / "prompts"
OPTION_KEYS = ("value", "label", "image", "description")  # 发给用户的选项只带这几个键


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


def selections(state: WeddingState) -> dict[str, Any]:
    """按已回答内容（没答或跳过用推荐项）得出风格、妆容、衣服。妆造师和前端画布（api._plan）共用。"""

    answers = {item.get("question_id"): item for item in state.get("answers", [])
               if item.get("asker") == "styling" and item.get("question_id")}
    description = str(state.get("description") or "").strip()
    style_options = _style_options(_load_assets("style"))
    clear_style = _description_style(description, style_options)
    style_id = _answer_value(answers.get("q_style"), {o["value"] for o in style_options}, strip="style_") \
        or clear_style or _answer_value({"value": (state.get("look") or {}).get("style")}, {o["value"] for o in style_options}) \
        or style_options[0]["value"]
    makeup_options = choices.makeup_options(style_id)
    makeup_id = _answer_value(answers.get("q_makeup"), {o["value"] for o in makeup_options}) or makeup_options[0]["value"]
    outfit_options = choices.outfit_options(style_id, _load_assets("outfit", [style_id]))
    outfit_ids = {o["value"] for o in outfit_options}
    legacy = answers.get("q_look_set")  # 老任务：选过整套妆造的，衣服沿用同名套装
    outfit_id = _answer_value(answers.get("q_outfit"), outfit_ids) \
        or (legacy and _answer_value({"value": choices.legacy_outfit(str(legacy.get("value") or ""))}, outfit_ids)) \
        or outfit_options[0]["value"]
    return {
        "answers": answers, "description": description, "clear_style": bool(clear_style),
        "style_id": style_id, "style_options": style_options,
        "style_choice": next(o for o in style_options if o["value"] == style_id),
        "makeup_options": makeup_options, "makeup": choices.makeup_detail(makeup_id),
        "outfit_options": outfit_options, "outfit": next(o for o in outfit_options if o["value"] == outfit_id),
    }


def _selection_context(state: WeddingState) -> dict[str, Any]:
    try:
        brief = Brief(**state.get("brief", {}))
    except Exception as error:
        raise ModuleError("PHOTO_INVALID", "需求单还不完整，暂时无法设计妆造") from error
    return {**selections(state), "brief": brief,
            "retouch_plan": state.get("retouch_plan") or {}, "candidates": bool(state.get("candidates"))}


def _load_assets(kind: str, tags: list[str] | None = None) -> list[dict]:
    """资产库出错或还没放图时视为空库；资产库错误不应阻塞对话。"""

    try:
        assets = search_assets(kind, tags)
    except Exception:
        return []
    return [dict(item) for item in assets if isinstance(item, dict)]


def _style_options(assets: list[dict]) -> list[dict]:
    images = {str(item.get("asset_id") or "").removeprefix("style_"): item.get("url") for item in assets}
    return [choices.style_option(style_id, images.get(style_id)) for style_id in choices.style_ids()]


def _description_style(description: str, options: list[dict]) -> str | None:
    if not description:
        return None
    lowered = description.casefold()
    for option in options:
        value = option["value"]
        aliases = choices.STYLE_ALIASES.get(value, ())
        if any(alias.casefold() in lowered for alias in aliases):
            return value
        if value.casefold() in lowered or option["label"].casefold() in lowered:
            return value
    return None


def _answer_value(answer: dict | None, allowed: set[str], strip: str = "") -> str | None:
    if not answer or answer.get("skipped"):
        return None
    value = answer.get("value")
    if isinstance(value, list):
        value = value[0] if value else None
    value = str(value or "").removeprefix(strip)
    return value if value in allowed else None


def _pending_questions(state: WeddingState, context: dict[str, Any]) -> list[dict]:
    plan = context["retouch_plan"]
    if context["candidates"] or plan.get("target") == "look":
        return []
    rounds = (state.get("question_rounds") or {}).get("styling", 0)
    if rounds >= settings.max_question_rounds:
        return []
    answers = context["answers"]  # 跳过也算回答（用推荐项）
    # 描述里已说清风格相当于回答了风格题，直接问妆容和衣服。
    if not context["clear_style"] and "q_style" not in answers:
        return [_question("q_style", "你们喜欢哪种婚礼风格？", context["style_options"])]
    if "q_look_set" in answers:  # 老任务已经选过整套妆造，不再追问
        return []
    pending = [("q_makeup", "选一个妆容方向", context["makeup_options"]),
               ("q_outfit", "选一套婚纱和西装", context["outfit_options"])]
    return [_question(qid, title, options) for qid, title, options in pending if qid not in answers]


def _question(question_id: str, title: str, options: list[dict]) -> dict:
    return {
        "question_id": question_id,
        "type": "single_choice",
        "title": title,
        "options": [{key: option.get(key) for key in OPTION_KEYS} for option in options],
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
            update["step_text"] = "我是妆造师，按这个风格挑了几个妆容方向和几套婚纱西装，各选一个吧。"
    return update


def _render_agent_prompt(context: dict[str, Any]) -> str:
    template = (PROMPTS / "agent.md").read_text(encoding="utf-8")
    style_id = context["style_id"]
    style_file = PROMPTS / f"{style_id}.md"
    style_template = style_file.read_text(encoding="utf-8").strip() if style_file.is_file() else ""
    fields = {
        "style_id": style_id,
        "style_template": style_template,
        "makeup": _makeup_text(context["makeup"]),
        "makeup_notes": "；".join(context["makeup"]["bride_notes"] + context["makeup"]["groom_notes"]) or "无",
        "makeup_notes": "；".join(context["makeup"]["bride_notes"] + context["makeup"]["groom_notes"]) or "无",
        "outfit": _outfit_text(context["outfit"]),
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
        description="查找婚纱馆已登记的 style 或 outfit 参考素材。",
    )
    llm = get_llm("agent")
    messages: list[Any] = [HumanMessage(content=prompt)]
    for _ in range(settings.max_agent_steps):
        response = llm.bind_tools([tool]).invoke(messages)
        messages.append(response)
        calls = getattr(response, "tool_calls", []) or []
        if not calls:
            break
        for call in calls:
            try:
                result = tool.invoke(call.get("args", {}))
            except Exception as error:
                result = {"error": str(error)}
            messages.append(ToolMessage(content=json.dumps(result, ensure_ascii=False), tool_call_id=call["id"]))
    # 最后一步只给 Look 一个工具，历史里不能再有 search_assets 的调用记录，
    # 否则模型会接着调 search_assets，解析器报 "Unknown tool type"。查到的素材以文字交给它。
    found = [m.content for m in messages if isinstance(m, ToolMessage)]
    final = prompt + "\n\n已查到的素材（JSON）：\n" + "\n".join(found) + "\n\n素材已经查完，现在直接给出最终方案。"
    return llm.with_structured_output(Look).invoke([HumanMessage(content=final)])


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
    chosen = f"{_makeup_text(context['makeup'])}；{_outfit_text(context['outfit'])}"
    text = str(raw.get("text") or "").strip()
    if not text:
        text = "；".join(part for part in (style_template, chosen) if part)
    user_description = context["description"]
    if user_description and user_description not in text:
        text += f"用户描述中的要求：{user_description}。"
    # 这些约束由妆造师代码补齐，防止模型或兜底模板漏写其中一人。
    if "新娘" not in text or "新郎" not in text:
        text = f"{text}；{chosen}"
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
    outfit_image = context["outfit"].get("image")
    if outfit_image:
        references.append({"url": outfit_image, "role": "outfit"})
    if style_image:
        references.append({"url": style_image, "role": "style"})
    return {"text": text, "style": style_id, "references": references}


def _makeup_text(makeup: dict) -> str:
    return f"妆容方向「{makeup['label']}」：新娘{makeup['bride']}，新郎{makeup['groom']}"


def _outfit_text(outfit: dict) -> str:
    if outfit.get("groom"):
        return f"衣服「{outfit['label']}」：新娘{outfit['bride']}，新郎{outfit['groom']}"
    return f"衣服「{outfit['label']}」：{outfit.get('description') or outfit['label']}"
