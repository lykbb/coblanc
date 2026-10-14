"""主 Agent（小囍）：接单、汇总方案和揭幕。

本模块保留仓库原有的单张合照兼容路径，同时支持新契约里的新郎/新娘分组照片。
照片分组、授权确认和照片质量检查都在接单阶段完成；造型、场景和灯光分别交给
妆造师和摄影师，避免主 Agent 重复追问。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.common.config import settings
from app.common.errors import ModuleError
from app.contracts import Reference
from app.state import Brief, WeddingState

PROMPTS = Path(__file__).parent / "prompts"


class PhotoCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    people_count: int = Field(ge=0)
    clear: bool
    front_facing: bool
    unobstructed: bool
    reason: str = ""


class ComposeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str
    references: list[Reference] = Field(default_factory=list)


class RevealResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str


STYLE_OPTIONS = [
    ("chinese_red_gold", "中式红金"),
    ("korean_studio", "韩式影棚"),
    ("french_editorial", "法式 editorial"),
    ("forest", "森系"),
    ("retro", "复古"),
    ("cinematic", "电影感"),
    ("keep_original", "保留原图场景"),
]
MATERIAL_OPTIONS = [
    ("photo", "婚纱照"),
    ("album", "相册"),
    ("invitation", "请柬"),
    ("welcome_poster", "迎宾海报"),
    ("seating_chart", "座位表"),
    ("led_screen", "婚礼大屏"),
    ("moments", "社交媒体封面"),
]
DEFAULT_CONSENT = {
    "authorization_scope": "generation_only",
    "retention_days": 7,
    "allow_training": False,
    "watermark": True,
    "delete_original": True,
    "confirmed": True,
}
CUSTOM_CONSENT = {
    **DEFAULT_CONSENT,
    # 自定义授权入口采用保守默认：仍可生成，但交付后保留原图，等待后续显式设置。
    "delete_original": False,
}

LEGACY_QUESTIONS = [
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
    return _real_intake(state)


def compose(state: WeddingState) -> dict:
    if settings.fake_for("intake"):
        return _fake_compose(state)
    brief = _brief(state)
    look = state.get("look") or {}
    shot = state.get("shot") or {}
    plan = state.get("retouch_plan") or {}
    fields = {
        "brief": json.dumps(brief.model_dump(), ensure_ascii=False),
        "look": str(look.get("text", "")),
        "shot": str(shot.get("text", "")),
        "photo_count": len(state.get("photo_urls") or []),
        "retouch_patch": str(plan.get("patch", "") if plan.get("target") == "prompt" else ""),
    }
    try:
        template = (PROMPTS / "compose.md").read_text(encoding="utf-8")
        message = template.format_map(_SafeFormat(fields))
        result = _get_llm("agent").with_structured_output(ComposeResult).invoke(message)
    except Exception as error:
        raise ModuleError("GENERATION_FAILED", "小囍暂时无法整理生图方案，请稍后再试") from error
    raw = result.model_dump() if hasattr(result, "model_dump") else result
    prompt = str(raw.get("prompt") or "").strip()
    if not prompt:
        raise ModuleError("GENERATION_FAILED", "小囍没有得到有效的生图提示词，请稍后再试")
    if plan.get("target") == "prompt" and plan.get("patch"):
        prompt = f"{prompt} 特别调整：{plan['patch']}。"
    references = _safe_references(raw.get("references"), look, shot)
    return {"prompt": prompt, "references": references[: settings.max_reference_images]}


def reveal(state: WeddingState) -> dict:
    if settings.fake_for("intake"):
        return {"message": "照片里你们笑得很自然，愿你们的婚礼也像这组照片一样，温柔又闪闪发光。"}
    brief = _brief(state)
    deliverables = state.get("deliverables") or {}
    invitation = brief.invitation or {}
    fields = {
        "names": str(invitation.get("names") or "你们"),
        "date": str(invitation.get("date") or ""),
        "place": str(invitation.get("place") or ""),
        "materials": ", ".join(str(key) for key in deliverables),
    }
    try:
        template = (PROMPTS / "reveal.md").read_text(encoding="utf-8")
        result = _get_llm("cheap").with_structured_output(RevealResult).invoke(template.format_map(_SafeFormat(fields)))
        raw = result.model_dump() if hasattr(result, "model_dump") else result
        text = str(raw.get("message") or "").strip()
    except Exception as error:
        raise ModuleError("GENERATION_FAILED", "小囍暂时无法写揭幕寄语，请稍后再试") from error
    return {"message": (text or f"愿{fields['names']}的婚礼温柔圆满。")[:50]}


def _real_intake(state: WeddingState) -> dict:
    answers = _answers(state)
    extended = _extended_mode(state)
    consent = _consent(state, answers)
    rounds = (state.get("question_rounds") or {}).get("intake", 0)
    if extended and consent is None:
        if rounds >= settings.max_question_rounds:
            raise ModuleError("PHOTO_INVALID", "请先确认照片授权范围后再开始生成")
        return {
            "brief": _brief_from_answers(state, answers, force_defaults=False).model_dump(),
            "questions": _questions(state, answers),
            "step_text": "我是小囍。开始前先确认照片授权和婚礼方向，照片只用于这次创作。",
        }
    _validate_photo_shape(state)
    _validate_photos_with_vision(state)
    brief = _brief_from_llm(state, answers)
    questions = _questions(state, answers)
    if rounds >= settings.max_question_rounds:
        brief = _brief_from_answers(state, answers, force_defaults=True)
        questions = []
    update: dict[str, Any] = {"brief": brief.model_dump(), "questions": questions}
    if consent is not None:
        update["consent"] = consent
    if questions:
        update["step_text"] = "我是小囍，你们这次拍摄的项目经理，再确认几项关键信息就可以交给妆造师了。"
    return update


def _fake_intake(state: WeddingState) -> dict:
    answers = _answers(state)
    if _extended_mode(state):
        consent = _consent(state, answers)
        rounds = (state.get("question_rounds") or {}).get("intake", 0)
        if consent is None and rounds >= settings.max_question_rounds:
            raise ModuleError("PHOTO_INVALID", "请先确认照片授权范围后再开始生成")
        brief = _brief_from_answers(state, answers, force_defaults=rounds >= settings.max_question_rounds)
        questions = [] if rounds >= settings.max_question_rounds else _questions(state, answers)
        update: dict[str, Any] = {"brief": brief.model_dump(), "questions": questions}
        if consent is not None:
            update["consent"] = consent
        if questions:
            update["step_text"] = "我是小囍，你们这次拍摄的项目经理，先确认风格、物料和照片授权。"
        return update
    if not answers:
        return {
            "questions": LEGACY_QUESTIONS,
            "brief": Brief(missing=["style", "heights_cm"]).model_dump(),
            "step_text": "我是小囍，你们这次拍摄的项目经理。先确认两件事，后面妆造师和摄影师还会跟你们细聊。",
        }
    brief = _brief_from_answers(state, answers, force_defaults=True)
    return {"questions": [], "brief": brief.model_dump()}


def _fake_compose(state: WeddingState) -> dict:
    look = state.get("look") or {}
    shot = state.get("shot") or {}
    plan = state.get("retouch_plan") or {}
    opening = (PROMPTS / "opening.md").read_text(encoding="utf-8").strip()
    parts = [opening, look.get("text", ""), shot.get("text", "")]
    if plan.get("target") == "prompt" and plan.get("patch"):
        parts.append(f"特别注意：{plan['patch']}。")
    refs = sorted(shot.get("references", []) + look.get("references", []), key=lambda ref: ref["role"] != "pose")
    unique = list({ref["url"]: ref for ref in refs}.values())
    return {"prompt": "".join(part for part in parts if part), "references": unique[: settings.max_reference_images]}


def _questions(state: WeddingState, answers: dict[str, dict]) -> list[dict]:
    if not _extended_mode(state):
        return [question for question in LEGACY_QUESTIONS if question["question_id"] not in answers]
    questions: list[dict] = []
    if "q_style" not in answers:
        questions.append({
            "question_id": "q_style",
            "type": "single_choice",
            "title": "想要哪种婚礼风格？",
            "options": [{"value": value, "label": label, "image": None} for value, label in STYLE_OPTIONS],
            "recommended": "korean_studio",
            "allow_skip": True,
        })
    if "q_materials" not in answers:
        questions.append({
            "question_id": "q_materials",
            "type": "multi_choice",
            "title": "这次需要生成哪些婚礼物料？",
            "options": [{"value": value, "label": label, "image": None} for value, label in MATERIAL_OPTIONS],
            "recommended": ["invitation", "welcome_poster", "led_screen"],
            "allow_skip": True,
        })
    if _consent(state, answers) is None:
        questions.append({
            "question_id": "q_consent",
            "type": "single_choice",
            "title": "是否同意照片仅用于本次生成？",
            "options": [
                {"value": "standard", "label": "同意标准授权：不用于训练，预览带水印，交付后删除原图", "image": None},
                {"value": "custom", "label": "自定义授权：交付后保留原图", "image": None},
            ],
            "recommended": "standard",
            "allow_skip": False,
        })
    return questions[:3]


def _answers(state: WeddingState) -> dict[str, dict]:
    return {
        item["question_id"]: item
        for item in state.get("answers", [])
        if item.get("asker", "intake") == "intake" and item.get("question_id")
    }


def _extended_mode(state: WeddingState) -> bool:
    return "groom_photo_urls" in state or "bride_photo_urls" in state or "consent" in state


def _consent(state: WeddingState, answers: dict[str, dict]) -> dict | None:
    existing = state.get("consent")
    if isinstance(existing, dict) and existing.get("confirmed"):
        return _normalise_consent(existing)
    answer = answers.get("q_consent")
    if not answer or answer.get("skipped"):
        return None
    value = answer.get("value")
    if value == "standard":
        return dict(DEFAULT_CONSENT)
    if value == "custom":
        return dict(CUSTOM_CONSENT)
    if isinstance(value, dict):
        merged = dict(DEFAULT_CONSENT)
        merged.update(value)
        merged["confirmed"] = True
        return _normalise_consent(merged)
    return None


def _normalise_consent(value: dict) -> dict:
    result = dict(DEFAULT_CONSENT)
    result.update({key: value[key] for key in DEFAULT_CONSENT if key in value})
    result["retention_days"] = max(0, int(result["retention_days"]))
    for key in ("allow_training", "watermark", "delete_original", "confirmed"):
        result[key] = bool(result[key])
    return result


def _brief_from_answers(state: WeddingState, answers: dict[str, dict], *, force_defaults: bool) -> Brief:
    style_answer = answers.get("q_style") or {}
    # 跳过选项时使用接口声明的推荐风格；不要把跳过静默解释成保留原图。
    style = style_answer.get("value") if not style_answer.get("skipped") else "korean_studio"
    valid_styles = {value for value, _ in STYLE_OPTIONS}
    if style not in valid_styles:
        style = "korean_studio" if force_defaults else "keep_original"
    material_answer = answers.get("q_materials") or {}
    materials = material_answer.get("value") if not material_answer.get("skipped") else None
    if isinstance(materials, str):
        materials = [materials]
    valid_materials = {value for value, _ in MATERIAL_OPTIONS}
    if not isinstance(materials, list):
        materials = ["invitation", "welcome_poster", "led_screen"]
    materials = [item for item in materials if item in valid_materials] or ["invitation", "welcome_poster", "led_screen"]
    heights = _parse_heights((answers.get("q_height") or {}).get("value"))
    if not heights and not _extended_mode(state) and not force_defaults:
        missing = ["style", "heights_cm"]
    else:
        missing = []
        if not force_defaults and "q_style" not in answers and _extended_mode(state):
            missing.append("style")
        if not force_defaults and "q_materials" not in answers and _extended_mode(state):
            missing.append("materials")
        if not force_defaults and "q_height" in answers and not heights:
            missing.append("heights_cm")
    return Brief(
        style=style,
        background="keep_original" if style == "keep_original" else "studio",
        heights_cm=heights,
        materials=materials,
        invitation={"names": "", "date": "", "place": ""},
        missing=missing,
    )


def _brief_from_llm(state: WeddingState, answers: dict[str, dict]) -> Brief:
    try:
        template = (PROMPTS / "brief.md").read_text(encoding="utf-8")
        message = template.format_map(_SafeFormat({
            "description": state.get("description", ""),
            "answers": json.dumps(list(answers.values()), ensure_ascii=False),
            "photo_groups": _photo_group_summary(state),
        }))
        result = _get_llm("agent").with_structured_output(Brief).invoke(message)
        brief = result if isinstance(result, Brief) else Brief(**(result.model_dump() if hasattr(result, "model_dump") else result))
    except Exception as error:
        raise ModuleError("GENERATION_FAILED", "小囍暂时无法整理需求，请稍后再试") from error
    fallback = _brief_from_answers(state, answers, force_defaults=False)
    source = _brief_source_text(state, answers)
    values = brief.model_dump()
    valid_styles = {value for value, _ in STYLE_OPTIONS}
    if values.get("style") not in valid_styles:
        values["style"] = fallback.style
    if values.get("background") not in {"keep_original", "studio"}:
        values["background"] = fallback.background
    # 模型不得凭空补充敏感事实；身高和姓名/日期/地点只接受用户输入中出现的值。
    values["heights_cm"] = fallback.heights_cm
    invitation = values.get("invitation") if isinstance(values.get("invitation"), dict) else {}
    values["invitation"] = {
        key: str(value).strip()
        for key, value in invitation.items()
        if key in {"names", "date", "place"} and value and str(value).strip() in source
    }
    values["keep_features"] = [
        str(item).strip()
        for item in values.get("keep_features", [])
        if str(item).strip() and str(item).strip() in source
    ]
    if values.get("beautify") == "light" and not any(token in source.lower() for token in ("light", "轻度美化", "轻微美化")):
        values["beautify"] = "none"
    values["missing"] = fallback.missing
    if not values.get("materials"):
        values["materials"] = fallback.materials
    return Brief(**values)


def _brief_source_text(state: WeddingState, answers: dict[str, dict]) -> str:
    """拼接用户可提供事实的原文，用于约束真实模型的敏感字段。"""

    answer_text = json.dumps(list(answers.values()), ensure_ascii=False)
    return f"{state.get('description', '')}\n{answer_text}"


def _photo_group_summary(state: WeddingState) -> str:
    groom = state.get("groom_photo_urls") or []
    bride = state.get("bride_photo_urls") or []
    if groom or bride:
        return f"新郎照片 {len(groom)} 张，新娘照片 {len(bride)} 张"
    return f"合照 {len(state.get('photo_urls') or [])} 张"


def _validate_photo_shape(state: WeddingState) -> None:
    groom = state.get("groom_photo_urls")
    bride = state.get("bride_photo_urls")
    if groom is not None or bride is not None:
        if not groom or not bride or not 1 <= len(groom) <= 10 or not 1 <= len(bride) <= 10:
            raise ModuleError("PHOTO_INVALID", "请分别上传新郎和新娘各 1～10 张正面生活照")
        return
    if not state.get("photo_urls"):
        raise ModuleError("PHOTO_INVALID", "请先上传照片")


def _validate_photos_with_vision(state: WeddingState) -> None:
    groups: list[tuple[str, list[str], int]] = []
    groom, bride = state.get("groom_photo_urls"), state.get("bride_photo_urls")
    if groom is not None or bride is not None:
        groups = [("新郎", groom or [], 1), ("新娘", bride or [], 1)]
    else:
        groups = [("合照", state.get("photo_urls") or [], 2)]
    template = (PROMPTS / "photo_check.md").read_text(encoding="utf-8")
    for label, urls, expected in groups:
        content: list[dict[str, Any]] = [{"type": "text", "text": template.format(label=label, expected=expected)}]
        content.extend({"type": "image_url", "image_url": {"url": url}} for url in urls)
        try:
            result = _get_llm("vision").with_structured_output(PhotoCheck).invoke([{"role": "user", "content": content}])
            check = result if isinstance(result, PhotoCheck) else PhotoCheck(**(result.model_dump() if hasattr(result, "model_dump") else result))
        except Exception as error:
            raise ModuleError("PHOTO_INVALID", f"{label}照片暂时无法完成质量检查，请换图重试") from error
        if check.people_count != expected or not check.clear or not check.front_facing or not check.unobstructed:
            reason = check.reason or "人数、清晰度、正脸或遮挡不符合要求"
            raise ModuleError("PHOTO_INVALID", f"{label}照片不合格：{reason}")


def _brief(state: WeddingState) -> Brief:
    try:
        return Brief(**state.get("brief", {}))
    except Exception as error:
        raise ModuleError("GENERATION_FAILED", "需求单格式不完整，无法继续") from error


def _safe_references(raw: Any, look: dict, shot: dict) -> list[dict]:
    allowed_urls = {
        item.get("url")
        for source in (look, shot)
        for item in (source.get("references") or [])
        if isinstance(item, dict) and item.get("url")
    }
    refs: list[dict] = []
    for item in raw or []:
        value = item.model_dump() if hasattr(item, "model_dump") else item
        if not isinstance(value, dict) or value.get("url") not in allowed_urls:
            continue
        if value.get("role") not in {"style", "outfit", "makeup", "pose", "background"}:
            continue
        ref = {"url": value["url"], "role": value["role"]}
        if ref not in refs:
            refs.append(ref)
    for source in (shot, look):
        for item in (source.get("references") or []):
            if isinstance(item, dict) and item.get("url") in allowed_urls and item not in refs:
                refs.append({"url": item["url"], "role": item["role"]})
    return sorted(refs, key=lambda ref: ref["role"] != "pose")


def _parse_heights(text: Any) -> list[int]:
    numbers = [int(n) for n in re.findall(r"\d{3}", str(text or ""))]
    return numbers[:2] if len(numbers) >= 2 else []


class _SafeFormat(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _get_llm(kind: str):
    """延迟导入模型 SDK，保证 fake 模式可以在无模型依赖时跑通。"""

    from app.common.llm import get_llm

    return get_llm(kind)
