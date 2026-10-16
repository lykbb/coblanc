"""离线对比人工标注和 check 输出。只报告计数，不报告人物、图片或地址。"""

import argparse
import json
import sys
from math import isfinite
from pathlib import Path

from app.common.config import settings
from app.common.errors import ModuleError

from .quality import validate_scores as _scores, passes, detected_defects, face_threshold as checked_threshold
from .metadata import PUBLIC_FIELDS, run_signature


def _rate(numerator: int, denominator: int) -> dict:
    return {"numerator": numerator, "denominator": denominator, "rate": numerator / denominator if denominator else None}


def summarize(annotations: list[dict], predictions: list[dict], *, face_threshold: float | None = None) -> dict:
    """predictions 每项包含 sample_id 和 result（现有 check 返回值）。"""
    if not isinstance(annotations, list) or not isinstance(predictions, list):
        raise ModuleError("FILE_INVALID", "评测输入必须是标注列表和预测列表")
    try:
        threshold = checked_threshold(face_threshold)
    except ModuleError:
        raise ModuleError("FILE_INVALID", "评测人脸阈值必须在 0 到 1 之间")
    try:
        models = {}
        for prediction in predictions:
            sample_id = prediction["sample_id"]
            if not isinstance(sample_id, str) or not sample_id.strip() or sample_id in models:
                raise ValueError("duplicate sample")
            raw = prediction["result"]["scores"]
            candidates = [{"image_id": score["image_id"]} for score in raw]
            models[sample_id] = {score["image_id"]: score for score in _scores(raw, candidates, complete=True)}
        counts = {"tp": 0, "tn": 0, "fp": 0, "fn": 0}
        pending = missing = route_total = route_correct = 0
        missing_routes = recommendation_total = recommendation_correct = recommendation_missing = 0
        defect_counts = {name: {"missed": 0, "total": 0} for name in ("identity", "identity_a", "identity_b", "body", "hands", "subjects", "text", "requirements")}
        timings = {name: [] for name in ("check_seconds", "retouch_seconds", "model_invocations")}
        metadata = []
        missing_metadata = 0
        cases = {name: [] for name in ("false_accepts", "false_rejects", "missing_predictions", "pending", "route_mismatches", "missing_round_routes")}
        seen_samples = set()
        annotation_keys = set()
        for sample in annotations:
            sample_id = sample["sample_id"]
            if not isinstance(sample_id, str) or not sample_id.strip() or sample_id in seen_samples:
                raise ValueError("invalid sample id")
            seen_samples.add(sample_id)
            seen_images = set()
            reviewed_labels = {}
            for candidate in sample["candidates"]:
                image_id = candidate["image_id"]
                if not isinstance(image_id, str) or not image_id.strip() or image_id in seen_images:
                    raise ValueError("invalid image id")
                seen_images.add(image_id)
                annotation_keys.add((sample_id, image_id))
                label = candidate["labels"]["human_passed"]
                if label is not None and not isinstance(label, bool):
                    raise ValueError("invalid label")
                status = candidate["review"]["status"]
                if status not in {"pending", "reviewed", "adjudicated"}:
                    raise ValueError("invalid review status")
                if status not in {"reviewed", "adjudicated"}:
                    pending += 1
                    cases["pending"].append({"sample_id": sample_id, "image_id": image_id})
                    continue
                reviewed_labels[image_id] = label
                score = models.get(sample_id, {}).get(image_id)
                if score is None:
                    if label is None:
                        pending += 1
                        cases["pending"].append({"sample_id": sample_id, "image_id": image_id})
                    else:
                        missing += 1
                        cases["missing_predictions"].append({"sample_id": sample_id, "image_id": image_id})
                    continue
                if label is None:
                    pending += 1
                    cases["pending"].append({"sample_id": sample_id, "image_id": image_id})
                else:
                    passed = passes(score, threshold, rescore=face_threshold is not None)
                    key = "tp" if label and passed else "fn" if label else "fp" if passed else "tn"
                    counts[key] += 1
                    if key in {"fp", "fn"}:
                        cases["false_accepts" if key == "fp" else "false_rejects"].append({"sample_id": sample_id, "image_id": image_id})
                labels = candidate["labels"]
                identity = [labels.get("person_a_identity"), labels.get("person_b_identity")]
                for value in identity:
                    if value not in {None, "像本人", "不像本人", "无法判断"}:
                        raise ValueError("invalid identity label")
                detected = detected_defects(score, threshold, rescore=face_threshold is not None)
                defects = {
                    "identity": ("不像本人" in identity, detected["identity"]),
                    "identity_a": (identity[0] == "不像本人", score["face_sim"][0] < threshold),
                    "identity_b": (identity[1] == "不像本人", score["face_sim"][1] < threshold),
                    "body": (labels.get("body_ok") is False, not score["body_ok"]),
                    "hands": (labels.get("hands_ok") is False, not score["hands_ok"]),
                }
                for name, field in [
                    ("subjects", "subject_count_ok"),
                    ("text", "text_ok"),
                    ("requirements", "requirements_ok"),
                ]:
                    defects[name] = (labels.get(field) is False, detected[name])
                for field in ("body_ok", "hands_ok", "subject_count_ok", "text_ok", "requirements_ok"):
                    if labels.get(field) is not None and not isinstance(labels[field], bool):
                        raise ValueError("invalid defect label")
                for name, (present, detected) in defects.items():
                    if present:
                        defect_counts[name]["total"] += 1
                        defect_counts[name]["missed"] += not detected
            # 返工方案是整轮的，不能把一个方案重复算成四张图片的路由。
            expected = sample.get("expected_round_target")
            prediction = next((item for item in predictions if item["sample_id"] == sample_id), {})
            plan = prediction.get("retouch_plan")
            if expected is not None:
                if expected not in {"look", "shot", "prompt", "generate", "none"}:
                    raise ValueError("invalid target")
                if plan is not None:
                    from app.contracts import RetouchPlan
                    plan = RetouchPlan.model_validate(plan).model_dump()
                    route_total += 1
                    route_correct += plan["target"] == expected
                    if plan["target"] != expected:
                        cases["route_mismatches"].append({"sample_id": sample_id, "expected_target": expected, "actual_target": plan["target"]})
                else:
                    missing_routes += 1
                    cases["missing_round_routes"].append({"sample_id": sample_id})
            if prediction:
                best = prediction["result"].get("best_image_id")
                if best is None:
                    recommendation_missing += 1
                elif best not in models[sample_id]:
                    raise ValueError("invalid best image")
                elif reviewed_labels.get(best) is not None:
                    recommendation_total += 1
                    recommendation_correct += reviewed_labels[best]
                for name, values in timings.items():
                    value = prediction.get("timing", {}).get(name)
                    if value is not None:
                        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value < 0:
                            raise ValueError("invalid timing")
                        values.append(value)
                info = prediction.get("metadata", {})
                if not isinstance(info, dict):
                    raise ValueError("invalid metadata")
                filtered = {key: info[key] for key in PUBLIC_FIELDS if key in info}
                if "face_sim_threshold" in filtered:
                    if face_threshold is None and filtered["face_sim_threshold"] != threshold:
                        raise ValueError("threshold mismatch")
                if any(not isinstance(value, (str, int, float)) or isinstance(value, bool) for value in filtered.values()):
                    raise ValueError("invalid metadata value")
                if filtered and filtered not in metadata:
                    metadata.append(filtered)
                try:
                    run_signature(info)
                except ModuleError:
                    missing_metadata += 1
        return {
            "confusion": counts,
            "evaluated_images": sum(counts.values()),
            "pending_or_unjudgeable": pending,
            "missing_predictions": missing,
            "false_acceptance": _rate(counts["fp"], counts["fp"] + counts["tn"]),
            "false_rejection": _rate(counts["fn"], counts["fn"] + counts["tp"]),
            "round_route_agreement": _rate(route_correct, route_total),
            "missing_round_routes": missing_routes,
            "recommendation_quality": _rate(recommendation_correct, recommendation_total),
            "rounds_without_recommendation": recommendation_missing,
            "defect_miss_rates": {name: _rate(value["missed"], value["total"]) for name, value in defect_counts.items()},
            "timing": {name: {"samples": len(values), "mean": sum(values) / len(values) if values else None, "max": max(values) if values else None} for name, values in timings.items()},
            "run_metadata": metadata,
            "mixed_run_metadata": len(metadata) > 1,
            "evaluation_face_threshold": threshold,
            "explicit_threshold_rescore": face_threshold is not None,
            "missing_run_metadata": missing_metadata,
            "cases": cases,
            "unexpected_predictions": [{"sample_id": sample_id, "image_id": image_id} for sample_id, images in models.items() for image_id in images if (sample_id, image_id) not in annotation_keys],
        }
    except ModuleError:
        raise
    except (KeyError, TypeError, ValueError):
        raise ModuleError("FILE_INVALID", "标注或预测格式不正确，请检查编号、评分与人工标签")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("annotations", type=Path)
    parser.add_argument("predictions", type=Path)
    args = parser.parse_args()
    try:
        report = summarize(json.loads(args.annotations.read_text(encoding="utf-8")), json.loads(args.predictions.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        sys.stderr.write("FILE_INVALID: 无法读取有效的评测 JSON\n")
        return 1
    except ModuleError as error:
        sys.stderr.write(f"{error.code}: {error.message}\n")
        return 1
    sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
