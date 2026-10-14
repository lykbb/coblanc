import pytest

from app.modules.assets import load_image, make_previews, package, save_image, search_assets


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


def test_package_deletes_grouped_originals_when_consent_allows(load_state):
    state = load_state("after_generation")
    original = state["photo_urls"][0]
    state["groom_photo_urls"] = [original]
    state["bride_photo_urls"] = [original]
    state["consent"] = {"confirmed": True, "delete_original": True}
    package(state)
    with pytest.raises(FileNotFoundError):
        load_image(original)


def test_search_by_kind_and_tags(asset_catalog):
    poses = search_assets("pose")
    assert [item["asset_id"] for item in poses] == ["pose_medium_a"]  # 文件缺失的那条不返回
    assert poses[0]["url"].endswith("/templates/poses/medium_a.png")
    assert search_assets("outfit", ["korean_studio"])[0]["asset_id"] == "outfit_korean_satin"
    assert search_assets("outfit", ["chinese_red"]) == []


def test_search_rejects_unknown_kind():
    with pytest.raises(ValueError):
        search_assets("shoes")


def test_empty_catalog_returns_nothing():
    assert search_assets("pose") == []

def test_load_template_reference(asset_catalog):
    from app.common.config import settings
    from app.modules.assets import load_image, search_assets

    reference = search_assets("pose", ["medium"])[0]
    assert load_image(reference["url"]).startswith(b"\x89PNG")
    import pytest
    with pytest.raises(ValueError):
        load_image(settings.public_base_url + "/templates/../../private.txt")
