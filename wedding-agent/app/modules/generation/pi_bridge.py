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
from app.common.log import get_logger

log = get_logger("pi_bridge")


def _describe(error: Exception) -> str:
    """只记录异常类型和不含数据的摘要：校验错误只记字段位置和错误类型，其他错误截断并去掉疑似密钥。"""
    errors = getattr(error, "errors", None)
    if callable(errors):
        try:
            return type(error).__name__ + " " + "; ".join(
                f"{'.'.join(str(part) for part in item.get('loc', ()))}:{item.get('type')}" for item in errors()[:5])
        except Exception:
            pass
    import re
    text = re.sub(r"(sk-|Bearer\s+)[A-Za-z0-9._-]+", r"\1***", str(error))
    return f"{type(error).__name__}: {text[:200]}"


def run_pi(payload: dict, decision: Callable[[dict], dict] | None,
           tool: Callable[[str, dict], object], timeout: float) -> dict:
    from app.modules.framing.pi_bridge import find_node
    node = find_node()
    if not node:
        raise ModuleError("GENERATION_FAILED", "生图服务运行环境未就绪（Node 版本过低），请联系管理员")
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
        except Exception as error:
            log.warning("Pi 输出读取失败：%s", _describe(error))
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
        except Exception as error:
            # 不把原始异常/请求数据交给 Pi；日志里只记类型和脱敏摘要，方便排查。
            log.warning("Pi %s 调用失败：%s", message.get("type"), _describe(error))
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
                log.warning("Pi 进程%s（退出码 %s），常见原因：步数用完或模型决策连续失败",
                            "报错" if message["type"] == "error" else "提前结束", process.poll())
                raise ModuleError("GENERATION_FAILED", "拍摄服务暂时不可用，请稍后重试")
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        workers.shutdown(wait=False, cancel_futures=True)
        process.stdin.close()
        process.stdout.close()
