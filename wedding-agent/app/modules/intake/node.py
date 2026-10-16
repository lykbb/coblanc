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

from . import photo_rules
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
    # groom/bride=单人；couple=两人合照；unknown=分不清（混合上传时用来建身份照）
    tag: str = "unknown"
    # 画面里有没有宠物（狗/猫/兔等），以及是哪种
    has_pet: bool = False
    # 动物是不是画面主体（背景里的、很小的、拿不准的都是 false）；只有主体宠物才需要用户同意
    pet_prominent: bool = False
    pet_kind: str = ""
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
    identity = _identity(state)
    if settings.fake_for("intake"):
        references = _fit_references(_look_shot_refs(look, shot), identity)
        opening = _opening(identity, references)
        parts = [opening, str(look.get("text", "")), str(shot.get("text", ""))]
        if plan.get("target") == "prompt" and plan.get("patch"):
            parts.append(str(plan["patch"]))
        prompt = "".join(part for part in parts if part)
        return {"prompt": prompt, "references": references, "identity": identity,
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
    references = _fit_references(_safe_references(raw.get("references"), look, shot), identity)
    opening = _opening(identity, references)
    for fixed in (opening, load_section(IMAGE_PROMPT, "identity")):
        if body.startswith(fixed):
            body = body[len(fixed):].lstrip()
    prompt = opening + body
    return {"prompt": prompt, "references": references, "identity": identity,
            "shot_prompts": _shot_prompts(prompt, state)}


MAX_SEND_IMAGES = 10


def _identity(state: WeddingState) -> list[dict]:
    """身份照清单（发图顺序）。优先用 intake 写入的 identity；
    否则分组上传：新郎前 2 张、新娘前 2 张；再否则单入口回退为全部标成合照（兼容旧任务）。"""
    saved = [dict(item) for item in state.get("identity") or [] if isinstance(item, dict) and item.get("url")]
    if saved:
        return saved[:MAX_SEND_IMAGES]
    groom, bride = state.get("groom_photo_urls"), state.get("bride_photo_urls")
    if groom is not None or bride is not None:
        items = [{"url": u, "role": "groom"} for u in list(groom or [])[:2]]
        items += [{"url": u, "role": "bride"} for u in list(bride or [])[:2]]
        return items
    return [{"url": u, "role": "couple"} for u in list(state.get("photo_urls") or [])[:MAX_SEND_IMAGES]]


def _fit_references(references: list[dict], identity: list[dict]) -> list[dict]:
    """身份照优先；参考图只能用剩下的位置，放不下的从后往前丢。"""
    return references[: max(0, MAX_SEND_IMAGES - len(identity))]


def _binding_templates() -> dict[str, str]:
    lines: dict[str, str] = {}
    for line in load_section(IMAGE_PROMPT, "binding").splitlines():
        key, sep, value = line.partition("：")
        if sep:
            lines[key.strip()] = value.strip()
    return lines


def binding_sentence(identity: list[dict], references: list[dict]) -> str:
    """按发图顺序写"图几是谁"，同一类连续的编号合并（图1、图2是新郎本人）。"""
    templates = _binding_templates()
    entries: list[tuple[str, str]] = []  # (分组键, 模板)
    for item in identity:
        role = item.get("role")
        key, template = role, templates[role]
        entries.append((key, template))
    entries += [(ref["role"], templates[ref["role"]]) for ref in references if ref.get("role") in templates]
    parts, n = [], 1
    i = 0
    while i < len(entries):
        j = i
        while j + 1 < len(entries) and entries[j + 1][0] == entries[i][0]:
            j += 1
        numbers = "、".join(f"图{k}" for k in range(n + i, n + j + 1))
        parts.append(entries[i][1].replace("图{n}", numbers))
        i = j + 1
    if not parts:
        return ""
    sentence = "；".join(parts) + "。"
    if references:
        sentence += templates["有参考图时句末"]
    return sentence


def _opening(identity: list[dict], references: list[dict]) -> str:
    return binding_sentence(identity, references) + load_section(IMAGE_PROMPT, "identity")


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
    failures = _count_failures(working) or _photo_failures(working)
    if failures:
        # 照片问题永远不终止任务：暂停等用户补传/说明，补完从 intake 继续
        update = {
            "brief": _brief_from_answers(working, answers, force_defaults=False).model_dump(),
            "questions": _upload_questions(failures),
            "consent": consent,
            "step_text": _photo_step_text(failures, _photo_ask_count(working)),
        }
        update.update(replacement)
        return update
    update = {
        "brief": _brief_from_llm(working, answers).model_dump(),
        "questions": _questions(working, answers),
        "consent": consent,
    }
    update.update(replacement)
    merged = {**working, **replacement}
    if _compose_from_solo(merged):
        update["brief"]["compose_from_solo"] = True
        note = "没有合照：用新郎、新娘的单人照合成双人画面，保持两人真实身高比例、光线方向和色调一致"
        if note not in update["brief"]["keep_features"]:
            update["brief"]["keep_features"].append(note)
    pet_note = _pet_keep_feature(merged)
    if pet_note and pet_note not in update["brief"]["keep_features"]:
        update["brief"]["keep_features"].append(pet_note)
    verdict = _mixed_verdict(merged)
    if verdict and verdict.identity:
        update["identity"] = verdict.identity
    if update["questions"]:
        update["step_text"] = "我是小囍，你们这次拍摄的项目经理，再确认几项关键信息就可以交给妆造师了。"
    return update


def _compose_from_solo(state: WeddingState) -> bool:
    verdict = _mixed_verdict(state)
    return bool(verdict and verdict.ok and verdict.compose_from_solo)


def _pet_keep_feature(state: WeddingState) -> str:
    """用户同意且照片里确实有主体宠物：写进需求单，生图时一起入镜。"""
    verdict = _mixed_verdict(state)
    pets = verdict.pets if verdict else []
    return f"宠物{pets[0]}作为纪念一起入镜，保持它的外貌特征" if pets else ""


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
        "heights_cm": fallback.heights_cm, "materials": fallback.materials, "compose_from_solo": False,
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
        problem = photo_rules.count_problem(len(photo_rules.dedupe(state.get("photo_urls"))))
        if problem:
            raise ModuleError("PHOTO_INVALID", problem)


def _photo_groups(state: WeddingState) -> list[tuple[str, str, list[str], int]]:
    """返回 (显示名, question_id, urls, expected_people)。
    expected_people=0 表示单入口混合上传：每张可以是单人照(1)或两人合照(2)。
    """
    groom, bride = state.get("groom_photo_urls"), state.get("bride_photo_urls")
    if groom is not None or bride is not None:
        return [
            ("新郎", "q_groom_photos", list(groom or []), 1),
            ("新娘", "q_bride_photos", list(bride or []), 1),
        ]
    # 单入口：不要把每张都当成合照（强制 2 人），否则男女各一张单人照会被误判要补传
    return [("照片", "q_photos", list(state.get("photo_urls") or []), 0)]


@lru_cache(maxsize=128)
def _cached_photo_check(urls: tuple[str, ...], expected: int, label: str) -> tuple[dict, ...]:
    template = load_section(PHOTO_SORT, "check")
    expected_text = "1 或 2" if expected == 0 else str(expected)
    content: list[dict[str, Any]] = [{"type": "text", "text": template.format(label=label, expected=expected_text)}]
    try:
        content.extend({"type": "image_url", "image_url": {"url": _data_url(url)}} for url in urls)
        result = _get_llm("vision").with_structured_output(PhotoCheck).invoke([{"role": "user", "content": content}])
    except Exception as error:
        # 模型/网络异常是系统问题，不能伪装成「照片没人脸」让用户补传
        raise ModuleError("GENERATION_FAILED", "小囍看照片时模型暂时没响应") from error
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
        people_count = int(value.get("people_count", 0))
        tag = str(value.get("tag") or "unknown").strip().lower()
        if tag not in {"groom", "bride", "couple", "pet", "unknown"}:
            tag = "unknown"
        if people_count >= 2 and tag == "unknown":
            tag = "couple"
        normalised.append({
            "index": int(value.get("index", index)),
            "people_count": people_count,
            "clear": bool(value.get("clear")),
            "front_facing": bool(value.get("front_facing")),
            "unobstructed": bool(value.get("unobstructed")),
            "tag": tag,
            "has_pet": bool(value.get("has_pet")) or tag == "pet",
            "pet_prominent": bool(value.get("pet_prominent")) or (tag == "pet" and people_count == 0),
            "pet_kind": str(value.get("pet_kind") or "").strip(),
            "reason": str(value.get("reason", "")),
        })
    while len(normalised) < len(urls):
        normalised.append({
            "index": len(normalised) + 1, "people_count": 0, "clear": False,
            "front_facing": False, "unobstructed": False, "tag": "unknown", "has_pet": False, "pet_prominent": False,
            "pet_kind": "", "reason": "未返回这张照片的检查结果",
        })
    return tuple(normalised[:len(urls)])


def _count_ok(people_count: int, expected: int) -> bool:
    """expected=0：混合上传，单人(1)或两人合照(2)都合格；否则必须人数正好等于 expected。"""
    if expected == 0:
        return people_count in (1, 2)
    return people_count == expected




def _pet_consent(state: WeddingState) -> bool:
    return photo_rules.pet_consent(_brief_source_text(state, _answers(state)))


def _photo_ask_count(state: WeddingState) -> int:
    """已经问过几轮补传照片（用来换说法，避免重复同一句）。"""
    return sum(1 for item in state.get("answers", []) if item.get("question_id") == "q_photos")


def _photo_failures(state: WeddingState) -> list[dict]:
    verdict = _mixed_verdict(state)
    if verdict is not None:
        return [{"label": "照片", "question_id": "q_photos", **item} for item in verdict.failures]
    # 分组上传（旧接口）：每组每张都要清晰、正面、无遮挡且人数正确
    failures = []
    for label, question_id, urls, expected in _photo_groups(state):
        for result in _cached_photo_check(tuple(urls), expected, label):
            if _count_ok(result["people_count"], expected) and result["clear"] and result["front_facing"] and result["unobstructed"]:
                continue
            reason = (result.get("reason") or "").strip() or (
                f"人数应为{expected}人" if not _count_ok(result["people_count"], expected) else "请换成更清晰、正脸、无遮挡的照片")
            failures.append({"label": label, "question_id": question_id, "index": result["index"], "reason": reason})
    return failures


def _mixed_verdict(state: WeddingState) -> photo_rules.Verdict | None:
    """单入口混合上传按 photo_rules 判断；分组上传（旧接口）返回 None。"""
    if state.get("groom_photo_urls") is not None or state.get("bride_photo_urls") is not None:
        return None
    urls = photo_rules.dedupe(state.get("photo_urls"))
    if not urls:
        return None
    results = list(_cached_photo_check(tuple(urls), 0, "照片"))
    return photo_rules.evaluate(urls, results, _pet_consent(state))


def _photo_replacements(state: WeddingState, answers: dict[str, dict], *, resolve_failures: bool = True) -> dict:
    update: dict[str, Any] = {}
    current_round = _rounds(state)
    for _label, question_id, current, _expected in _photo_groups(state):
        answer = answers.get(question_id) or {}
        urls = answer.get("urls")
        # 只用最近一轮的补传，避免旧回答被重复套用
        if answer.get("round") not in (None, current_round):
            continue
        if answer.get("skipped") or not isinstance(urls, list) or not urls:
            continue
        if question_id == "q_photos" and resolve_failures:
            # 混合上传：去掉被点名的照片，新照片追加在后面，总数不超过 10（新照片优先保留）
            flagged = {item["index"] for item in _photo_failures(state) if item.get("index")}
            kept = [url for i, url in enumerate(current, 1) if i not in flagged]
            new_urls = (kept + list(urls))[-10:] if len(kept) + len(urls) > 10 else kept + list(urls)
        elif len(urls) == len(current):
            new_urls = list(urls)
        else:
            failures = [item["index"] for item in _photo_failures(state) if item["question_id"] == question_id and item.get("index")] if resolve_failures else list(range(1, len(urls) + 1))
            new_urls = list(current)
            for index, url in zip(failures, urls):
                if 1 <= index <= len(new_urls):
                    new_urls[index - 1] = url
        if question_id == "q_photos":
            update["photo_urls"] = photo_rules.dedupe(new_urls)
        elif question_id == "q_groom_photos":
            update["groom_photo_urls"] = new_urls
        else:
            update["bride_photo_urls"] = new_urls
    if "groom_photo_urls" in update or "bride_photo_urls" in update:
        groom = update.get("groom_photo_urls", state.get("groom_photo_urls") or [])
        bride = update.get("bride_photo_urls", state.get("bride_photo_urls") or [])
        update["photo_urls"] = list(groom) + list(bride)
    return update


def _count_failures(state: WeddingState) -> list[dict]:
    """数量不对也当成照片问题，让用户补传，不终止任务。"""
    try:
        _validate_photo_shape(state)
    except ModuleError as error:
        groom, bride = state.get("groom_photo_urls"), state.get("bride_photo_urls")
        question_id = "q_photos" if groom is None and bride is None else ("q_groom_photos" if not groom else "q_bride_photos")
        return [{"label": "照片", "question_id": question_id, "index": None, "reason": error.message}]
    return []


def _describe_failures(items: list[dict]) -> str:
    return photo_rules.describe(items)


def _photo_step_text(failures: list[dict], asked: int = 0) -> str:
    detail = _describe_failures(failures)
    if asked == 0:
        return f"照片还差一点：{detail}。直接在下方对话框补传照片或告诉我就行。"
    if asked == 1:
        return f"我再说清楚一点：{detail}。{photo_rules.UPLOAD_HINT}，每人有一张能看清脸的就够了。"
    return f"还是卡在这里：{detail}。可以点左下角回形针补传照片，或者在对话框里告诉我情况，我会按你的意思继续。"


def _upload_questions(failures: list[dict]) -> list[dict]:
    by_group: dict[str, list[dict]] = {}
    for item in failures:
        by_group.setdefault(item["question_id"], []).append(item)
    return [{
        "question_id": question_id, "type": "upload",
        "title": f"照片还差一点：{_describe_failures(items)}",
        "options": [], "recommended": None, "allow_skip": False,
    } for question_id, items in by_group.items()]


def _failure_message(failures: list[dict]) -> str:
    return "上传的照片不符合要求：" + _describe_failures(failures)


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


def _data_url(url: str) -> str:
    """本机地址外部模型下载不到，统一转成 base64 内嵌发送。
    先按 EXIF 摆正、转 RGB、长边缩到 1536、存 JPEG：手机原图和 2048 透明 PNG 动辄 5MB，
    多张一起发会超出视觉模型的请求上限。"""
    if url.startswith("data:"):
        return url
    import base64
    import io
    from app.modules.assets import load_image
    try:
        data = load_image(url)
    except Exception:
        return url  # 读不到本地文件（例如公网地址）就原样发
    try:
        from PIL import Image, ImageOps
        image = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
        if image.mode != "RGB":
            background = Image.new("RGB", image.size, "white")
            rgba = image.convert("RGBA")
            background.paste(rgba, mask=rgba.split()[-1])
            image = background
        image.thumbnail((1536, 1536))
        buffer = io.BytesIO()
        image.save(buffer, "JPEG", quality=88)
        return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
    except Exception:
        mime = "image/png" if data.startswith(b"\x89PNG") else "image/jpeg"
        return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")


def _get_llm(kind: str):
    from app.common.llm import get_llm
    return get_llm(kind)
