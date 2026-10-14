"""运行时、离线评测和阈值扫描共同使用的质检规则。"""

from math import isfinite

from pydantic import ValidationError

from app.common.config import settings
from app.common.errors import ModuleError
from app.contracts import Score

THRESHOLD_ISSUES = {
    "原图人物 A 与候选人脸相似度不足",
    "原图人物 B 与候选人脸相似度不足",
}
ISSUE_TERMS = {
    "identity": ("人脸", "脸", "五官", "不像"),
    "body": ("身材", "比例", "身高"),
    "hands": ("手部", "手指"),
    "subjects": ("主体人数", "多余人物", "多余的人"),
    "text": ("乱码", "非预期文字"),
    "requirements": ("需求不一致", "风格", "婚纱", "妆容", "妆造", "服饰", "场景", "背景", "姿势"),
}


def face_threshold(value: float | None = None) -> float:
    value = settings.face_sim_threshold if value is None else value
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not isfinite(value) or not 0 <= value <= 1:
        raise ModuleError("GENERATION_FAILED", "人脸阈值配置必须是 0 到 1 之间的数值")
    return float(value)


def validate_feedback(raw: dict | None, candidates: list[dict]) -> dict:
    if raw is None or raw == {}:
        return {}
    if not isinstance(raw, dict):
        raise ModuleError("GENERATION_FAILED", "重做意见格式不正确，请重新提交")
    if raw.get("image_id") not in {candidate["image_id"] for candidate in candidates}:
        raise ModuleError("GENERATION_FAILED", "需要重做的图片不在当前候选中，请重新选择")
    reason = raw.get("reason") or "other"
    if not isinstance(reason, str) or reason not in {"face", "hands", "body", "style", "other"}:
        raise ModuleError("GENERATION_FAILED", "无法识别重做原因，请重新选择")
    if raw.get("note") is not None and not isinstance(raw["note"], str):
        raise ModuleError("GENERATION_FAILED", "重做说明必须是文字")
    return {"image_id": raw["image_id"], "reason": reason, "note": raw.get("note")}


def validate_scores(raw: list[dict], candidates: list[dict], complete: bool = False) -> list[dict]:
    try:
        scores = [Score.model_validate(item, strict=True).model_dump() for item in raw]
        ids = [item["image_id"] for item in scores]
        current = {item["image_id"] for item in candidates}
        if any(not image_id.strip() for image_id in ids) or len(ids) != len(set(ids)) or not set(ids) <= current or (complete and set(ids) != current):
            raise ValueError("scores do not match candidates")
        for score in scores:
            if not all(isfinite(value) and 0 <= value <= 1 for value in [*score["face_sim"], score["total"]]):
                raise ValueError("invalid score")
            score["issues"] = list(dict.fromkeys(issue.strip() for issue in score["issues"] if issue.strip()))
    except (ValidationError, TypeError, ValueError):
        raise ModuleError("GENERATION_FAILED", "质检评分缺失或格式不正确，请重新质检") from None
    return scores


def passes(score: dict, threshold: float | None = None, *, rescore: bool = False) -> bool:
    threshold = face_threshold(threshold)
    issues = [issue for issue in score["issues"] if not rescore or issue not in THRESHOLD_ISSUES]
    return min(score["face_sim"]) >= threshold and score["body_ok"] and score["hands_ok"] and not issues


def detected_defects(score: dict, threshold: float | None = None, *, rescore: bool = False) -> dict[str, bool]:
    threshold = face_threshold(threshold)
    issues = "；".join(issue for issue in score["issues"] if not rescore or issue not in THRESHOLD_ISSUES)
    result = {name: any(term in issues for term in terms) for name, terms in ISSUE_TERMS.items()}
    result["identity"] |= min(score["face_sim"]) < threshold
    result["body"] |= not score["body_ok"]
    result["hands"] |= not score["hands_ok"]
    return result


def route_for_score(score: dict) -> str:
    defects = detected_defects(score)
    if defects["identity"] or defects["hands"] or defects["subjects"]:
        return "generate"
    if defects["body"] or any(term in "；".join(score["issues"]) for term in ("场景", "背景", "姿势")):
        return "shot"
    if any(term in "；".join(score["issues"]) for term in ("风格", "婚纱", "妆容", "妆造", "服饰")):
        return "look"
    return "prompt"
