"""大模型入口（框架维护）。模块里不要自己写模型名和密钥，统一用 get_llm。

    llm = get_llm("agent")                         # 小囍、修图师这类需要判断的地方
    llm = get_llm("cheap")                         # 简单的改写、分类
    llm = get_llm("vision")                        # 需要看图的地方
    brief = get_llm("agent").with_structured_output(Brief).invoke(messages)
"""

from langchain_openai import ChatOpenAI

from app.common.config import settings


def get_llm(kind: str = "agent") -> ChatOpenAI:
    models = {
        "agent": settings.llm_model_agent,
        "cheap": settings.llm_model_cheap,
        "vision": settings.llm_model_vision,
    }
    if kind not in models:
        raise ValueError(f"kind 只能是 {list(models)}，收到 {kind!r}")
    if not settings.llm_api_key or not models[kind]:
        raise RuntimeError(f"缺少 LLM_API_KEY 或 LLM_MODEL_{kind.upper()}，请在 .env 里填写")
    return ChatOpenAI(
        model=models[kind],
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        timeout=settings.llm_timeout_seconds,
        max_retries=1,
    )
