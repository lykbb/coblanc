"""真实分支：资产库读图、人脸服务比较、视觉评测和修图 agent。"""

import json
from math import isfinite
from time import monotonic

from pydantic import ValidationError

from app.common.config import settings
from app.common.errors import ModuleError
from app.contracts import RetouchPlan
from app.modules.assets import load_image
from app.state import Brief, WeddingState

from . import face_compare
from .face_compare import compare_faces, provider_metadata
from .model_calls import read_prompt, structured_call
from .vision import finding_issues, finding_notes, inspect_candidates
from .asset_inputs import read_images
from .quality import face_threshold, passes, route_for_score, validate_scores, rule_plan, default_patch


def check_real(state: WeddingState, candidates: list[dict], *, caller=None, comparator=None, loader=None, stats=None, simulated: bool = False) -> list[dict]:
    # 没传比对器且人脸服务未接入时，退回只用视觉模型检查，结果标记 face_compare=skipped。
    comparator = comparator or compare_faces
    skip_face = comparator is face_compare.compare_faces and not provider_metadata()["connected"]
    loader = loader or load_image
    threshold = face_threshold()
    source, images = read_images(state, candidates, loader=loader)
    if skip_face:
        return _vision_only_scores(state, source, images, threshold, caller=caller, stats=stats)
    # 校验格式并先做人脸比较；没有已配置的人脸服务时，不会发起视觉付费请求。
    face_scores = {}
    for image_id, data in images:
        started = monotonic()
        success = False
        try:
            faces = comparator(source, data)
            if len(faces) != 2 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) or not 0 <= v <= 1 for v in faces):
                raise ValueError("invalid face scores")
            face_scores[image_id] = [float(v) for v in faces]
            success = True
        except ModuleError:
            raise
        except Exception:
            raise ModuleError("GENERATION_FAILED", "人脸比对结果格式不正确，请重新质检") from None
        finally:
            if stats is not None:
                stats.record("face", monotonic() - started, 0, success, simulated=simulated)
    findings = inspect_candidates(source, images, state.get("brief") or {}, caller=caller, stats=stats)
    scores = []
    for image_id, _ in images:
        finding = findings[image_id]
        faces = face_scores[image_id]
        issues = finding_issues(finding)
        for index, value in enumerate(faces):
            if value < threshold:
                issues.append(f"原图人物 {'A' if index == 0 else 'B'} 与候选人脸相似度不足")
        scores.append({"image_id": image_id, "face_sim": faces, "body_ok": finding.body_ok, "hands_ok": finding.hands_ok, "issues": issues,
                       "notes": finding_notes(finding), "total": round(sum(faces) / 2, 3)})
    return scores


def _vision_only_scores(state, source, images, threshold, *, caller=None, stats=None) -> list[dict]:
    """人脸比对不可用时的退路：face_sim 记为阈值（不代表真实相似度），只看视觉模型的结论；
    视觉模型只在「明显不是本人」时判身份不合格，轻微差异进 notes。"""
    findings = inspect_candidates(source, images, state.get("brief") or {}, caller=caller, stats=stats)
    scores = []
    for image_id, _ in images:
        finding = findings[image_id]
        issues = finding_issues(finding)
        notes = finding_notes(finding)
        total = round(threshold if issues else min(1.0, threshold + 0.1 - 0.01 * len(notes)), 3)
        scores.append({"image_id": image_id, "face_sim": [threshold, threshold], "body_ok": finding.body_ok,
                       "hands_ok": finding.hands_ok, "issues": issues, "notes": notes, "total": total, "face_compare": "skipped"})
    return scores


def propose_retouch(state: WeddingState, scores: list[dict], feedback: dict, qualified_ids: set[str], *, caller=None, stats=None) -> dict:
    caller = caller or structured_call
    if not scores:
        raise ModuleError("GENERATION_FAILED", "请先完成候选质检，再制定修图方案")
    scores = validate_scores(scores, [{"image_id": item["image_id"]} for item in scores], complete=True)
    actual_qualified = {score["image_id"] for score in scores if passes(score)}
    if actual_qualified != qualified_ids:
        raise ModuleError("GENERATION_FAILED", "修图输入的合格候选与评分不一致，请重新质检")
    required_target = "none" if actual_qualified else route_for_score(max(scores, key=lambda score: score["total"]))
    try:
        brief = Brief.model_validate(state.get("brief") or {}).model_dump()
    except ValidationError:
        raise ModuleError("GENERATION_FAILED", "修图需求单格式不正确") from None
    brief = {key: value for key, value in brief.items() if key not in {"invitation", "materials", "missing", "intent"}}
    payload = {"brief": brief, "scores": scores, "user_feedback": feedback, "qualified_image_ids": sorted(qualified_ids), "required_target_without_feedback": required_target, "retry_count": state.get("retry_count", 0)}
    fallback = rule_plan(scores, feedback)
    try:
        plan = caller("agent", RetouchPlan, [("system", read_prompt("retouch.md")), ("human", json.dumps(payload, ensure_ascii=False))], stats=stats).model_dump()
    except Exception:
        # 输入校验在调用前完成；模型或提示词失败仅影响说明，不改变规则方向。
        return fallback
    target = fallback["target"]
    image_id = plan.get("image_id") if target == "none" and plan.get("image_id") in qualified_ids else fallback["image_id"]
    return {"target": target, "patch": plan["patch"].strip() or default_patch(target), "image_id": image_id}
