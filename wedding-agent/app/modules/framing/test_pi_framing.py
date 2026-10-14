import copy
import shutil

import pytest

from app.common.config import settings
from app.common.errors import ModuleError
from app.contracts import validate_update
from app.modules.framing import node
from app.modules.framing.schemas import Decision


def test_height_boundaries_and_wrong_band(load_state, asset_catalog):
    assert node.height_band([175, 170]) == "close"
    assert node.height_band([175, 169]) == "medium"
    assert node.height_band([175, 160]) == "medium"
    assert node.height_band([175, 159]) == "large"
    state = load_state("after_intake")
    state["brief"].update(heights_cm=[185, 160], pose="medium_a")
    assert node.frame(state)["shot"]["pose"] == "keep_original"


def test_no_mutation_and_no_retouch_questions(load_state):
    state = load_state("after_intake")
    state["retouch_plan"] = {"target": "shot", "patch": "保留原比例"}
    before = copy.deepcopy(state)
    result = node.frame(state)
    assert state == before
    assert "questions" not in result


@pytest.mark.skipif(shutil.which("node") is None, reason="Pi 集成测试需要 Node.js")
def test_real_pi_with_injected_langchain_model(load_state, asset_catalog, monkeypatch):
    monkeypatch.setattr(settings, "fake", False)
    state = load_state("after_intake")
    state["brief"]["pose"] = "medium_a"
    pose_url = settings.public_base_url + "/templates/poses/medium_a.png"
    outputs = iter([
        Decision(action="search_assets", kind="pose", tags=["medium"]),
        Decision(action="final", shot={
            "text": "平视半身构图，柔和侧光。", "pose": "medium_a",
            "references": [{"url": pose_url, "role": "pose"}],
        }),
    ])

    class Model:
        def with_structured_output(self, schema, **kwargs):
            assert schema is Decision
            return self

        def invoke(self, messages):
            return next(outputs)

    monkeypatch.setattr(node, "get_llm", lambda kind: Model())
    before = copy.deepcopy(state)
    result = node.frame(state)
    validate_update("frame", result)
    assert result["shot"]["pose"] == "medium_a"
    assert "175cm" in result["shot"]["text"]
    assert result["questions"]
    assert state == before


def test_real_failures_are_module_errors(load_state, monkeypatch):
    monkeypatch.setattr(settings, "fake", False)
    monkeypatch.setattr(node, "get_llm", lambda kind: (_ for _ in ()).throw(RuntimeError("missing")))
    with pytest.raises(ModuleError) as caught:
        node.frame(load_state("after_intake"))
    assert caught.value.code == "GENERATION_FAILED"
