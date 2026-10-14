"""评测修图师。

check：给每张候选打分，选出最好的一张，判断是否通过质检。
retouch（agent）：根据质检问题或用户的重做原因，决定退回哪一块、怎么改。
"""

from pydantic import ValidationError

from app.common.config import settings
from app.common.errors import ModuleError
from app.contracts import Candidate
from app.state import WeddingState

from .real import check_real, propose_retouch
from .quality import passes as _passes, validate_scores as _scores, route_for_score as _target, face_threshold, validate_feedback

# 用户重做原因 → 退回哪一块：generate 生图重拍，shot 摄影师，look 妆造师，prompt 小囍改提示词
REASON_TARGET = {"face": "generate", "hands": "generate", "body": "shot", "style": "look", "other": "prompt"}


def check(state: WeddingState) -> dict:
    face_threshold()
    candidates = _candidates(state)
    if settings.fake_for("review"):
        scores = _fake_scores(state, candidates)
    else:
        scores = check_real(state, candidates)

    scores = _scores(scores, candidates, complete=True)
    passing = [score for score in scores if _passes(score)]
    best = max(passing, key=lambda score: score["total"])["image_id"] if passing else None
    return {"scores": scores, "best_image_id": best, "passed": bool(passing)}


def retouch(state: WeddingState) -> dict:
    candidates = _candidates(state)
    scores = _scores(state.get("scores") or [], candidates)
    feedback = validate_feedback(state.get("user_feedback"), candidates)
    if settings.fake_for("review"):
        if feedback:
            reason = feedback.get("reason") or "other"
            target = REASON_TARGET[reason]
            patch = feedback.get("note") or _default_patch(target)
            return {"retouch_plan": {"target": target, "patch": patch, "image_id": None}}
        else:
            passing = [score for score in scores if _passes(score)]
            if passing:
                best = max(passing, key=lambda score: score["total"])
                return {"retouch_plan": {"target": "none", "patch": "使用已通过质检的候选图", "image_id": best["image_id"]}}
            # 从最有希望的候选的问题制定下一步；没有评分时保持骨架的生图回退。
            score = max(scores, key=lambda item: item["total"]) if scores else None
            target = _target(score) if score else "generate"
            patch = _default_patch(target)
            if score and score["issues"]:
                patch += "；需修正：" + "；".join(score["issues"])
        return {"retouch_plan": {"target": target, "patch": patch, "image_id": None}}
    scores = _scores(scores, candidates, complete=True)
    return {"retouch_plan": propose_retouch(state, scores, feedback, {score["image_id"] for score in scores if _passes(score)})}


def _candidates(state: WeddingState) -> list[dict]:
    try:
        candidates = [Candidate.model_validate(item).model_dump() for item in state.get("candidates", [])]
        ids = [item["image_id"] for item in candidates]
        if not ids or any(not image_id.strip() for image_id in ids) or len(set(ids)) != len(ids):
            raise ValueError("empty or duplicate candidates")
    except (ValidationError, TypeError, ValueError):
        raise ModuleError("GENERATION_FAILED", "候选图片缺失或格式不正确，请重新生成") from None
    return candidates


def _default_patch(target: str) -> str:
    return {
        "generate": "加强两人五官与原图的一致性，修正手部并保持只有两位主体",
        "shot": "修正身材比例，保持原图身高差和体型，必要时恢复原图姿势",
        "look": "按已确认的风格调整婚纱和妆造，保留用户要求保留的特征",
        "prompt": "澄清拍摄指令，保持人物特征和已确认的需求，避免乱码文字",
    }[target]


def _fake_scores(state: WeddingState, candidates: list[dict]) -> list[dict]:
    # FAKE_FAIL_FIRST_CHECK=1 时第一次质检全部不合格，用来演示修图流程
    fail = settings.fake_fail_first_check and state.get("retry_count", 0) == 0 and not state.get("user_feedback")
    scores = []
    for i, candidate in enumerate(candidates):
        face_sim = [0.42, 0.81] if fail else [round(0.86 - 0.02 * i, 2), round(0.82 - 0.01 * i, 2)]
        scores.append(
            {
                "image_id": candidate["image_id"],
                "face_sim": face_sim,
                "body_ok": True,
                "hands_ok": True,
                "issues": ["新娘不太像本人"] if fail else [],
                "total": round(sum(face_sim) / 2, 3),
            }
        )
    return scores
