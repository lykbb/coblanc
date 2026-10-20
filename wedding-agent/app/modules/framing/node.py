"""摄影师（agent）：负责背景、构图、景别、光线、姿势，写出镜头描述 shot。

在妆造师之后上场，可以参考妆造师的 look：只问用户一个问题——场景（按风格给 3 个 + 保留原图场景），
灯光、季节、互动由风格和场景自动带出（scenes.py），确认后写 shot。姿势骨架图、背景参考图用资产库的 search_assets 去找。默认沿用原图姿势；
换姿势时只能用资产库里的姿势，按身高差分 3 档：close（5cm 以内）、medium（5–15cm）、large（15cm 以上）。
每次调用都要返回一版 shot（还在问问题时给的是按推荐选项写的草稿）。
fake 模式用下面的规则版；真实实现是一个 agent，按 TODO 补。
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from app.common.config import settings
from app.common.errors import ModuleError
from app.common.llm import get_llm, model_name
from app.modules.assets import search_assets
from app.modules.framing.style_lookup import style_references
from app.state import Brief, WeddingState

from .pi_bridge import run_pi
from .scenes import scene_choice, scene_question
from .schemas import Decision

PROMPTS = Path(__file__).parent / "prompts"
KEEP_ORIGINAL = "keep_original"
BACKGROUNDS = {
    "keep_original": "保持原图的人物构图",
    "studio": "半身到全身构图",
}


# 分镜表模板：9 个镜头的景别和动作各不相同，避免套图 9 张一个样。slot 0 同时用于样片。
SHOT_PLANS = [
    ("全身", "牵手并肩走向镜头"),
    ("半身", "相拥对视微笑"),
    ("特写", "额头相抵，闭眼微笑"),
    ("全身", "新郎单膝跪地牵起新娘的手"),
    ("半身", "新娘挽着新郎手臂，一起看镜头"),
    ("远景", "两人背影，并肩望向远方"),
    ("半身", "新郎从身后环抱新娘"),
    ("特写", "两人十指相扣的手和戒指"),
    ("全身", "新郎抱起新娘转圈，裙摆飞扬"),
]


def plan_shots(shot: dict, scene: str) -> list[dict]:
    """按 shot 的整体方案拆出 settings.set_candidates 个不同镜头。"""
    count = max(settings.set_candidates, 1)
    shots = []
    for slot in range(count):
        framing, action = SHOT_PLANS[slot % len(SHOT_PLANS)]
        shots.append({
            "slot": slot, "pose": shot["pose"],
            "framing": framing, "scene": scene,
            "text": f"{framing}构图，{action}",
        })
    return shots


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
        style_cases, style_text = style_references((state.get("look") or {}).get("style"))
        scene = _scene(state)
        context = {
            "brief": brief.model_dump(), "look": copy.deepcopy(state.get("look") or {}),
            "answers": answers,
            "scene": {key: scene[key] for key in ("label", "description", "light", "season", "interaction")},
            "height_band": band, "expected_pose": expected_pose,
            "retouch_plan": copy.deepcopy(plan) if retouching else None,
            # 资产库里每类有几张可用图；为 0 的类别搜不到东西，模型不要反复搜索、直接给出方案
            "asset_library": {kind: len(search_assets(kind)) for kind in ("pose", "background")},
            "style_cases": style_text,
            "asset_note": "asset_library 里数量为 0 的类别不要调用 search_assets；同一类最多搜索 2 次，搜不到就直接 final，references 留空。",
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
            {"model": model_name("agent"), "system": system, "input": context,
             "max_steps": settings.max_agent_steps}, decide, find,
            timeout=settings.llm_timeout_seconds * (settings.max_agent_steps + 1),
        ))
        if result.action != "final" or result.shot is None:
            raise ValueError("摄影師未输出镜头描述")
        shot = result.shot.model_dump()
        shot["style_cases"] = style_cases
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
        if scene["label"] not in shot["text"]:
            shot["text"] = f"场景：{scene['label']}（{scene['description']}），{scene['light']}，{scene['season']}；" + shot["text"]
        shot["text"] = _height_text(brief) + "；" + shot["text"]
        if retouching and plan.get("patch"):
            shot["text"] += f"调整：{plan['patch']}。"
        if expected_pose == KEEP_ORIGINAL:
            shot["text"] += "沿用原图姿势，不因互动偏好改变肢体位置。"
        if brief.keep_features:
            shot["text"] += f"保留：{'、'.join(brief.keep_features)}。"
        if context["look"].get("text"):
            shot["text"] += f"构图与既定造型协调：{context['look']['text']}。"
        return _with_questions(state, {"shot": shot, "shots": plan_shots(shot, scene["label"])})
    except ModuleError:
        raise
    except Exception:
        raise ModuleError("GENERATION_FAILED", "摄影师暂时无法完成拍摄方案，请稍后重试")


def _height_text(brief: Brief) -> str:
    if len(brief.heights_cm) == 2:
        return f"两人身高 {brief.heights_cm[0]}cm 和 {brief.heights_cm[1]}cm，保持这个身高差和体型"
    return "保持原图里两人的身高差和体型"


def _scene(state: WeddingState) -> dict:
    answers = {item["question_id"]: item for item in state.get("answers", [])
               if item.get("asker") == "framing" and item.get("question_id")}
    return scene_choice((state.get("look") or {}).get("style"), answers)


def _pending_questions(state: WeddingState) -> list[dict]:
    """规则版和真实 agent 共用：只问一次场景；修图、已有候选图、回答过或轮次用完都不再问。"""

    if state.get("candidates") or (state.get("retouch_plan") or {}).get("target") == "shot":
        return []
    if (state.get("question_rounds") or {}).get("framing", 0) >= settings.max_question_rounds:
        return []
    if any(item.get("asker") == "framing" for item in state.get("answers", [])):
        return []
    return [scene_question((state.get("look") or {}).get("style"))]


def _with_questions(state: WeddingState, update: dict) -> dict:
    questions = _pending_questions(state)
    if questions:
        update.update(questions=questions, step_text="我是摄影师，按你们的风格挑了几个场景，选一个吧。")
    return update


def _rule_shot(state: WeddingState) -> dict:
    brief = Brief(**state.get("brief", {}))
    plan = state.get("retouch_plan") or {}
    scene = _scene(state)

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
        interaction=scene["interaction"],
        scene=f"{scene['label']}（{scene['description']}）",
        season=scene["season"],
        light=scene["light"],
    )
    if pose == KEEP_ORIGINAL:
        text += "互动仅作为氛围参考，沿用原图肢体位置。"
    if plan.get("target") == "shot" and plan.get("patch"):
        text += f"调整：{plan['patch']}。"

    shot = {"text": text, "pose": pose, "references": references}
    return _with_questions(state, {"shot": shot, "shots": plan_shots(shot, scene["label"])})
