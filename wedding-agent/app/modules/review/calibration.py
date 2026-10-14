"""离线阈值扫描；不改 settings 或 .env，不使用验收集选择阈值。"""

import argparse
import json
import sys
from pathlib import Path

from app.common.config import settings
from app.common.errors import ModuleError

from .evaluation import summarize
from .metadata import consistent_signature


def calibrate(annotations: list[dict], predictions: list[dict], thresholds: list[float] | None = None) -> dict:
    try:
        identities = {"calibration": set(), "validation": set()}
        groups = {"calibration": set(), "validation": set()}
        splits = {"calibration": [], "validation": []}
        for sample in annotations:
            split = sample["split"]
            group = sample["person_group_id"]
            persons = sample["person_ids"]
            if split not in splits or not isinstance(group, str) or not group.strip() or not isinstance(persons, list) or len(persons) != 2 or len(set(persons)) != 2 or any(not isinstance(person, str) or not person.strip() for person in persons):
                raise ValueError("invalid split or identity references")
            groups[split].add(group)
            identities[split].update(persons)
            splits[split].append(sample)
        if identities["calibration"] & identities["validation"] or groups["calibration"] & groups["validation"]:
            raise ValueError("identity leakage")
        if not splits["calibration"]:
            raise ValueError("no calibration set")
        # 标定与验收必须来自同一运行签名，不能只检查标定集内部。
        consistent_signature(predictions)
        if {item["sample_id"] for item in predictions} != {sample["sample_id"] for sample in annotations}:
            raise ValueError("sample coverage mismatch")
        # 先验证全体编号与分数。
        combined = summarize(annotations, predictions)
        if combined["unexpected_predictions"]:
            raise ValueError("unexpected prediction images")
        by_id = {item["sample_id"]: item for item in predictions}
        calibration_predictions = [by_id[sample["sample_id"]] for sample in splits["calibration"] if sample["sample_id"] in by_id]
        if thresholds is None:
            thresholds = sorted({settings.face_sim_threshold, 1.0, *[min(score["face_sim"]) for item in calibration_predictions for score in item["result"]["scores"]]})
        if not thresholds:
            raise ValueError("empty threshold grid")
        scans = [{"threshold": threshold, "metrics": summarize(splits["calibration"], calibration_predictions, face_threshold=threshold)} for threshold in thresholds]
        first = scans[0]["metrics"]
        if first["missing_predictions"] or first["false_acceptance"]["denominator"] == 0 or first["false_rejection"]["denominator"] == 0:
            return {"recommended_threshold": None, "reason": "标定集缺少完整预测、合格样本或不合格样本，不能推荐阈值", "scans": scans, "validation": None}
        # 首先压低误放行，其次压低误拦截；同等效果取最接近现配置的阈值。
        best = min(scans, key=lambda item: (item["metrics"]["false_acceptance"]["rate"], item["metrics"]["false_rejection"]["rate"], abs(item["threshold"] - settings.face_sim_threshold), item["threshold"]))
        validation_predictions = [by_id[sample["sample_id"]] for sample in splits["validation"] if sample["sample_id"] in by_id]
        validation = summarize(splits["validation"], validation_predictions, face_threshold=best["threshold"]) if splits["validation"] else None
        return {"recommended_threshold": best["threshold"], "selection_policy": "先最小误放行，再最小误拦截；仅用标定集选阈值", "scans": scans, "validation": validation, "config_changed": False}
    except ModuleError:
        raise
    except (KeyError, TypeError, ValueError):
        raise ModuleError("FILE_INVALID", "标定数据不完整、人物跨集合泄漏或版本混合，请检查数据划分") from None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("annotations", type=Path)
    parser.add_argument("predictions", type=Path)
    parser.add_argument("--thresholds", type=float, nargs="+")
    args = parser.parse_args()
    try:
        report = calibrate(json.loads(args.annotations.read_text(encoding="utf-8")), json.loads(args.predictions.read_text(encoding="utf-8")), args.thresholds)
    except (OSError, ValueError):
        sys.stderr.write("FILE_INVALID: 无法读取有效的标定 JSON\n")
        return 1
    except ModuleError as error:
        sys.stderr.write(f"{error.code}: {error.message}\n")
        return 1
    sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
