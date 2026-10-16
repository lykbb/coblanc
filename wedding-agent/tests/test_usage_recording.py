"""真实调用链路（不花钱）：本地假 DeepSeek 接口返回 DeepSeek 形状的 usage，走 get_llm + 结构化输出，
确认下一次真实任务会记下 token（含缓存命中）、步骤，并写过程记录。"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from pydantic import BaseModel

from app.common import llm, trace, usage
from app.common.config import settings
from app.common.log import current_step, current_task


class Answer(BaseModel):
    text: str


class _Fake(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        body = {"id": "x", "object": "chat.completion", "created": 1, "model": "deepseek-flash",
                "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {"role": "assistant", "content": "",
                             "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "Answer", "arguments": "{\"text\": \"好\"}"}}]}}],
                "usage": {"prompt_tokens": 1200, "completion_tokens": 80, "total_tokens": 1280,
                          "prompt_cache_hit_tokens": 1024, "prompt_cache_miss_tokens": 176,
                          "prompt_tokens_details": {"cached_tokens": 1024}}}
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def test_real_call_path_records_tokens(monkeypatch):
    server = HTTPServer(("127.0.0.1", 0), _Fake)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(settings, "chat_api_key", "test-key")
    monkeypatch.setattr(settings, "chat_base_url", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setattr(settings, "chat_model_agent", "deepseek-flash")
    task, step = current_task.set("t_rec"), current_step.set("frame")
    try:
        result = llm.get_llm("agent").with_structured_output(Answer).invoke("你好")
    finally:
        current_task.reset(task)
        current_step.reset(step)
        server.shutdown()
    assert result.text == "好"
    entry = usage.read(task_id="t_rec")[-1]
    assert (entry["input"], entry["cached"], entry["output"], entry["step"], entry["provider"]) == (1200, 1024, 80, "frame", "chat")
    assert usage.cost(entry) > 0
    item = trace.read("t_rec")[-1]
    assert item["kind"] == "llm" and item["step"] == "frame" and item["output"][0]["tool_calls"][0]["args"] == {"text": "好"}
