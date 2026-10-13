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


def test_assets_helpers_follow_contract(png_bytes):
    from app.modules.assets import get_template, load_image, save_image

    url = save_image(png_bytes, "candidate")
    assert isinstance(url, str) and url.startswith(settings.public_base_url)
    assert load_image(url) == png_bytes
    assert list(inspect.signature(get_template).parameters) == ["name"]


def test_generation_client_signature():
    from app.modules.generation.client import generate_image

    assert list(inspect.signature(generate_image).parameters) == ["photo_urls", "prompt", "seed", "pose_ref_url"]
    assert not inspect.iscoroutinefunction(generate_image)


@pytest.mark.parametrize(
    "name, update",
    [
        ("style", {"look": {"text": "造型"}}),  # 少了 style
        ("style", {"look": {"text": "造型", "style": "x", "color": "red"}}),  # 多了字段
        ("frame", {"shot": {"text": "镜头", "pose": "keep_original"}, "prompt": "越权"}),  # 写了别人的字段
        ("check", {"scores": [{"image_id": "img_1", "face_sim": [0.9], "body_ok": True, "hands_ok": True, "issues": [], "total": 0.9}]}),
        ("retouch", {"retouch_plan": {"target": "everything", "patch": "x"}}),
        ("intake", {"brief": {"style": "korean_studio", "mood": "开心"}}),  # 需求单里没有的字段
        ("generate", None),
    ],
)
def test_contract_rejects_bad_output(name, update):
    with pytest.raises(ContractError):
        validate_update(name, update)
