"""妆造师（agent）：负责妆容、发型、服饰、配饰，写出造型描述 look。

在小囍之后、摄影师之前上场：先从资产库按分类找参考图（search_assets），以妆造师身份展示给用户，
用 questions 和用户确认妆容、发型、服饰、配饰，确认后写 look。框架负责暂停、收集回答，回答后再调用一次本函数。
每次调用都要返回一版 look（还在问问题时给的是按推荐选项写的草稿）。
fake 模式用下面的模板填空版；真实实现通过统一的大模型入口生成结构化方案。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.common.config import settings
from app.common.errors import ModuleError
from app.modules.assets import search_assets
from app.contracts import Look
from app.state import Brief, WeddingState

PROMPTS = Path(__file__).parent / "prompts"
DEFAULT_STYLE = "keep_original"
# 资产库里还没有物料时，用文字选项兜底
FALLBACK_OPTIONS = {
    "style": [
        ("chinese_red_gold", "中式红金"),
        ("korean_studio", "韩式影棚"),
        ("french_editorial", "法式 editorial"),
        ("forest", "森系"),
        ("retro", "复古"),
        ("cinematic", "电影感"),
        ("keep_original", "保留原图场景"),
    ],
    "makeup": [("natural", "自然淡妆"), ("korean", "清透韩妆"), ("retro", "复古红唇")],
    "outfit": [("satin", "缎面抹胸婚纱"), ("lace", "蕾丝长袖婚纱"), ("mermaid", "鱼尾拖尾婚纱")],
    "hair": [("low_bun", "低盘发"), ("half_up", "温柔半扎发"), ("waves", "自然大波浪")],
    "accessories": [("pearl", "珍珠耳饰"), ("veil", "长头纱与简洁头饰"), ("bouquet", "白色花束与细致胸花")],
}


def available_styles() -> list[str]:
    # agent.md 是妆造师系统提示词，不是可选婚礼风格。
    return sorted(path.stem for path in PROMPTS.glob("*.md") if path.stem != "agent")


def style(state: WeddingState) -> dict:
    if settings.fake_for("styling"):
        return _template_look(state)
    return _agent_look(state)


def _agent_look(state: WeddingState) -> dict:
    """让妆造师模型产出一版可执行的造型方案。

    物料检索在模型调用之前完成，模型只能从传入的选项中引用参考图。这样既满足
    妆造师可以使用资产库工具的约定，也避免模型自由编造外链。第一次调用会返回
    推荐草稿和问题；回答过问题或进入修图流程时只返回方案，不再打断用户。
    """

    # 当前妆造流程只需一次结构化模型调用；仍遵守全局 agent 步数上限，避免
    # 配置为 0 时意外发起付费请求。后续若增加工具循环，应在这里递增并检查该值。
    if settings.max_agent_steps < 1:
        raise ModuleError("GENERATION_FAILED", "妆造师暂时无法生成方案，请稍后再试")
    try:
        brief = Brief(**state.get("brief", {}))
    except Exception as error:
        raise ModuleError("PHOTO_INVALID", "需求单还不完整，暂时无法设计妆造") from error

    # 需求单里的风格编号必须原样写回 look；没有专属模板时只借用默认模板生成文字。
    style_id = brief.style or DEFAULT_STYLE
    questions = _questions(style_id, extended=_extended_style_mode(state))
    answers = {
        item["question_id"]: item
        for item in state.get("answers", [])
        if item.get("asker") == "styling"
    }
    selected = {question["question_id"]: _choose(question, answers.get(question["question_id"])) for question in questions}
    makeup, outfit = selected["q_makeup"], selected["q_outfit"]
    style_options = _options("style", style_id)
    hair = selected.get("q_hair")
    accessories = selected.get("q_accessories")
    choices = {
        "makeup": makeup,
        "outfit": outfit,
        "hair": hair,
        "accessories": accessories,
        "style_options": style_options,
        "style_choice": next((item for item in style_options if item["value"] == style_id), style_options[0]),
        "makeup_options": questions[0]["options"],
        "outfit_options": questions[1]["options"],
    }
    prompt = _render_agent_prompt(brief, style_id, choices, state.get("retouch_plan"))
    try:
        result = _invoke_agent(prompt)
    except Exception as error:
        # 不把上游的密钥、请求体或照片地址传给用户；详细堆栈由 runner 记录。
        raise ModuleError("GENERATION_FAILED", "妆造师暂时无法生成方案，请稍后再试") from error

    look = _normalise_look(result, style_id, choices, brief, state.get("retouch_plan"))
    # 已经回答过妆造问题，或流程正在修图，不再重复打断用户。
    if answers or state.get("candidates") or (state.get("retouch_plan") or {}).get("target") == "look":
        return {"look": look}
    return {
        "look": look,
        "questions": questions,
        "step_text": "我是妆造师，按你们选的风格挑了几款妆容和婚纱，选一个最喜欢的吧。",
    }


def _render_agent_prompt(
    brief: Brief,
    style_id: str,
    choices: dict[str, Any],
    retouch_plan: dict | None,
) -> str:
    """把需求渲染进提示词文件，不在代码中硬编码模型提示词。"""

    template = (PROMPTS / "agent.md").read_text(encoding="utf-8")
    fields = {key: value for key, value in brief.model_dump().items()}
    fields.update(
        style_id=style_id,
        makeup_choice=choices["makeup"]["label"],
        outfit_choice=choices["outfit"]["label"],
        makeup_options=_format_options(choices["makeup_options"]),
        outfit_options=_format_options(choices["outfit_options"]),
        hair_choice=_choice_label(choices.get("hair")),
        accessories_choice=_choice_label(choices.get("accessories")),
        retouch_patch=(retouch_plan or {}).get("patch", "") if (retouch_plan or {}).get("target") == "look" else "",
        style_options=_format_options(choices.get("style_options", [])),
        style_choice=(choices.get("style_choice") or {}).get("label", style_id),
    )
    # agent.md 仅允许使用需求单字段名作为占位符；未知字段直接报错，避免静默丢约束。
    try:
        return template.format_map(fields)
    except (KeyError, ValueError) as error:
        raise ModuleError("GENERATION_FAILED", "妆造师提示词配置有误，请联系开发者") from error


def _format_options(options: list[dict]) -> str:
    return "、".join(
        f"{item.get('value', '')}:{item.get('label', '')}"
        for item in options
        if item.get("value") and item.get("label")
    )


def _choice_label(choice: dict | list[dict] | None) -> str:
    if isinstance(choice, list):
        return "、".join(item.get("label", "") for item in choice if item.get("label"))
    return (choice or {}).get("label", "")


def _get_llm(kind: str):
    """延迟导入模型 SDK，保证 fake 模式不要求配置模型依赖。"""

    from app.common.llm import get_llm

    return get_llm(kind)


def _invoke_agent(prompt: str) -> Any:
    """Run a bounded asset-tool turn, then request the structured look.

    The preselected options are still supplied in the prompt so the fake and real
    paths are deterministic. The tool binding lets a real model request a fresh
    tagged asset list without giving it arbitrary network access.
    """

    from langchain_core.messages import HumanMessage, ToolMessage
    from langchain_core.tools import StructuredTool

    llm = _get_llm("agent")
    asset_tool = StructuredTool.from_function(
        search_assets,
        name="search_assets",
        description="按 kind（style、makeup、outfit）和 tags 查找已登记的婚纱馆参考图。",
    )
    messages: list[Any] = [HumanMessage(content=prompt)]
    for _ in range(settings.max_agent_steps):
        response = llm.bind_tools([asset_tool]).invoke(messages)
        messages.append(response)
        # 每一轮只执行一个工具调用，确保总工具调用数不超过配置上限。
        calls = (getattr(response, "tool_calls", []) or [])[:1]
        if not calls:
            break
        for call in calls:
            try:
                result = asset_tool.invoke(call.get("args", {}))
            except Exception as error:
                result = {"error": str(error)}
            messages.append(ToolMessage(content=json.dumps(result, ensure_ascii=False), tool_call_id=call["id"]))
    return llm.with_structured_output(Look).invoke(messages)


def _normalise_look(
    result: Any,
    style_id: str,
    choices: dict[str, Any],
    brief: Brief,
    retouch_plan: dict | None,
) -> dict:
    """校验并收敛模型返回，确保只引用资产库中已登记的图片。"""

    if isinstance(result, Look):
        raw = result.model_dump()
    elif isinstance(result, dict):
        raw = result
    elif hasattr(result, "model_dump"):
        raw = result.model_dump()
    else:
        raw = {}

    text = str(raw.get("text") or "").strip()
    if not text:
        # 结构化输出偶尔会漏掉 text，使用已确认的模板仍能安全继续流程。
        fields = {key: value for key, value in brief.model_dump().items() if isinstance(value, str)}
        fields.update(makeup=choices["makeup"]["label"], outfit_bride=choices["outfit"]["label"])
        if choices.get("hair"):
            fields["hair"] = _choice_label(choices["hair"])
        if choices.get("accessories"):
            fields["accessories"] = _choice_label(choices["accessories"])
        template_style = style_id if (PROMPTS / f"{style_id}.md").is_file() else DEFAULT_STYLE
        text = (PROMPTS / f"{template_style}.md").read_text(encoding="utf-8").strip().format_map(fields)
        if template_style != style_id:
            text = f"婚礼风格：{style_id}。" + text
        if choices.get("hair"):
            text += f"发型：{_choice_label(choices['hair'])}。"
        if choices.get("accessories"):
            text += f"配饰：{_choice_label(choices['accessories'])}。"
    else:
        if choices.get("hair") and choices["hair"]["label"] not in text:
            text += f"发型：{choices['hair']['label']}。"
        if choices.get("accessories") and choices["accessories"]["label"] not in text:
            text += f"配饰：{choices['accessories']['label']}。"
    if brief.keep_features:
        text += f"保留：{'、'.join(brief.keep_features)}。"
    if brief.beautify != "light":
        text += "保持真实年龄与五官，不瘦身、不改变脸型，不做年轻化处理。"
    if retouch_plan and retouch_plan.get("target") == "look" and retouch_plan.get("patch"):
        text += f"调整：{retouch_plan['patch']}。"

    selected_options = (
        (choices["makeup"], "makeup"),
        (choices["outfit"], "outfit"),
        (choices.get("style_choice") or {}, "style"),
    )
    allowed_by_role = {
        role: option.get("image")
        for option, role in selected_options
        if option.get("image")
    }
    references = []
    for reference in raw.get("references") or []:
        if not isinstance(reference, dict):
            continue
        url, role = reference.get("url"), reference.get("role")
        if role in allowed_by_role and url == allowed_by_role[role]:
            item = {"url": url, "role": role}
            if item not in references:
                references.append(item)
    # 如果模型没返回参考图，使用用户实际选择的资产，保证方案与问题答案一致。
    for option, role in selected_options:
        if option.get("image"):
            item = {"url": option["image"], "role": role}
            if item not in references:
                references.append(item)
    return {"text": text, "style": style_id, "references": references}


def _options(kind: str, style_id: str) -> list[dict]:
    if kind not in {"style", "makeup", "outfit"}:
        return [{"value": value, "label": label, "image": None} for value, label in FALLBACK_OPTIONS[kind]]
    assets = search_assets(kind, [style_id])[:4]
    if assets:
        return [{"value": item["asset_id"], "label": item["name"], "image": item["url"]} for item in assets]
    return [{"value": value, "label": label, "image": None} for value, label in FALLBACK_OPTIONS[kind]]


def _questions(style_id: str, *, extended: bool = False) -> list[dict]:
    makeup, outfit = _options("makeup", style_id), _options("outfit", style_id)
    questions = [
        {"question_id": "q_makeup", "type": "single_choice", "title": "想要什么样的妆容？", "options": makeup, "recommended": makeup[0]["value"], "allow_skip": True},
        {"question_id": "q_outfit", "type": "single_choice", "title": "婚纱想要哪种款式？", "options": outfit, "recommended": outfit[0]["value"], "allow_skip": True},
    ]
    if extended:
        hair = _options("hair", style_id)
        accessories = _options("accessories", style_id)
        questions.extend([
            {"question_id": "q_hair", "type": "single_choice", "title": "喜欢哪种发型？", "options": hair, "recommended": hair[0]["value"], "allow_skip": True},
            {"question_id": "q_accessories", "type": "multi_choice", "title": "需要哪些配饰？", "options": accessories, "recommended": [accessories[0]["value"]], "allow_skip": True},
        ])
    return questions


def _choose(question: dict, answer: dict | None) -> dict | list[dict]:
    """用户选了就用用户选的，跳过或没回答就用推荐项。"""
    if answer and not answer.get("skipped"):
        value = answer.get("value")
        values = value if isinstance(value, list) else [value]
        selected = [option for option in question["options"] if option["value"] in values]
        if selected:
            return selected if question["type"] == "multi_choice" else selected[0]
    recommended = question["recommended"]
    if isinstance(recommended, list):
        recommended = recommended[0] if recommended else None
    fallback = next(option for option in question["options"] if option["value"] == recommended)
    return [fallback] if question["type"] == "multi_choice" else fallback


def _template_look(state: WeddingState) -> dict:
    brief = Brief(**state.get("brief", {}))
    style_id = brief.style or DEFAULT_STYLE
    questions = _questions(style_id, extended=_extended_style_mode(state))
    style_options = _options("style", style_id)
    style_choice = next((item for item in style_options if item["value"] == style_id), style_options[0])
    answers = {item["question_id"]: item for item in state.get("answers", []) if item.get("asker") == "styling"}
    selected = {question["question_id"]: _choose(question, answers.get(question["question_id"])) for question in questions}
    makeup, outfit = selected["q_makeup"], selected["q_outfit"]
    hair, accessories = selected.get("q_hair"), selected.get("q_accessories")

    fields = {key: value for key, value in brief.model_dump().items() if isinstance(value, str)}
    fields.update(makeup=makeup["label"], outfit_bride=outfit["label"])
    if hair:
        fields["hair"] = _choice_label(hair)
    if accessories:
        fields["accessories"] = _choice_label(accessories)
    template_style = style_id if (PROMPTS / f"{style_id}.md").is_file() else DEFAULT_STYLE
    text = (PROMPTS / f"{template_style}.md").read_text(encoding="utf-8").strip().format_map(fields)
    if template_style != style_id:
        text = f"婚礼风格：{style_id}。" + text
    if hair:
        text += f"发型：{hair['label']}。"
    if accessories:
        text += f"配饰：{_choice_label(accessories)}。"
    if brief.keep_features:
        text += f"保留：{'、'.join(brief.keep_features)}。"
    plan = state.get("retouch_plan") or {}
    if plan.get("target") == "look" and plan.get("patch"):
        text += f"调整：{plan['patch']}。"

    references = [
        {"url": option["image"], "role": role}
        for option, role in ((style_choice, "style"), (makeup, "makeup"), (outfit, "outfit"))
        if option.get("image")
    ]
    look = {"text": text, "style": style_id, "references": references}
    if answers or state.get("candidates") or (state.get("retouch_plan") or {}).get("target") == "look":  # 已经和用户确认过，或已经在修图阶段：不再问
        return {"look": look}
    return {"look": look, "questions": questions, "step_text": "我是妆造师，按你们选的风格挑了几款妆容和婚纱，选一个最喜欢的吧。"}


def _extended_style_mode(state: WeddingState) -> bool:
    return "groom_photo_urls" in state or "bride_photo_urls" in state
