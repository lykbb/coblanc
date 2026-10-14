"""摄影师（agent）：负责背景、构图、景别、光线、姿势，写出镜头描述 shot。

在妆造师之后上场，可以参考妆造师的 look：以摄影师身份用 questions 和用户确认两人关系、互动方式、场景、季节和灯光，
确认后写 shot。姿势骨架图、背景参考图用资产库的 search_assets 去找。默认沿用原图姿势；
换姿势时只能用资产库里的姿势，按身高差分 3 档：close（5cm 以内）、medium（5–15cm）、large（15cm 以上）。
每次调用都要返回一版 shot（还在问问题时给的是按推荐选项写的草稿）。
fake 模式用下面的规则版；真实实现是一个 agent，按 TODO 补。
"""

import copy
import json
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from app.common.config import settings
from app.common.errors import ModuleError
from app.common.llm import get_llm
from app.modules.assets import search_assets
from app.state import Brief, WeddingState

from .pi_bridge import run_pi
from .schemas import Decision

PROMPTS = Path(__file__).parent / "prompts"
KEEP_ORIGINAL = "keep_original"
BACKGROUNDS = {
    "keep_original": "保持原图的地点、构图和光线",
    "studio": "简洁的室内影棚，半身到全身构图",
}
QUESTIONS = [
    {
        "question_id": "q_interaction",
        "type": "single_choice",
        "title": "你们平时相处更像哪种状态？",
        "options": [
            {"value": "gaze", "label": "牵手对视", "image": None},
            {"value": "hug", "label": "相拥微笑", "image": None},
            {"value": "side", "label": "并肩看镜头", "image": None},
        ],
        "recommended": "gaze",
        "allow_skip": True,
    },
    {
        "question_id": "q_light",
        "type": "single_choice",
        "title": "喜欢什么样的光线？",
        "options": [
            {"value": "soft", "label": "柔和自然光", "image": None},
            {"value": "warm", "label": "温暖的室内灯光", "image": None},
            {"value": "backlight", "label": "傍晚逆光", "image": None},
        ],
        "recommended": "soft",
        "allow_skip": True,
    },
]


def height_band(heights_cm: list[int]) -> str | None:
    if len(heights_cm) != 2:
        return None
    diff = abs(heights_cm[0] - heights_cm[1])
    if diff <= 5:
        return "close"
    if diff <= 15:
        return "medium"
    return "large"


def frame(state: WeddingState) -> dict:
    if settings.fake_for("framing"):
        return _rule_shot(state)
    try:
        brief = Brief(**state.get("brief", {}))
        answers = [copy.deepcopy(item) for item in state.get("answers", [])
                   if item.get("asker") == "framing"]
        plan = state.get("retouch_plan") or {}
        retouching = plan.get("target") == "shot"
        expected_pose = KEEP_ORIGINAL if retouching else brief.pose
        band = height_band(brief.heights_cm)
        system = (PROMPTS / "agent.md").read_text(encoding="utf-8")
        context = {
            "brief": brief.model_dump(), "look": copy.deepcopy(state.get("look") or {}),
            "answers": answers, "height_band": band, "expected_pose": expected_pose,
            "retouch_plan": copy.deepcopy(plan) if retouching else None,
        }
        assets: dict[str, dict] = {}
        llm = get_llm("agent").with_structured_output(Decision, method="function_calling")

        def decide(message: dict) -> dict:
            value = llm.invoke([SystemMessage(content=system), HumanMessage(content=json.dumps(
                {"input": context, "history": message["history"],
                 "remaining_steps": message["remaining_steps"]}, ensure_ascii=False,
            ))])
            return Decision.model_validate(value).model_dump(mode="json")

        def find(name: str, arguments: dict) -> list[dict]:
            if name != "search_assets" or arguments.get("kind") not in {"pose", "background"}:
                raise ValueError("不允许的工具")
            found = search_assets(arguments["kind"], arguments.get("tags") or None)
            if arguments["kind"] == "pose":
                found = [item for item in found
                         if band and item["asset_id"].startswith(f"pose_{band}_")]
            found = found[:20]
            assets.update({item["url"]: item for item in found})
            return found

        result = Decision.model_validate(run_pi(
            {"model": settings.llm_model_agent, "system": system, "input": context,
             "max_steps": settings.max_agent_steps}, decide, find,
            timeout=settings.llm_timeout_seconds * (settings.max_agent_steps + 1),
        ))
        if result.action != "final" or result.shot is None:
            raise ValueError("摄影師未输出镜头描述")
        shot = result.shot.model_dump()
        if expected_pose == KEEP_ORIGINAL:
            shot["pose"] = KEEP_ORIGINAL
            shot["references"] = [ref for ref in shot["references"] if ref["role"] != "pose"]
        elif not band or not shot["pose"].startswith(f"{band}_"):
            shot["pose"], shot["references"] = KEEP_ORIGINAL, []
        for reference in shot["references"]:
            asset = assets.get(reference["url"])
            if not asset or reference["role"] != asset["kind"]:
                raise ValueError("摄影师使用了资产库之外的参考图")
        if shot["pose"] != KEEP_ORIGINAL and not any(
            assets.get(ref["url"], {}).get("asset_id") == f"pose_{shot['pose']}"
            for ref in shot["references"] if ref["role"] == "pose"
        ):
            shot["pose"] = KEEP_ORIGINAL
            shot["references"] = [ref for ref in shot["references"] if ref["role"] != "pose"]
        shot["references"] = sorted(shot["references"], key=lambda ref: ref["role"] != "pose")
        shot["references"] = shot["references"][:settings.max_reference_images]
        if shot["pose"] != KEEP_ORIGINAL and not any(
            ref["role"] == "pose" for ref in shot["references"]
        ):
            shot["pose"] = KEEP_ORIGINAL
        shot["text"] = _height_text(brief) + "；" + shot["text"]
        if retouching and plan.get("patch"):
            shot["text"] += f"调整：{plan['patch']}。"
        if expected_pose == KEEP_ORIGINAL:
            shot["text"] += "沿用原图姿势，不因互动偏好改变肢体位置。"
        if brief.keep_features:
            shot["text"] += f"保留：{'、'.join(brief.keep_features)}。"
        if context["look"].get("text"):
            shot["text"] += f"构图与既定造型协调：{context['look']['text']}。"
        update = {"shot": shot}
        questions = _pending_questions(state, answers)
        if questions:
            update.update(questions=questions, step_text="我是摄影师，想确认你们的互动和光线偏好。")
        return update
    except ModuleError:
        raise
    except Exception:
        raise ModuleError("GENERATION_FAILED", "摄影师暂时无法完成拍摄方案，请稍后重试") from None


