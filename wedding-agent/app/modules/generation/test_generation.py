import pytest

from app.common.config import settings
from app.common.errors import ModuleError
from app.modules.generation import build_prompt, generate


def test_fake_returns_four_candidates(load_state):
    update = generate(load_state("after_generation") | {"generation": {}})
    assert [c["image_id"] for c in update["candidates"]] == ["img_1", "img_2", "img_3", "img_4"]
    assert update["generation"]["total_images"] == 4
    assert update["prompt"].startswith("保持图中两人")


def test_image_ids_continue_across_rounds(load_state):
    update = generate(load_state("after_generation"))
    assert [c["image_id"] for c in update["candidates"]] == ["img_5", "img_6", "img_7", "img_8"]
    assert update["generation"]["total_images"] == 8


def test_stops_at_image_limit(load_state, monkeypatch):
    monkeypatch.setattr(settings, "max_images_per_task", 4)
    with pytest.raises(ModuleError) as error:
        generate(load_state("after_generation"))
    assert error.value.code == "GENERATION_FAILED"


def test_prompt_includes_look_shot_and_patch(load_state):
    state = load_state("after_generation")
    state["retouch_plan"] = {"target": "generate", "patch": "新娘的脸更像原图", "image_id": None}
    prompt = build_prompt(state)
    assert "韩式婚纱照造型" in prompt
    assert "简洁的室内影棚" in prompt
    assert "新娘的脸更像原图" in prompt
