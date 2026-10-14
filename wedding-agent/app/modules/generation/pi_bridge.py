"""本模块私有的 Pi 进程桥；保持同步节点接口，不把密钥或用户照片传给 Node。"""

import json
import os
import queue
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from app.common.errors import ModuleError


def run_pi(payload: dict, decision: Callable[[dict], dict] | None,
           tool: Callable[[str, dict], object], timeout: float) -> dict:
    node = shutil.which("node")
    if not node:
        raise ModuleError("GENERATION_FAILED", "拍摄服务暂时未就绪，请稍后重试")
    script = Path(__file__).with_name("pi_runtime.mjs")
    environment = {key: value for key, value in os.environ.items()
                   if not any(word in key.upper() for word in ("KEY", "TOKEN", "SECRET", "PASSWORD"))}
    process = subprocess.Popen(
        [node, str(script)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, encoding="utf-8", env=environment,
    )
    received: queue.Queue = queue.Queue()
    lock = threading.Lock()
    workers = ThreadPoolExecutor(max_workers=max(1, payload.get("parallelism", 1)))

    def read_lines() -> None:
        try:
            for line in process.stdout:
                if len(line) > 1_048_576:
                    raise ValueError("Pi 消息过长")
                received.put(json.loads(line))
        except Exception:
            received.put({"type": "error"})
        finally:
            received.put({"type": "closed"})

    def write(value: dict) -> None:
        with lock:
            process.stdin.write(json.dumps(value, ensure_ascii=False) + "\n")
            process.stdin.flush()

    def handle(message: dict) -> None:
        try:
            if message["type"] == "decision":
                if decision is None:
                    raise ValueError("此模块不开放模型决策接口")
                result = decision(message)
            else:
                result = tool(message["name"], message["arguments"])
            answer = {"id": message["id"], "value": result}
        except Exception:
            # 不把原始异常/请求数据交给 Pi 或日志，服务密钥和照片可能包含在异常中。
            answer = {"id": message["id"], "error": "业务工具执行失败"}
        try:
            write(answer)
        except (BrokenPipeError, ValueError, OSError):
            pass

    threading.Thread(target=read_lines, daemon=True).start()
    deadline = time.monotonic() + timeout
    try:
        write({"type": "start", **payload})
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ModuleError("GENERATION_FAILED", "处理超时，请稍后重试")
            try:
                message = received.get(timeout=remaining)
            except queue.Empty:
                raise ModuleError("GENERATION_FAILED", "处理超时，请稍后重试") from None
            if message["type"] in {"decision", "tool"}:
                workers.submit(handle, message)
            elif message["type"] == "result":
                return message["value"]
            elif message["type"] in {"error", "closed"}:
                raise ModuleError("GENERATION_FAILED", "拍摄服务暂时不可用，请稍后重试")
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        workers.shutdown(wait=False, cancel_futures=True)
        process.stdin.close()
        process.stdout.close()