def _height_text(brief: Brief) -> str:
    if len(brief.heights_cm) == 2:
        return f"两人身高 {brief.heights_cm[0]}cm 和 {brief.heights_cm[1]}cm，保持这个身高差和体型"
    return "保持原图里两人的身高差和体型"


def _pending_questions(state: WeddingState, answers: list[dict]) -> list[dict]:
    if state.get("candidates") or (state.get("retouch_plan") or {}).get("target") == "shot":
        return []
    rounds = (state.get("question_rounds") or {}).get("framing", 0)
    if rounds >= settings.max_question_rounds:
        return []
    answered_ids = {item["question_id"] for item in answers}
    questions = [copy.deepcopy(q) for q in QUESTIONS if q["question_id"] not in answered_ids]
    if questions:
        return questions[:3]
    if rounds == 1 and settings.max_question_rounds > 1:
        extra = [
            {"question_id": "q_background", "type": "text", "title": "希望在什么场景拍摄？",
             "recommended": "按已经确认的场景拍摄", "allow_skip": True},
            {"question_id": "q_season", "type": "text", "title": "希望照片呈现哪个季节？",
             "recommended": "沿用原图季节", "allow_skip": True},
            {"question_id": "q_relationship", "type": "text", "title": "想在照片里呈现怎样的两人关系？",
             "recommended": "自然亲密", "allow_skip": True},
        ]
        return [q for q in extra if q["question_id"] not in answered_ids]
    return []


def _choose(question: dict, answer: dict | None) -> dict:
    if answer and not answer.get("skipped"):
        for option in question["options"]:
            if option["value"] == answer.get("value"):
                return option
    return next(option for option in question["options"] if option["value"] == question["recommended"])


def _rule_shot(state: WeddingState) -> dict:
    brief = Brief(**state.get("brief", {}))
    plan = state.get("retouch_plan") or {}
    answers = {item["question_id"]: item for item in state.get("answers", []) if item.get("asker") == "framing"}
    interaction, light = (_choose(question, answers.get(question["question_id"])) for question in QUESTIONS)

    pose = brief.pose
    if plan.get("target") == "shot":  # 修图方案指向镜头（比如身材比例不对）：先改回原图姿势
        pose = KEEP_ORIGINAL
    references = []
    if pose != KEEP_ORIGINAL:
        band = height_band(brief.heights_cm)
        matches = [item for item in search_assets("pose") if band
                   and pose.startswith(f"{band}_") and item["asset_id"] == f"pose_{pose}"]
        if matches:
            references.append({"url": matches[0]["url"], "role": "pose"})
        else:  # 资产库里还没有这个姿势：退回原图姿势
            pose = KEEP_ORIGINAL

    if len(brief.heights_cm) == 2:
        height = f"两人身高 {brief.heights_cm[0]}cm 和 {brief.heights_cm[1]}cm，保持这个身高差"
    else:
        height = "保持原图里两人的身高差和体型"
    pose_text = "沿用原图的姿势" if pose == KEEP_ORIGINAL else "按参考图的姿势站立"

    template = (PROMPTS / "shot.md").read_text(encoding="utf-8").strip()
    text = template.format(
        background=BACKGROUNDS.get(brief.background, BACKGROUNDS["keep_original"]),
        height=height,
        pose=pose_text,
        interaction=interaction["label"],
        light=light["label"],
    )
    if pose == KEEP_ORIGINAL:
        text += "互动仅作为氛围参考，沿用原图肢体位置。"
    if plan.get("target") == "shot" and plan.get("patch"):
        text += f"调整：{plan['patch']}。"

    shot = {"text": text, "pose": pose, "references": references}
    if (answers or state.get("candidates") or plan.get("target") == "shot"
            or (state.get("question_rounds") or {}).get("framing", 0) >= settings.max_question_rounds):
        return {"shot": shot}
    return {"shot": shot, "questions": copy.deepcopy(QUESTIONS), "step_text": "我是摄影师，想再了解一下你们平时怎么相处，喜欢什么样的光线。"}

