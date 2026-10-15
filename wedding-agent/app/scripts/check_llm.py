"""连通性检查：uv run python -m app.scripts.check_llm [agent|cheap|vision ...]

agent、cheap 各发一句很短的文字请求，vision 在 user 消息里带一张小红图，只报告 ok / 错误类型，不打印密钥。
"""

import sys

import base64
import struct
import zlib

from app.common.llm import KINDS, get_llm, llm_config


def _red_png(size: int = 8) -> str:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    rows = b"".join(b"\x00" + b"\xff\x00\x00" * size for _ in range(size))
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))
    return "data:image/png;base64," + base64.b64encode(png).decode()


RED_PNG = _red_png()


def check(kind: str) -> bool:
    config = llm_config(kind)
    label = f"[{kind}] {config['provider']} {config['base_url']} model={config['model'] or '未配置'}"
    if not config["api_key"]:
        print(f"{label}: 未配置密钥（CHAT_API_KEY 或 LLM_API_KEY）")
        return False
    try:
        if kind == "vision":  # 看图：在 user 消息里带一张 8x8 红色小图
            content = [{"type": "text", "text": "这张图主要是什么颜色？只回答颜色"},
                       {"type": "image_url", "image_url": {"url": RED_PNG}}]
            reply = get_llm(kind).invoke([{"role": "user", "content": content}])
        else:
            reply = get_llm(kind).invoke([("user", "只回复两个字：收到")])
        text = str(getattr(reply, "content", "")).strip().replace(config["api_key"], "***")
        print(f"{label}: ok，回复「{text[:20]}」")
        return True
    except Exception as error:
        message = str(error).replace(config["api_key"], "***")[:200]
        print(f"{label}: 失败 {type(error).__name__}: {message}")
        return False


def main(argv: list[str]) -> int:
    kinds = argv or list(KINDS)
    return 0 if all([check(kind) for kind in kinds]) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
