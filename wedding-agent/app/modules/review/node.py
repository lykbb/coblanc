"""评测修图师。

check：给每张候选打分，选出最好的一张，判断是否通过质检。
retouch（agent）：根据质检问题或用户的重做原因，决定退回哪一块、怎么改。
"""

from app.common.config import settings
from app.state import WeddingState

# 用户重做原因 → 退回哪一块
REASON_TARGET = {"face": "generate", "hands": "generate", "body": "shot", "style": "look", "other": "generate"}


def check(state: WeddingState) -> dict:
    candidates = state.get("candidates", [])
    if settings.fake_for("review"):
        scores = _fake_scores(state, candidates)
    else:
        # TODO(评测修图师)：
        #   1. 人脸相似度：两个人分别和原图比（InsightFace 或云厂商人脸比对 API）
        #   2. get_llm("vision") 检查身材比例、手部、多余的人、乱码文字
        #   3. 每张输出 image_id、face_sim（两个数）、body_ok、hands_ok、issues、total
        raise NotImplementedError("质检的真实实现还没写，见《小囍模块接入规范》模块卡片 6")

    passing = [
        score
        for score in scores
        if min(score["face_sim"]) >= settings.face_sim_threshold and score["body_ok"] and score["hands_ok"]
    ]
    best = max(passing, key=lambda score: score["total"])["image_id"] if passing else None
    return {"scores": scores, "best_image_id": best, "passed": bool(passing)}


def retouch(state: WeddingState) -> dict:
    feedback = state.get("user_feedback") or {}
    if settings.fake_for("review"):
        if feedback:
            target = REASON_TARGET.get(feedback.get("reason") or "other", "generate")
            patch = feedback.get("note") or "按用户的意见调整"
        else:
            target, patch = "generate", "加强两人五官与原图的一致性"
        return {"retouch_plan": {"target": target, "patch": patch, "image_id": None}}
    # TODO(评测修图师)：用 get_llm("agent") 根据 scores 里的 issues 或 user_feedback 决定 target：
    #   脸不像、手部问题 → generate；身材比例 → shot；风格不对 → look；已有另一张合格 → none + image_id
    raise NotImplementedError("修图方案的真实实现还没写，见《小囍模块接入规范》模块卡片 6")


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
