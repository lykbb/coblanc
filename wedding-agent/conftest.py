"""测试公共设置：一律用 fake 模式和临时文件夹，不花钱，也不碰 storage/。"""

import json
import os
import shutil
import struct
import tempfile
import zlib
from pathlib import Path

import pytest

_TMP = tempfile.mkdtemp(prefix="wedding-test-")
os.environ.update({"FAKE": "1", "FAKE_FAIL_FIRST_CHECK": "0", "STORAGE_DIR": _TMP, "ACCESS_INVITE_REQUIRED": "0", "REFERENCE_DIR": _TMP + "-refs"})
# 默认全部用示例数据；想让某个模块走真实实现，运行时加 REAL_MODULES=模块名（会产生费用）
os.environ.setdefault("REAL_MODULES", "")

FIXTURES = Path(__file__).parent / "tests" / "fixtures"


def make_png(width: int = 8, height: int = 8) -> bytes:
    """生成一张纯色小图，当作测试照片。"""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + b"\xf0\xc8\xc8" * width for _ in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


@pytest.fixture
def png_bytes() -> bytes:
    return make_png()


@pytest.fixture
def load_state():
    """读 tests/fixtures/<name>.json 示例工单，并把里面的图片换成真实存在的测试图。"""
    from app.modules.assets import save_image

    def load(name: str) -> dict:
        state = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
        if "photo_urls" in state:
            state["photo_urls"] = [save_image(make_png(), "upload")]
        for candidate in state.get("candidates", []):
            candidate["url"] = save_image(make_png(), "candidate")
        return state

    return load


@pytest.fixture
def asset_catalog(tmp_path, monkeypatch):
    """临时物料库：一张姿势骨架、一张韩式婚纱参考，另有一条文件缺失的登记。"""
    from app.modules.assets import node

    (tmp_path / "poses").mkdir()
    (tmp_path / "outfits").mkdir()
    (tmp_path / "poses" / "medium_a.png").write_bytes(make_png())
    (tmp_path / "outfits" / "korean_satin.png").write_bytes(make_png())
    entries = [
        {"asset_id": "pose_medium_a", "kind": "pose", "name": "并肩牵手", "tags": ["medium"], "file": "poses/medium_a.png"},
        {"asset_id": "outfit_korean_satin", "kind": "outfit", "name": "缎面婚纱", "tags": ["korean_studio"], "file": "outfits/korean_satin.png"},
        {"asset_id": "pose_large_a", "kind": "pose", "name": "文件还没放", "tags": ["large"], "file": "poses/large_a.png"},
    ]
    (tmp_path / "catalog.json").write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(node, "TEMPLATES_DIR", tmp_path)
    monkeypatch.setattr(node, "CATALOG", tmp_path / "catalog.json")
    return entries


@pytest.fixture(scope="session", autouse=True)
def _cleanup_tmp():
    yield
    shutil.rmtree(_TMP, ignore_errors=True)


@pytest.fixture(autouse=True)
def _no_real_chat_model(monkeypatch):
    """测试不连真实对话模型：即使本机 .env 里有 CHAT_API_KEY / DEEPSEEK_API_KEY 也当作没填。"""
    from app.common.config import settings
    monkeypatch.setattr(settings, "chat_api_key", "")


def portal_login(site: str, holder: str):
    """在内部站点（admin / gallery）登录，改动类请求自动带 CSRF 头。"""
    from fastapi.testclient import TestClient

    from app import access
    from app.api import app

    client = TestClient(app, headers={"X-Portal-CSRF": "1"})
    [(_, code)] = access.create([holder])
    client.post(f"/api/{site}/redeem", json={"code": code})
    return client


@pytest.fixture
def portal_env(tmp_path, monkeypatch):
    from app import access
    from app.common.config import settings

    monkeypatch.setattr(settings, "reference_dir", tmp_path / "refs")
    monkeypatch.setattr(settings, "state_dir", tmp_path / "state")
    monkeypatch.setattr(settings, "access_required", True)
    monkeypatch.setattr(settings, "admin_holders", ["lyk"])
    monkeypatch.setattr(settings, "gallery_members", ["刘静", "何选"])
    access._fails.clear()


@pytest.fixture
def admin_client(portal_env):
    return portal_login("admin", "lyk")


@pytest.fixture
def gallery_client(portal_env):
    return portal_login("gallery", "刘静")
