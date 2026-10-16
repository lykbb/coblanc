"""同一标注集的新旧运行对比；版本变化可以比较，样本缺失不能静默忽略。"""

import argparse
import json
import sys
from pathlib import Path

from app.common.errors import ModuleError

from .evaluation import summarize
from .metadata import consistent_signature
from .quality import face_threshold, passes, validate_scores


def compare_runs(annotations: list[dict], baseline: list[dict], current: list[dict]) -> dict:
    try:
        signatures = [consistent_signature(run) for run in (baseline, current)]
        if signatures[0][0] != signatures[1][0] or signatures[0][2] != signatures[1][2]:
            raise ValueError("different mode or scale")
        versions = [{item.get("metadata", {}).get("dataset_version") for item in run} for run in (baseline, current)]
        if any(len(version) != 1 or not all(isinstance(value, str) and value.strip() for value in version) for version in versions) or versions[0] != versions[1]:
            raise ValueError("dataset version mismatch")
        expected = {(sample["sample_id"], candidate["image_id"]) for sample in annotations for candidate in sample["candidates"]}
        indexed = []
        thresholds = []
        metrics = []
        for run in (baseline, current):
            values = {item["metadata"].get("face_sim_threshold") for item in run}
            if len(values) != 1 or None in values:
                raise ValueError("threshold missing or mixed")
            threshold = face_threshold(next(iter(values)))
            scores = {}
            for item in run:
                raw = item["result"]["scores"]
                validated = validate_scores(raw, [{"image_id": score["image_id"]} for score in raw], complete=True)
                for score in validated:
                    key = (item["sample_id"], score["image_id"])
                    if key in scores:
                        raise ValueError("duplicate prediction")
                    scores[key] = score
            if set(scores) != expected:
                raise ValueError("coverage mismatch")
            indexed.append(scores)
            thresholds.append(threshold)
            metrics.append(summarize(annotations, run, face_threshold=threshold))
        before, after = metrics
        deltas = {}
        for key in ("false_acceptance", "false_rejection", "recommendation_quality", "round_route_agreement"):
            previous, latest = before[key]["rate"], after[key]["rate"]
            deltas[key] = latest - previous if previous is not None and latest is not None else None
        deltas["defect_miss_rates"] = {name: after["defect_miss_rates"][name]["rate"] - value["rate"] if value["rate"] is not None and after["defect_miss_rates"][name]["rate"] is not None else None for name, value in before["defect_miss_rates"].items()}
        changed = []
        for sample_id, image_id in sorted(expected):
            key = (sample_id, image_id)
            old = passes(indexed[0][key], thresholds[0], rescore=True)
            new = passes(indexed[1][key], thresholds[1], rescore=True)
            if old != new:
                changed.append({"sample_id": sample_id, "image_id": image_id, "baseline_passed": old, "current_passed": new})
        return {"status": "compared" if after["evaluated_images"] else "insufficient_labels", "baseline": before, "current": after, "rate_deltas_current_minus_baseline": deltas, "changed_cases": changed, "config_changed": False}
    except ModuleError:
        raise
    except (KeyError, TypeError, ValueError):
        raise ModuleError("FILE_INVALID", "基线对比需要相同样本、数据集版本、模式及分数尺度，并记录各自阈值")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("annotations", type=Path)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("current", type=Path)
    args = parser.parse_args()
    try:
        inputs = [json.loads(path.read_text(encoding="utf-8")) for path in (args.annotations, args.baseline, args.current)]
        report = compare_runs(*inputs)
    except (OSError, ValueError):
        sys.stderr.write("FILE_INVALID: 无法读取有效的回归 JSON\n")
        return 1
    except ModuleError as error:
        sys.stderr.write(f"{error.code}: {error.message}\n")
        return 1
    sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
