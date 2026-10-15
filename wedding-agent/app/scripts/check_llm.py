"""连通性检查：uv run python -m app.scripts.check_llm [agent|cheap|vision ...]

每种模型发一句很短的文字请求，只报告 ok / 错误类型，不打印密钥。
"""

import sys

from app.common.llm import KINDS, get_llm, llm_config


def check(kind: str) -> bool:
    config = llm_config(kind)
    label = f"[{kind}] {config['provider']} {config['base_url']} model={config['model'] or '未配置'}"
    if not config["api_key"]:
        print(f"{label}: 未配置密钥（DEEPSEEK_API_KEY 或 LLM_API_KEY）")
        return False
    try:
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
