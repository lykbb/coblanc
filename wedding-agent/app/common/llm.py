"""大模型入口（框架维护）。模块里不要自己写模型名和密钥，统一用 get_llm。

    llm = get_llm("agent")                         # 小囍、妆造师、摄影师、修图师这类需要判断的地方
    llm = get_llm("cheap")                         # 简单的改写、分类
    llm = get_llm("vision")                        # 需要看图的地方（图片只能放在 user 消息里，不能放 system）
    brief = get_llm("agent").with_structured_output(Brief).invoke(messages)

选哪家：.env 里填了 CHAT_API_KEY 就用 CHAT_BASE_URL 指向的服务（默认 DeepSeek；模型默认 CHAT_MODEL，可用
CHAT_MODEL_AGENT / CHAT_MODEL_CHEAP / CHAT_MODEL_VISION 分别覆盖；旧名 DEEPSEEK_* 仍然有效）；没填就用原来的 LLM_*（火山方舟）。
FAKE / REAL_MODULES 照旧决定每个模块是否真的调用模型。生图不走这里，仍用 Seedream。
"""

from langchain_core.exceptions import OutputParserException
from langchain_openai import ChatOpenAI
from pydantic import ValidationError

from app.common.config import settings

KINDS = ("agent", "cheap", "vision")


# 统一重试：网络/超时/429/5xx 由 SDK 自带指数退避重试（HTTP_RETRIES 次）；
# 结构化输出格式不对（模型偶尔调错工具、字段不合法）在这里再整体重试，带退避，所有模块共用。
HTTP_RETRIES = 2
STRUCTURED_ATTEMPTS = 2


class _Model(ChatOpenAI):
    def with_structured_output(self, schema=None, *, method=None, **kwargs):
        runnable = super().with_structured_output(schema, method=method or self._default_method, **kwargs)
        return runnable.with_retry(retry_if_exception_type=(OutputParserException, ValidationError),
                                   stop_after_attempt=STRUCTURED_ATTEMPTS, wait_exponential_jitter=True)

    _default_method = None


class ArkModel(_Model):
    """火山方舟：沿用 langchain 默认的结构化输出方式。"""


class ChatModel(_Model):
    """CHAT_* 服务用：结构化输出默认走 function_calling。

    DeepSeek 等服务不支持 response_format=json_schema（langchain 的默认），思考模式下也不支持强制 tool_choice，
    所以这里默认 function_calling，并按 CHAT_THINKING 关掉思考。
    """

    _default_method = "function_calling"


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
    if config["provider"] == "chat":
        extra = {} if settings.chat_thinking else {"thinking": {"type": "disabled"}}
        return ChatModel(model=config["model"], base_url=config["base_url"], api_key=config["api_key"],
                         timeout=settings.llm_timeout_seconds, max_retries=HTTP_RETRIES, extra_body=extra or None)
    return ArkModel(
        model=config["model"],
        base_url=config["base_url"],
        api_key=config["api_key"],
        timeout=settings.llm_timeout_seconds,
        max_retries=HTTP_RETRIES,
    )
