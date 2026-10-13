import pytest

from app.modules.assets import get_template, load_image, make_previews, package, save_image


def test_save_and_load_roundtrip(png_bytes):
    url = save_image(png_bytes, "upload")
    assert url.endswith(".png")
    assert load_image(url) == png_bytes


def test_rejects_non_image():
    with pytest.raises(ValueError):
        save_image(b"not an image", "upload")


def test_rejects_foreign_url():
    with pytest.raises(ValueError):
        load_image("http://example.com/files/upload/x.png")


def test_previews_put_best_first(load_state):
    state = load_state("after_generation")
    state["best_image_id"] = "img_2"
    previews = make_previews(state)["previews"]
    assert len(previews) == 4
    assert previews[0]["image_id"] == "img_2" and previews[0]["is_best"]


def test_package_outputs_all_materials(load_state):
    deliverables = package(load_state("after_generation"))["deliverables"]
    assert set(deliverables) == {"photo", "invitation", "welcome_poster", "led_screen", "moments"}


def test_missing_template_returns_none():
    assert get_template("poses/no_such_pose.png") is None
