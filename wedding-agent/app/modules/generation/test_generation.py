import pytest

from app.common.config import settings
from app.common.errors import ModuleError
from app.modules.generation import generate


def test_fake_returns_four_candidates(load_state):
    update = generate(load_state("after_generation") | {"generation": {}})
    assert [c["image_id"] for c in update["candidates"]] == ["img_1", "img_2", "img_3", "img_4"]
    assert update["generation"]["total_images"] == 4


def test_does_not_rewrite_prompt(load_state):
    assert "prompt" not in generate(load_state("after_generation"))


def test_image_ids_continue_across_rounds(load_state):
    update = generate(load_state("after_generation"))
    assert [c["image_id"] for c in update["candidates"]] == ["img_5", "img_6", "img_7", "img_8"]
    assert update["generation"]["total_images"] == 8


def test_stops_at_image_limit(load_state, monkeypatch):
    monkeypatch.setattr(settings, "max_images_per_task", 4)
    with pytest.raises(ModuleError) as error:
        generate(load_state("after_generation"))
    assert error.value.code == "GENERATION_FAILED"
