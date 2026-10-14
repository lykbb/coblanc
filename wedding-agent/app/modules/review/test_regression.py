import json
from copy import deepcopy
from pathlib import Path

import pytest

from app.common.errors import ModuleError
from app.modules.review.regression import compare_runs


def example():
    folder = Path(__file__).parent / "examples"
    annotations = json.loads((folder / "synthetic_annotations.json").read_text(encoding="utf-8"))
    baseline = json.loads((folder / "synthetic_predictions.json").read_text(encoding="utf-8"))
    return annotations, baseline, deepcopy(baseline)


def test_regression_reports_both_improvement_and_rejection_cost():
    annotations, baseline, current = example()
    for run in current:
        run["metadata"].update(face_sim_threshold=0.7, prompt_version="synthetic_v2")
        if run["result"]["scores"][0]["face_sim"][0] < 0.7:
            run["result"].update(best_image_id=None, passed=False)
    original = deepcopy((annotations, baseline, current))
    report = compare_runs(annotations, baseline, current)
    assert report["status"] == "compared"
    assert report["rate_deltas_current_minus_baseline"]["false_acceptance"] == -1.0
    assert report["rate_deltas_current_minus_baseline"]["false_rejection"] == 0.5
    assert len(report["changed_cases"]) == 8
    assert report["config_changed"] is False
    assert (annotations, baseline, current) == original


@pytest.mark.parametrize("kind", ["missing_image", "missing_sample", "dataset", "scale", "mode", "missing_metadata", "duplicate"])
def test_incomparable_runs_are_rejected(kind):
    annotations, baseline, current = example()
    if kind == "missing_image":
        current[0]["result"]["scores"].pop()
    elif kind == "missing_sample":
        current.pop()
    elif kind == "duplicate":
        current.append(deepcopy(current[0]))
    elif kind == "missing_metadata":
        current[0]["metadata"].pop("face_model")
    else:
        field = {"dataset": "dataset_version", "scale": "score_scale", "mode": "mode"}[kind]
        for run in current:
            run["metadata"][field] = "different"
    with pytest.raises(ModuleError):
        compare_runs(annotations, baseline, current)


def test_no_reviewed_labels_cannot_be_claimed_as_comparison():
    annotations, baseline, current = example()
    for sample in annotations:
        for candidate in sample["candidates"]:
            candidate["review"]["status"] = "pending"
    report = compare_runs(annotations, baseline, current)
    assert report["status"] == "insufficient_labels"
    assert report["rate_deltas_current_minus_baseline"]["false_acceptance"] is None
