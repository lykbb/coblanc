from copy import deepcopy

import pytest

from app.common.config import settings
from app.common.errors import ModuleError
from app.modules.review.calibration import calibrate


def data():
    annotations, predictions = [], []
    for split, label, similarity, number in [("calibration", False, 0.6, 1), ("calibration", True, 0.8, 2), ("validation", True, 0.6, 3)]:
        sample_id = f"sample_{number}"
        annotations.append({"sample_id": sample_id, "split": split, "person_group_id": f"group_{number}", "person_ids": [f"person_{number}_a", f"person_{number}_b"], "candidates": [{"image_id": "img_1", "labels": {"human_passed": label}, "review": {"status": "reviewed"}}]})
        predictions.append({"sample_id": sample_id, "metadata": {"mode": "synthetic_fixture", "face_model": "synthetic_vectors", "score_scale": "cosine_clipped_0_1", "vision_model": "mock", "prompt_version": "v1"}, "result": {"scores": [{"image_id": "img_1", "face_sim": [similarity, similarity], "body_ok": True, "hands_ok": True, "issues": [], "total": similarity}], "best_image_id": "img_1", "passed": True}})
    return annotations, predictions


def test_threshold_uses_only_calibration_data_and_never_changes_config():
    annotations, predictions = data()
    original = deepcopy((annotations, predictions))
    threshold = settings.face_sim_threshold
    result = calibrate(annotations, predictions, [0.5, 0.7, 0.9])
    assert result["recommended_threshold"] == 0.7
    assert result["validation"]["false_rejection"]["rate"] == 1.0
    assert result["config_changed"] is False
    assert settings.face_sim_threshold == threshold
    assert (annotations, predictions) == original


@pytest.mark.parametrize("field,value", [("person_group_id", "group_1"), ("person_ids", ["person_1_a", "someone_else"])])
def test_person_or_group_leakage_is_rejected(field, value):
    annotations, predictions = data()
    annotations[-1][field] = value
    with pytest.raises(ModuleError):
        calibrate(annotations, predictions)


def test_single_class_cannot_produce_recommendation():
    annotations, predictions = data()
    annotations[0]["candidates"][0]["labels"]["human_passed"] = True
    assert calibrate(annotations, predictions)["recommended_threshold"] is None


@pytest.mark.parametrize("grid", [[], [float("nan")], [-0.1], [1.1]])
def test_invalid_grid_is_rejected(grid):
    annotations, predictions = data()
    with pytest.raises(ModuleError):
        calibrate(annotations, predictions, grid)


def test_old_threshold_messages_do_not_lock_threshold_scan():
    from app.modules.review.evaluation import summarize
    annotations, predictions = data()
    predictions[1]["result"]["scores"][0]["issues"] = ["原图人物 A 与候选人脸相似度不足"]
    baseline = summarize([annotations[1]], [predictions[1]])
    rescored = summarize([annotations[1]], [predictions[1]], face_threshold=0.7)
    assert baseline["confusion"]["fn"] == 1
    assert rescored["confusion"]["tp"] == 1
    predictions[1]["result"]["scores"][0]["issues"].append("手部结构异常")
    assert summarize([annotations[1]], [predictions[1]], face_threshold=0.7)["confusion"]["fn"] == 1


@pytest.mark.parametrize("key", ["face_model", "score_scale", "vision_model", "prompt_version", "mode"])
def test_validation_signature_must_match_calibration(key):
    annotations, predictions = data()
    predictions[-1]["metadata"][key] = "different"
    with pytest.raises(ModuleError):
        calibrate(annotations, predictions)


def test_required_metadata_cannot_be_missing():
    annotations, predictions = data()
    predictions[0]["metadata"].pop("score_scale")
    with pytest.raises(ModuleError):
        calibrate(annotations, predictions)
