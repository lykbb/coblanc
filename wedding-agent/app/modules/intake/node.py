"""小囍：只收集照片、授权和婚礼基础信息，并汇总专家方案。"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.common.config import settings
from app.common.errors import ModuleError
from app.contracts import Reference
from app.state import Brief, WeddingState

PROMPTS = Path(__file__).parent / "prompts"
SKILLS = Path(__file__).parent / "skills"
DIALOGUE = PROMPTS / "dialogue.md"
PHOTO_SORT = SKILLS / "photo_sort" / "SKILL.md"
IMAGE_PROMPT = SKILLS / "image_prompt" / "SKILL.md"


def load_section(path: Path, name: str) -> str:
    """读取 md 文件里 <!-- section: name --> 与 <!-- /section --> 之间的内容。"""
    text = path.read_text(encoding="utf-8")
    start = f"<!-- section: {name} -->"
    if start not in text:
        raise KeyError(f"{path.name} 缺少 section {name}")
    body = text.split(start, 1)[1].split("<!-- /section -->", 1)[0]
    return body.strip()


class PhotoCheckItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=1)
    people_count: int = Field(ge=0)
    clear: bool
    front_facing: bool
    unobstructed: bool
    reason: str = ""


class PhotoCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    results: list[PhotoCheckItem] = Field(default_factory=list)


class ComposeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str
    references: list[Reference] = Field(default_factory=list)


class RevealResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str


MATERIAL_OPTIONS = [
    ("invitation", "请柬"),
    ("welcome_poster", "迎宾海报"),
    ("led_screen", "婚礼大屏"),
]
DEFAULT_MATERIALS = [item[0] for item in MATERIAL_OPTIONS]
DEFAULT_CONSENT = {
    "authorization_scope": "generation_only",
    "retention_days": 7,
    "allow_training": False,
    "watermark": True,
    "delete_original": True,
    "confirmed": True,
}
KEEP_PHOTOS_CONSENT = {**DEFAULT_CONSENT, "delete_original": False}


def intake(state: WeddingState) -> dict:
    return _fake_intake(state) if settings.fake_for("intake") else _real_intake(state)


def compose(state: WeddingState) -> dict:
    brief = _brief(state)
    look, shot = state.get("look") or {}, state.get("shot") or {}
    plan = state.get("retouch_plan") or {}
    opening = load_section(IMAGE_PROMPT, "identity")
    if settings.fake_for("intake"):
        parts = [opening, str(look.get("text", "")), str(shot.get("text", ""))]
        if plan.get("target") == "prompt" and plan.get("patch"):
            parts.append(str(plan["patch"]))
        prompt = "".join(part for part in parts if part)
        return {"prompt": prompt, "references": _look_shot_refs(look, shot),
                "shot_prompts": _shot_prompts(prompt, state)}
    fields = {
        "brief": json.dumps(brief.model_dump(), ensure_ascii=False),
        "heights": json.dumps(brief.heights_cm, ensure_ascii=False),
        "look": str(look.get("text", "")),
        "shot": str(shot.get("text", "")),
        "retouch_patch": str(plan.get("patch", "") if plan.get("target") == "prompt" else ""),
    }
    try:
        template = load_section(IMAGE_PROMPT, "compose")
        result = _get_llm("agent").with_structured_output(ComposeResult).invoke(template.format_map(_SafeFormat(fields)))
        raw = result.model_dump() if hasattr(result, "model_dump") else result
        body = str(raw.get("prompt") or "").strip()
    except Exception as error:
        raise ModuleError("GENERATION_FAILED", "小囍暂时无法整理生图方案，请稍后再试") from error
    if not body:
        raise ModuleError("GENERATION_FAILED", "小囍没有得到有效的生图提示词，请稍后再试")
    if body.startswith(opening):
        body = body[len(opening):].lstrip()
    prompt = opening + body
    return {"prompt": prompt, "references": _safe_references(raw.get("references"), look, shot),
            "shot_prompts": _shot_prompts(prompt, state)}


def _shot_prompts(prompt: str, state: WeddingState) -> list[dict]:
    """每个镜头的最终提示词 = 共用提示词 + 这个镜头的景别、场景和动作。"""
    return [
        {"slot": item["slot"],
         "prompt": f"{prompt}本张镜头：{item['framing']}，场景{item['scene']}，{item['text']}。"}
        for item in state.get("shots") or []
    ]


def reveal(state: WeddingState) -> dict:
    if settings.fake_for("intake"):
        return {"message": "照片里你们笑得很自然，愿你们的婚礼也像这组照片一样，温柔又闪闪发光。"}
    brief = _brief(state)
    invitation = brief.invitation or {}
    fields = {
        "names": str(invitation.get("names") or "你们"),
        "date": str(invitation.get("date") or ""),
        "place": str(invitation.get("place") or ""),
        "materials": ", ".join(str(key) for key in (state.get("deliverables") or {})),
    }
    try:
        template = load_section(DIALOGUE, "reveal")
        result = _get_llm("cheap").with_structured_output(RevealResult).invoke(template.format_map(_SafeFormat(fields)))
        raw = result.model_dump() if hasattr(result, "model_dump") else result
        text = str(raw.get("message") or "").strip()
    except Exception as error:
        raise ModuleError("GENERATION_FAILED", "小囍暂时无法写揭幕寄语，请稍后再试") from error
    return {"message": (text or f"愿{fields['names']}的婚礼温柔圆满。")[:50]}


def _fake_intake(state: WeddingState) -> dict:
    answers, rounds = _answers(state), _rounds(state)
    update: dict[str, Any] = {
        "brief": _brief_from_answers(state, answers, force_defaults=rounds >= settings.max_question_rounds).model_dump()
    }
    consent = _consent(state, answers)
    if consent is None and rounds >= settings.max_question_rounds:
        consent = dict(DEFAULT_CONSENT)
    if consent is not None:
        update["consent"] = consent
    update["questions"] = _questions(state, answers) if rounds < settings.max_question_rounds else []
    replacement = _photo_replacements(state, answers, resolve_failures=False)
    if replacement:
        update.update(replacement)
    if update["questions"]:
        update["step_text"] = "我是小囍，你们这次拍摄的项目经理，先确认照片授权和婚礼基础信息。"
    return update


def _real_intake(state: WeddingState) -> dict:
    answers, rounds = _answers(state), _rounds(state)
    consent = _consent(state, answers)
    if consent is None and rounds < settings.max_question_rounds:
        update: dict[str, Any] = {
            "brief": _brief_from_llm(state, answers).model_dump(),
            "questions": _questions(state, answers),
            "step_text": "我是小囍。开始前先确认照片授权和婚礼基础信息。",
        }
        replacement = _photo_replacements(state, answers)
        if replacement:
            update.update(replacement)
        return update
    if consent is None:
        consent = dict(DEFAULT_CONSENT)
    replacement = _photo_replacements(state, answers)
    working = dict(state)
    working.update(replacement)
    _validate_photo_shape(working)
    failures = _photo_failures(working)
    if failures:
        if rounds >= settings.max_question_rounds:
            raise ModuleError("PHOTO_INVALID", _failure_message(failures))
        update = {
            "brief": _brief_from_answers(working, answers, force_defaults=False).model_dump(),
            "questions": _upload_questions(failures),
            "consent": consent,
            "step_text": "有几张照片还需要补传，我会只替换不合格的那几张。",
        }
        update.update(replacement)
        return update
    update = {
        "brief": _brief_from_llm(working, answers).model_dump(),
        "questions": _questions(working, answers),
        "consent": consent,
    }
    update.update(replacement)
    if update["questions"]:
        update["step_text"] = "我是小囍，你们这次拍摄的项目经理，再确认几项关键信息就可以交给妆造师了。"
    return update


def _rounds(state: WeddingState) -> int:
    return (state.get("question_rounds") or {}).get("intake", 0)


def _answers(state: WeddingState) -> dict[str, dict]:
    return {
        item["question_id"]: item
        for item in state.get("answers", [])
        if item.get("asker", "intake") == "intake" and item.get("question_id")
    }


def _questions(state: WeddingState, answers: dict[str, dict]) -> list[dict]:
    facts = _description_facts(str(state.get("description", "")))
    questions: list[dict] = []
    if _consent(state, answers) is None:
        questions.append({
            "question_id": "q_consent", "type": "single_choice", "title": "是否同意照片仅用于本次生成？",
            "options": [
                {"value": "standard", "label": "同意：仅用于本次生成，不用于训练，预览带水印，交付后删除原图", "image": None},
                {"value": "keep_photos", "label": "同意，但交付后保留原图", "image": None},
            ], "recommended": "standard", "allow_skip": False,
        })
    if "q_height" not in answers and not facts["heights"]:
        questions.append({
            "question_id": "q_height", "type": "text", "title": "两人身高大概多少？",
            "placeholder": "例如 175 / 162", "allow_skip": True,
        })
    if "q_materials" not in answers and not facts["materials"]:
        questions.append({
            "question_id": "q_materials", "type": "multi_choice", "title": "需要哪些婚礼物料？",
            "options": [{"value": value, "label": label, "image": None} for value, label in MATERIAL_OPTIONS],
            "recommended": list(DEFAULT_MATERIALS), "allow_skip": True,
        })
    if "q_invitation" not in answers and not facts["invitation"]:
        questions.append({
            "question_id": "q_invitation", "type": "text",
            "title": "请柬上写什么：新人名字、婚礼日期、地点？",
            "placeholder": "例如 张三 & 李四，2026-12-20，杭州", "allow_skip": True,
        })
    return questions[:4]


def _consent(state: WeddingState, answers: dict[str, dict]) -> dict | None:
    existing = state.get("consent")
    if isinstance(existing, dict) and existing.get("confirmed"):
        return _normalise_consent(existing)
    answer = answers.get("q_consent") or {}
    if answer.get("skipped"):
        return None
    value = answer.get("value")
    if value == "standard":
        return dict(DEFAULT_CONSENT)
    if value == "keep_photos":
        return dict(KEEP_PHOTOS_CONSENT)
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
    description = str(state.get("description", ""))
    facts = _description_facts(description)
    heights = _parse_heights((answers.get("q_height") or {}).get("value")) or facts["heights"]
    material_answer = answers.get("q_materials") or {}
    materials = _clean_materials(material_answer.get("value")) if not material_answer.get("skipped") else []
    materials = materials or facts["materials"] or list(DEFAULT_MATERIALS)
    invitation = _parse_invitation((answers.get("q_invitation") or {}).get("value")) or facts["invitation"] or {}
    missing = []
    if not heights:
        missing.append("heights_cm")
    if not invitation:
        missing.append("invitation")
    return Brief(heights_cm=heights, materials=materials, invitation=invitation, missing=missing)


def _brief_from_llm(state: WeddingState, answers: dict[str, dict]) -> Brief:
    fallback = _brief_from_answers(state, answers, force_defaults=False)
    try:
        template = load_section(DIALOGUE, "brief")
        result = _get_llm("agent").with_structured_output(Brief).invoke(template.format_map(_SafeFormat({
            "description": state.get("description", ""),
            "answers": json.dumps(list(answers.values()), ensure_ascii=False),
        })))
        raw = result.model_dump() if hasattr(result, "model_dump") else result
        values = Brief(**raw).model_dump()
    except Exception as error:
        raise ModuleError("GENERATION_FAILED", "小囍暂时无法整理需求，请稍后再试") from error
    values.update({
        "style": "undecided", "background": "undecided", "makeup": "undecided",
        "outfit_bride": "undecided", "outfit_groom": "undecided", "expression": "undecided", "pose": "undecided",
        "heights_cm": fallback.heights_cm, "materials": fallback.materials,
        "invitation": fallback.invitation, "missing": fallback.missing,
    })
    source = _brief_source_text(state, answers).lower()
    values["keep_features"] = [
        str(item).strip() for item in values.get("keep_features", [])
        if str(item).strip().lower() in source
    ]
    values["body_types"] = [
        str(item).strip() for item in values.get("body_types", [])
        if str(item).strip().lower() in source
    ]
    if values.get("beautify") not in {"none", "light"} or (
        values.get("beautify") == "light"
        and not any(token in source for token in ("轻度美化", "轻微美化", "light"))
    ):
        values["beautify"] = "none"
    return Brief(**values)


def _brief_source_text(state: WeddingState, answers: dict[str, dict]) -> str:
    return f"{state.get('description', '')}\n{json.dumps(list(answers.values()), ensure_ascii=False)}"


def _description_facts(description: str) -> dict[str, Any]:
    heights = _parse_heights(description)
    materials = [
        key for key, words in (
            ("invitation", ("请柬",)),
            ("welcome_poster", ("迎宾海报",)),
            ("led_screen", ("婚礼大屏", "大屏")),
        )
        if any(word in description for word in words)
    ]
    return {"heights": heights, "materials": materials, "invitation": _parse_invitation(description)}


def _parse_invitation(value: Any) -> dict:
    text = str(value or "").strip()
    if not text or not re.search(r"20\d{2}[-/.年]\s*\d{1,2}", text):
        return {}
    date_match = re.search(r"20\d{2}[-/.年]\s*\d{1,2}(?:[-/.月]\s*\d{1,2}日?)?", text)
    date = date_match.group(0).replace("年", "-").replace("月", "-").replace("日", "").strip(" -") if date_match else ""
    before = text[:date_match.start()].strip(" ，,：:;") if date_match else ""
    after = text[date_match.end():].strip(" ，,：:;") if date_match else ""
    names = before if before and not re.fullmatch(r".*(?:婚礼|日期|地点).*", before) else ""
    place = after.split("，")[0].split(",")[0].strip() if after else ""
    result = {}
    if names:
        result["names"] = names
    if date:
        result["date"] = date
    if place:
        result["place"] = place
    return result if len(result) >= 2 else {}


def _parse_heights(value: Any) -> list[int]:
    numbers = [int(number) for number in re.findall(r"(?<!\d)\d{3}(?!\d)", str(value or ""))]
    return numbers[:2] if len(numbers) >= 2 else []


def _clean_materials(value: Any) -> list[str]:
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, list):
        return []
    allowed = {item[0] for item in MATERIAL_OPTIONS}
    return [item for item in values if item in allowed]


def _validate_photo_shape(state: WeddingState) -> None:
    groom, bride = state.get("groom_photo_urls"), state.get("bride_photo_urls")
    if groom is not None or bride is not None:
        if not groom or not bride or not 1 <= len(groom) <= 10 or not 1 <= len(bride) <= 10:
            raise ModuleError("PHOTO_INVALID", "请分别上传新郎和新娘各 1～10 张正面生活照")
        photos = state.get("photo_urls")
        if photos is not None and list(photos) != list(groom) + list(bride):
            raise ModuleError("PHOTO_INVALID", "分组照片字段不一致，请重新上传")
    else:
        photos = state.get("photo_urls") or []
        if not 1 <= len(photos) <= 10:
            raise ModuleError("PHOTO_INVALID", "请上传 1～10 张合照")


def _photo_groups(state: WeddingState) -> list[tuple[str, str, list[str], int]]:
    groom, bride = state.get("groom_photo_urls"), state.get("bride_photo_urls")
    if groom is not None or bride is not None:
        return [
            ("新郎", "q_groom_photos", list(groom or []), 1),
            ("新娘", "q_bride_photos", list(bride or []), 1),
        ]
    return [("合照", "q_photos", list(state.get("photo_urls") or []), 2)]


@lru_cache(maxsize=128)
def _cached_photo_check(urls: tuple[str, ...], expected: int, label: str) -> tuple[dict, ...]:
    template = load_section(PHOTO_SORT, "check")
    content: list[dict[str, Any]] = [{"type": "text", "text": template.format(label=label, expected=expected)}]
    content.extend({"type": "image_url", "image_url": {"url": url}} for url in urls)
    try:
        result = _get_llm("vision").with_structured_output(PhotoCheck).invoke([{"role": "user", "content": content}])
    except Exception as error:
        return tuple({"index": i, "people_count": 0, "clear": False, "front_facing": False, "unobstructed": False, "reason": "照片检查暂时失败，请补传"} for i in range(1, len(urls) + 1))
    raw = result.model_dump() if hasattr(result, "model_dump") else result
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        items = raw.get("results") or raw.get("photos") or raw.get("items") or []
    else:
        items = []
    normalised = []
    for index, item in enumerate(items, 1):
        value = item.model_dump() if hasattr(item, "model_dump") else dict(item)
        normalised.append({
            "index": int(value.get("index", index)),
            "people_count": int(value.get("people_count", 0)),
            "clear": bool(value.get("clear")),
            "front_facing": bool(value.get("front_facing")),
            "unobstructed": bool(value.get("unobstructed")),
            "reason": str(value.get("reason", "")),
        })
    while len(normalised) < len(urls):
        normalised.append({
            "index": len(normalised) + 1, "people_count": 0, "clear": False,
            "front_facing": False, "unobstructed": False, "reason": "未返回这张照片的检查结果",
        })
    return tuple(normalised[:len(urls)])


def _photo_failures(state: WeddingState) -> list[dict]:
    failures = []
    for label, question_id, urls, expected in _photo_groups(state):
        for result in _cached_photo_check(tuple(urls), expected, label):
            if result["people_count"] != expected or not result["clear"] or not result["front_facing"] or not result["unobstructed"]:
                failures.append({
                    "label": label, "question_id": question_id, "index": result["index"],
                    "reason": result["reason"] or "人数、清晰度、正脸或遮挡不符合要求",
                })
    return failures


def _photo_replacements(state: WeddingState, answers: dict[str, dict], *, resolve_failures: bool = True) -> dict:
    update: dict[str, Any] = {}
    for _label, question_id, current, _expected in _photo_groups(state):
        answer = answers.get(question_id) or {}
        urls = answer.get("urls")
        if answer.get("skipped") or not isinstance(urls, list) or not urls:
            continue
        if len(urls) == len(current):
            new_urls = list(urls)
        else:
            failures = [item["index"] for item in _photo_failures(state) if item["question_id"] == question_id] if resolve_failures else list(range(1, len(urls) + 1))
            new_urls = list(current)
            for index, url in zip(failures, urls):
                if 1 <= index <= len(new_urls):
                    new_urls[index - 1] = url
        if question_id == "q_photos":
            update["photo_urls"] = new_urls
        elif question_id == "q_groom_photos":
            update["groom_photo_urls"] = new_urls
        else:
            update["bride_photo_urls"] = new_urls
    if "groom_photo_urls" in update or "bride_photo_urls" in update:
        groom = update.get("groom_photo_urls", state.get("groom_photo_urls") or [])
        bride = update.get("bride_photo_urls", state.get("bride_photo_urls") or [])
        update["photo_urls"] = list(groom) + list(bride)
    return update


def _upload_questions(failures: list[dict]) -> list[dict]:
    by_group: dict[str, list[dict]] = {}
    for item in failures:
        by_group.setdefault(item["question_id"], []).append(item)
    questions = []
    for question_id, items in by_group.items():
        detail = "、".join(f"第{item['index']}张：{item['reason']}" for item in items)
        label = items[0]["label"]
        questions.append({
            "question_id": question_id, "type": "upload",
            "title": f"{label}{detail}，请补传清晰的正面照",
            "options": [], "recommended": None, "allow_skip": False,
        })
    return questions


def _failure_message(failures: list[dict]) -> str:
    return "；".join(f"{item['label']}第{item['index']}张：{item['reason']}" for item in failures)


def _brief(state: WeddingState) -> Brief:
    try:
        return Brief(**state.get("brief", {}))
    except Exception as error:
        raise ModuleError("GENERATION_FAILED", "需求单格式不完整，无法继续") from error


def _look_shot_refs(look: dict, shot: dict) -> list[dict]:
    refs = [
        item for source in (shot, look)
        for item in (source.get("references") or [])
        if isinstance(item, dict) and item.get("url")
    ]
    unique = []
    for item in refs:
        value = {"url": item["url"], "role": item["role"]}
        if value not in unique:
            unique.append(value)
    return sorted(unique, key=lambda item: item["role"] != "pose")[: settings.max_reference_images]


def _safe_references(raw: Any, look: dict, shot: dict) -> list[dict]:
    allowed = {
        item.get("url") for source in (look, shot)
        for item in (source.get("references") or []) if isinstance(item, dict)
    }
    refs = []
    for item in raw or []:
        value = item.model_dump() if hasattr(item, "model_dump") else item
        if isinstance(value, dict) and value.get("url") in allowed and value.get("role") in {"style", "outfit", "makeup", "pose", "background"}:
            ref = {"url": value["url"], "role": value["role"]}
            if ref not in refs:
                refs.append(ref)
    for ref in _look_shot_refs(look, shot):
        if ref not in refs:
            refs.append(ref)
    return sorted(refs, key=lambda item: item["role"] != "pose")[: settings.max_reference_images]


class _SafeFormat(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _get_llm(kind: str):
    from app.common.llm import get_llm
    return get_llm(kind)
