from copy import deepcopy

import pytest

from app.common.errors import ModuleError
from app.modules.review.evaluation import summarize


def example_data():
    labels = [True, False, False, True, None]
    outputs = [True, False, True, False, True]
    annotation = {"sample_id": "sample_1", "expected_round_target": "generate", "candidates": [{"image_id": f"img_{i}", "labels": {"human_passed": label}, "review": {"status": "reviewed"}} for i, label in enumerate(labels)]}
    scores = [{"image_id": f"img_{i}", "face_sim": [0.9, 0.9], "body_ok": True, "hands_ok": passed, "issues": [] if passed else ["手部结构异常"], "total": 0.9} for i, passed in enumerate(outputs)]
    predictions = [{"sample_id": "sample_1", "result": {"scores": scores, "best_image_id": "img_0", "passed": True}, "retouch_plan": {"target": "generate", "patch": "修正手部", "image_id": None}}]
    return [annotation], predictions


def test_confusion_rates_ignore_unjudgeable_labels():
    annotations, predictions = example_data()
    original = deepcopy((annotations, predictions))
    result = summarize(annotations, predictions)
    assert result["confusion"] == {"tp": 1, "tn": 1, "fp": 1, "fn": 1}
    assert result["evaluated_images"] == 4
    assert result["pending_or_unjudgeable"] == 1
    assert result["false_acceptance"]["rate"] == 0.5
    assert result["false_rejection"]["rate"] == 0.5
    assert result["round_route_agreement"] == {"numerator": 1, "denominator": 1, "rate": 1.0}
    assert (annotations, predictions) == original


def test_no_data_rates_are_null():
    result = summarize([], [])
    assert result["false_acceptance"]["rate"] is None
    assert result["false_rejection"]["rate"] is None
    assert result["round_route_agreement"]["rate"] is None


def test_missing_predictions_are_reported_not_treated_as_rejections():
    annotations, _ = example_data()
    result = summarize(annotations, [])
    assert result["missing_predictions"] == 4
    assert result["evaluated_images"] == 0


def test_pending_labels_do_not_count_as_ground_truth():
    annotations, predictions = example_data()
    annotations[0]["candidates"][0]["review"]["status"] = "pending"
    assert summarize(annotations, predictions)["evaluated_images"] == 3


@pytest.mark.parametrize("kind", ["duplicate_sample", "duplicate_image", "string_label", "bad_target", "nonfinite_score"])
def test_invalid_data_is_rejected(kind):
    annotations, predictions = example_data()
    if kind == "duplicate_sample":
        predictions.append(deepcopy(predictions[0]))
    elif kind == "duplicate_image":
        annotations[0]["candidates"].append(deepcopy(annotations[0]["candidates"][0]))
    elif kind == "string_label":
        annotations[0]["candidates"][0]["labels"]["human_passed"] = "false"
    elif kind == "bad_target":
        annotations[0]["expected_round_target"] = "anything"
    else:
        predictions[0]["result"]["scores"][0]["total"] = float("nan")
    with pytest.raises(ModuleError):
        summarize(annotations, predictions)


def test_defects_recommendations_timing_and_metadata():
    annotations, predictions = example_data()
    candidate = annotations[0]["candidates"][2]
    candidate["labels"].update(person_a_identity="不像本人", hands_ok=False, text_ok=False)
    predictions[0]["timing"] = {"check_seconds": 2.0, "retouch_seconds": 1.0, "model_invocations": 2}
    predictions[0]["metadata"] = {"mode": "mock", "prompt_version": "v1", "face_sim_threshold": 0.5, "api_key": "do not include"}
    result = summarize(annotations, predictions)
    assert result["defect_miss_rates"]["identity"]["rate"] == 1.0
    assert result["defect_miss_rates"]["hands"]["rate"] == 1.0
    assert result["defect_miss_rates"]["text"]["rate"] == 1.0
    assert result["defect_miss_rates"]["body"]["rate"] is None
    assert result["recommendation_quality"]["rate"] == 1.0
    assert result["timing"]["check_seconds"]["mean"] == 2.0
    assert "api_key" not in str(result)


def test_missing_routes_are_counted():
    annotations, predictions = example_data()
    predictions[0].pop("retouch_plan")
    assert summarize(annotations, predictions)["missing_round_routes"] == 1


@pytest.mark.parametrize("metadata", [{"face_sim_threshold": 0.2}, {"face_sim_threshold": float("nan")}])
def test_threshold_mismatch_is_not_silently_aggregated(metadata):
    annotations, predictions = example_data()
    predictions[0]["metadata"] = metadata
    with pytest.raises(ModuleError):
        summarize(annotations, predictions)


def test_person_a_miss_is_not_hidden_by_person_b_detection():
    annotations, predictions = example_data()
    annotations[0]["candidates"][2]["labels"].update(person_a_identity="不像本人", person_b_identity="像本人")
    predictions[0]["result"]["scores"][2]["face_sim"] = [0.9, 0.1]
    result = summarize(annotations, predictions)
    assert result["defect_miss_rates"]["identity"]["rate"] == 0.0
    assert result["defect_miss_rates"]["identity_a"]["rate"] == 1.0
    assert result["defect_miss_rates"]["identity_b"]["rate"] is None


def test_report_lists_wrong_and_missing_cases():
    annotations, predictions = example_data()
    result = summarize(annotations, predictions)
    assert result["cases"]["false_accepts"] == [{"sample_id": "sample_1", "image_id": "img_2"}]
    assert result["cases"]["false_rejects"] == [{"sample_id": "sample_1", "image_id": "img_3"}]
    missing = summarize(annotations, [])
    assert len(missing["cases"]["missing_predictions"]) == 4


def test_unexpected_prediction_is_visible_in_report():
    annotations, predictions = example_data()
    extra = deepcopy(predictions[0]["result"]["scores"][0])
    extra["image_id"] = "old_image"
    predictions[0]["result"]["scores"].append(extra)
    assert summarize(annotations, predictions)["unexpected_predictions"] == [{"sample_id": "sample_1", "image_id": "old_image"}]
