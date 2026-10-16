"""共用的 LLM 结构化重试、styling 最后一步、错误原因日志。"""

import logging

from langchain_core.exceptions import OutputParserException
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel

from app.common import llm as llm_mod
from app.common.errors import ModuleError, describe_cause


class Out(BaseModel):
    x: int


def test_structured_output_retries_parse_failure(monkeypatch):
    calls = []

    def flaky(self, input, config=None, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise OutputParserException("Unknown tool type: 'search_assets'")
        return Out(x=1)

    model = llm_mod.ChatModel(model="m", api_key="sk-test", base_url="http://x")
    runnable = model.with_structured_output(Out)
    monkeypatch.setattr(type(runnable.bound), "invoke", flaky)
    assert runnable.invoke("hi") == Out(x=1)
    assert len(calls) == 2


def test_describe_cause_masks_secrets():
    try:
        try:
            raise RuntimeError("401 bad key sk-abcdef1234567890 Bearer abcdefghijk")
        except RuntimeError as error:
            raise ModuleError("GENERATION_FAILED", "x") from error
    except ModuleError as error:
        text = describe_cause(error)
    assert "RuntimeError" in text and "abcdef1234567890" not in text and "abcdefghijk" not in text


def test_styling_final_step_has_no_tool_history(monkeypatch):
    from app.modules.styling import node

    seen = {}

    class Fake:
        def bind_tools(self, tools):
            return self

        def invoke(self, messages):
            if len(messages) == 1:
                return AIMessage(content="", tool_calls=[{"id": "1", "name": "search_assets", "args": {"kind": "style"}}])
            return AIMessage(content="ok")

        def with_structured_output(self, schema):
            class R:
                def invoke(_, messages):
                    seen["messages"] = messages
                    return "LOOK"
            return R()

    monkeypatch.setattr(llm_mod, "get_llm", lambda kind="agent": Fake())
    monkeypatch.setattr(node, "_load_assets", lambda kind, tags: [{"id": "a1"}])
    assert node._invoke_agent("PROMPT") == "LOOK"
    msgs = seen["messages"]
    assert len(msgs) == 1 and isinstance(msgs[0], HumanMessage) and "a1" in msgs[0].content
