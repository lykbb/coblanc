"""大模型入口（框架维护）。模块里不要自己写模型名和密钥，统一用 get_llm。

    llm = get_llm("agent")                         # 小囍、妆造师、摄影师、修图师这类需要判断的地方
    llm = get_llm("cheap")                         # 简单的改写、分类
    llm = get_llm("vision")                        # 需要看图的地方（图片只能放在 user 消息里，不能放 system）
    brief = get_llm("agent").with_structured_output(Brief).invoke(messages)

选哪家：.env 里填了 CHAT_API_KEY 就用 CHAT_BASE_URL 指向的服务（默认 DeepSeek；模型默认 CHAT_MODEL，可用
CHAT_MODEL_AGENT / CHAT_MODEL_CHEAP / CHAT_MODEL_VISION 分别覆盖；旧名 DEEPSEEK_* 仍然有效）；没填就用原来的 LLM_*（火山方舟）。
FAKE / REAL_MODULES 照旧决定每个模块是否真的调用模型。生图不走这里，仍用 Seedream。
"""

from langchain_openai import ChatOpenAI

from app.common.config import settings

KINDS = ("agent", "cheap", "vision")


def llm_config(kind: str = "agent") -> dict:
    """返回 {provider, base_url, model, api_key}；不打印、不记录 api_key。"""
    if kind not in KINDS:
        raise ValueError(f"kind 只能是 {list(KINDS)}，收到 {kind!r}")
    if settings.chat_api_key:
        model = getattr(settings, f"chat_model_{kind}") or settings.chat_model
        return {"provider": "chat", "base_url": settings.chat_base_url,
                "model": model, "api_key": settings.chat_api_key}
    return {"provider": "ark", "base_url": settings.llm_base_url,
            "model": getattr(settings, f"llm_model_{kind}"), "api_key": settings.llm_api_key}


def llm_ready(kind: str = "agent") -> bool:
    config = llm_config(kind)
    return bool(config["api_key"] and config["model"])


def model_name(kind: str = "agent") -> str:
    return llm_config(kind)["model"]


def get_llm(kind: str = "agent") -> ChatOpenAI:
    config = llm_config(kind)
    if not config["api_key"] or not config["model"]:
        raise RuntimeError(f"缺少 CHAT_API_KEY（或 LLM_API_KEY + LLM_MODEL_{kind.upper()}），请在 .env 里填写")
    return ChatOpenAI(
        model=config["model"],
        base_url=config["base_url"],
        api_key=config["api_key"],
        timeout=settings.llm_timeout_seconds,
        max_retries=1,
    )
