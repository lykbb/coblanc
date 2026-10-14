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
from .quality import passes as _passes, validate_scores as _scores, route_for_score as _target, face_threshold, validate_feedback, rule_plan, default_patch as _default_patch, REASON_TARGET

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
        return {"retouch_plan": rule_plan(scores, feedback)}
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
