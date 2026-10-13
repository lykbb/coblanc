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
os.environ.update({"FAKE": "1", "FAKE_FAIL_FIRST_CHECK": "0", "STORAGE_DIR": _TMP})
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


@pytest.fixture(scope="session", autouse=True)
def _cleanup_tmp():
    yield
    shutil.rmtree(_TMP, ignore_errors=True)
