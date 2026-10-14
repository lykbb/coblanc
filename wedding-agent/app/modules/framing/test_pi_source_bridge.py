"""验证下载并改造的 Pi 源码通过原有 Python 接口运行，而不是回退到 npm SDK。"""

import json
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from app.common.errors import ModuleError
from app.modules.framing import pi_bridge


pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="源码桥测试需要 Node.js")


@pytest.mark.parametrize("input_text", ["", "not-json\n", json.dumps({
    "type": "start", "system": "test", "max_steps": 0,
}) + "\n"])
def test_source_cli_rejects_bad_input_and_closed_connection(input_text):
    result = subprocess.run(
        [shutil.which("node"), str(Path(pi_bridge.__file__).with_name("pi_runtime.mjs"))],
        input=input_text, text=True, capture_output=True, timeout=5,
    )
    assert result.returncode == 1
    assert json.loads(result.stdout) == {"type": "error", "message": "Pi wedding agent failed"}


def test_source_core_tool_cap_applies_through_python_bridge():
    decisions = []
    tools = []

    def decide(message):
        decisions.append(message["remaining_steps"])
        return {"action": "search_assets", "kind": "pose", "tags": []}

    def search(name, arguments):
        tools.append(name)
        return []

    with pytest.raises(ModuleError):
        pi_bridge.run_pi({"system": "test", "input": {}, "max_steps": 1}, decide, search, timeout=5)
    assert decisions == [1, 0]
    assert tools == ["search_assets"]


def test_bridge_timeout_stops_source_process(monkeypatch):
    processes = []
    entered = threading.Event()
    release = threading.Event()
    original_popen = subprocess.Popen

    def popen(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        processes.append(process)
        return process

    def decide(message):
        entered.set()
        release.wait(3)
        return {"action": "final", "shot": {"text": "test", "pose": "keep_original", "references": []}}

    monkeypatch.setattr(pi_bridge.subprocess, "Popen", popen)
    try:
        with pytest.raises(ModuleError, match="处理超时"):
            pi_bridge.run_pi({"system": "test", "input": {}, "max_steps": 1}, decide,
                             lambda *args: [], timeout=1)
        assert entered.is_set()
        assert len(processes) == 1 and processes[0].poll() is not None
    finally:
        release.set()
