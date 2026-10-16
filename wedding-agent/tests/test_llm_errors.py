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


def test_http_429_is_retried_by_sdk_then_succeeds():
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    hits = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            hits.append(1)
            if len(hits) == 1:
                self.send_response(429)
                self.send_header("Retry-After", "0")
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":{"message":"rate limited"}}')
                return
            body = {"id": "x", "object": "chat.completion", "created": 0, "model": "m", "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "ok"}}]}
            data = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        model = llm_mod.ChatModel(model="m", api_key="sk-test", base_url=f"http://127.0.0.1:{server.server_port}/v1",
                                  timeout=10, max_retries=llm_mod.HTTP_RETRIES)
        assert model.invoke("hi").content == "ok"
        assert len(hits) == 2
    finally:
        server.shutdown()


def test_interrupted_tasks_marked_on_startup(tmp_path):
    from app.common.progress import TaskStore

    first = TaskStore(tmp_path, 7)
    first.create("t_aaaa")
    first.update("t_aaaa", status="running", step="framing")
    fresh = TaskStore(tmp_path, 7)
    assert fresh.mark_interrupted() == ["t_aaaa"]
    import json
    saved = json.loads((tmp_path / "t_aaaa.json").read_text(encoding="utf-8"))
    assert saved["status"] == "failed" and saved["error"]["retryable"] is True
