"""契约测试：检查每个模块能不能直接接进流程。

组员替换实现后运行：uv run pytest tests/test_contracts.py
默认检查示例数据分支；加 REAL_MODULES=模块名 可检查真实实现（会产生费用）。
"""

import importlib
import inspect

import pytest

from app.common.config import settings
from app.contracts import MODULE_WRITES, ContractError, validate_update

# (模块文件夹, 对外函数, 用哪份示例工单)
ENTRY_POINTS = [
    ("intake", "intake", "new_task"),
    ("intake", "compose", "after_generation"),
    ("intake", "reveal", "after_generation"),
    ("styling", "style", "after_intake"),
    ("framing", "frame", "after_intake"),
    ("generation", "generate", "after_generation"),
    ("review", "check", "after_generation"),
    ("review", "retouch", "after_generation"),
    ("assets", "make_previews", "after_generation"),
    ("assets", "package", "after_generation"),
]


def test_every_entry_point_is_listed():
    assert {name for _, name, _ in ENTRY_POINTS} == set(MODULE_WRITES)


@pytest.mark.parametrize("module, name, fixture", ENTRY_POINTS)
def test_entry_point_follows_contract(module, name, fixture, load_state):
    package = importlib.import_module(f"app.modules.{module}")
    assert hasattr(package, name), f"app/modules/{module}/__init__.py 没有导出 {name}"
    function = getattr(package, name)
    assert not inspect.iscoroutinefunction(function), f"{name} 必须是普通函数（def），不能是 async def"
    assert len(inspect.signature(function).parameters) == 1, f"{name} 只能有一个参数 state"
    validate_update(name, function(load_state(fixture)))


def test_assets_helpers_follow_contract(png_bytes, asset_catalog):
    from app.modules.assets import load_image, save_image, search_assets

    url = save_image(png_bytes, "candidate")
    assert isinstance(url, str) and url.startswith(settings.public_base_url)
    assert load_image(url) == png_bytes
    assert list(inspect.signature(search_assets).parameters) == ["kind", "tags"]
    for item in search_assets("pose"):
        assert set(item) == {"asset_id", "kind", "name", "tags", "url"}


def test_generation_client_signature():
    from app.modules.generation.client import generate_image

    assert list(inspect.signature(generate_image).parameters) == ["photo_urls", "prompt", "seed", "references"]
    assert not inspect.iscoroutinefunction(generate_image)


@pytest.mark.parametrize(
    "name, update",
    [
        ("style", {"look": {"text": "造型"}}),  # 少了 style
        ("style", {"look": {"text": "造型", "style": "x", "color": "red"}}),  # 多了字段
        ("frame", {"shot": {"text": "镜头", "pose": "keep_original"}, "prompt": "越权"}),  # 写了别人的字段
        ("generate", {"prompt": "提示词归小囍写", "candidates": []}),
        ("frame", {"shot": {"text": "镜头", "pose": "keep_original", "references": [{"url": "u", "role": "shoes"}]}}),
        ("check", {"scores": [{"image_id": "img_1", "face_sim": [0.9], "body_ok": True, "hands_ok": True, "issues": [], "total": 0.9}]}),
        ("retouch", {"retouch_plan": {"target": "everything", "patch": "x"}}),
        ("intake", {"brief": {"style": "korean_studio", "mood": "开心"}}),  # 需求单里没有的字段
        ("style", {"questions": []}),  # 问问题时也必须先给一版 look
        ("compose", {"prompt": "只写了提示词"}),  # 少了 references
        ("generate", None),
    ],
)
def test_contract_rejects_bad_output(name, update):
    with pytest.raises(ContractError):
        validate_update(name, update)


# ---- 小囍更新照片字段（补传照片后） ----

_G = ["http://x/g1.png"]
_B = ["http://x/b1.png", "http://x/b2.png"]


@pytest.mark.parametrize(
    "update, state",
    [
        ({"brief": {}, "groom_photo_urls": _G, "bride_photo_urls": _B, "photo_urls": _G + _B}, None),
        ({"brief": {}, "bride_photo_urls": ["http://x/b9.png"], "photo_urls": _G + ["http://x/b9.png"]}, {"groom_photo_urls": _G, "bride_photo_urls": _B, "photo_urls": _G + _B}),
        ({"brief": {}, "photo_urls": ["http://x/new.png"]}, {"photo_urls": ["http://x/old.png"]}),  # 旧的合照任务
    ],
)
def test_intake_may_update_photos(update, state):
    validate_update("intake", update, state)


@pytest.mark.parametrize(
    "update, state",
    [
        ({"brief": {}, "groom_photo_urls": _G, "bride_photo_urls": _B, "photo_urls": _B + _G}, None),  # 顺序不对
        ({"brief": {}, "groom_photo_urls": _G, "bride_photo_urls": _B}, None),  # 没给 photo_urls
        ({"brief": {}, "groom_photo_urls": [], "bride_photo_urls": _B, "photo_urls": _B}, None),  # 一组为空
        ({"brief": {}, "groom_photo_urls": [f"http://x/g{i}.png" for i in range(11)], "bride_photo_urls": _B, "photo_urls": [f"http://x/g{i}.png" for i in range(11)] + _B}, None),  # 超过 10 张
        ({"brief": {}, "groom_photo_urls": [""], "bride_photo_urls": _B, "photo_urls": [""] + _B}, None),  # 空地址
        ({"brief": {}, "groom_photo_urls": "http://x/g1.png"}, None),  # 不是列表
        ({"brief": {}, "bride_photo_urls": ["http://x/b9.png"]}, {"groom_photo_urls": _G, "bride_photo_urls": _B, "photo_urls": _G + _B}),  # 换了新娘照片但没更新 photo_urls
        ({"brief": {}, "photo_urls": []}, None),
    ],
)
def test_intake_photo_fields_are_checked(update, state):
    with pytest.raises(ContractError):
        validate_update("intake", update, state)


def test_brief_style_fields_default_to_undecided():
    from app.state import DEPRECATED_BRIEF_FIELDS, UNDECIDED, Brief

    brief = Brief()
    assert all(getattr(brief, key) == UNDECIDED for key in DEPRECATED_BRIEF_FIELDS)
    validate_update("intake", {"brief": Brief(heights_cm=[175, 162]).model_dump()})


def test_shots_and_shot_prompts_contract():
    from app.contracts import ContractError, validate_update
    shot = {"text": "t", "pose": "keep_original", "references": []}
    shots = [{"slot": i, "pose": "keep_original", "framing": "全身", "scene": "影棚", "text": f"镜头{i}"} for i in range(9)]
    validate_update("frame", {"shot": shot, "shots": shots})
    validate_update("compose", {"prompt": "p", "references": [], "shot_prompts": [{"slot": 0, "prompt": "p0"}]})
    validate_update("compose", {"prompt": "p", "references": []})  # 分镜是可选的
    with pytest.raises(ContractError):
        validate_update("frame", {"shot": shot, "shots": shots + [shots[0]]})
    with pytest.raises(ContractError):
        validate_update("compose", {"prompt": "p", "references": [], "shot_prompts": [{"slot": 0}]})
    with pytest.raises(ContractError):
        validate_update("generate", {"candidates": [], "generation": {"engine": "x", "workflow": "x", "seconds": 0, "total_images": 0}, "shots": shots})
