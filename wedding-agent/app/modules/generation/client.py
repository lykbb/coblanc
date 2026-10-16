"""唯一生图服务出口：Seedream 主力，配置完整时使用 RunningHub 备用。

Seedream 5.0 Pro 不接受 seed，传入的 seed 只供备用工作流使用。
原型契约要求 seed:int，因此 Seedream 候选的 seed=-1 代表服务未提供种子。
上下文仅存在当前线程的调用栈中，多任务不共享预算、照片或生成结果。
"""

import base64
import json
import socket
import threading
import time
import urllib.error
import urllib.request
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path

from app.common import usage
from app.common.config import settings
from app.common.errors import ModuleError
from app.common.log import get_logger
from app.modules.assets import load_image

log = get_logger("generation")


class ImageCallFailure(ModuleError):
    def __init__(self, message: str, retryable: bool = False):
        super().__init__("GENERATION_FAILED", message)
        self.retryable = retryable


class _ProviderFailure(Exception):
    def __init__(self, code: str, retryable: bool = False, unknown: bool = False):
        self.code, self.retryable, self.unknown = code, retryable, unknown


@dataclass
class _Budget:
    limit: int
    used: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def reserve(self) -> None:
        with self.lock:
            if self.used >= self.limit:
                raise ImageCallFailure("这次的生成次数用完了，请重新开始")
            self.used += 1


@dataclass
class _Scope:
    budget: _Budget
    deadline: float
    parameters: dict = field(default_factory=dict)
    engine: str = ""
    effective_seed: int = -1
    records: list[dict] = field(default_factory=list)
    response_metadata: dict = field(default_factory=dict)
    request_id: str | None = None


_ACTIVE_SCOPE: ContextVar[_Scope | None] = ContextVar("generation_call_scope", default=None)


@contextmanager
def _call_scope(scope: _Scope):
    token = _ACTIVE_SCOPE.set(scope)
    try:
        yield scope
    finally:
        _ACTIVE_SCOPE.reset(token)


def _remaining() -> float:
    scope = _ACTIVE_SCOPE.get()
    remaining = (scope.deadline - time.monotonic()) if scope else settings.image_timeout_seconds
    if remaining <= 0:
        raise ImageCallFailure("生图等待超时，请稍后重新开始")
    return max(0.01, min(settings.image_timeout_seconds, remaining))


def _read(request: urllib.request.Request) -> bytes:
    try:
        with urllib.request.urlopen(request, timeout=_remaining()) as response:
            scope = _ACTIVE_SCOPE.get()
            if scope:
                scope.request_id = response.headers.get("X-Request-Id")
            data = bytearray()
            while True:
                _remaining()
                chunk = response.read(65536)
                if not chunk:
                    return bytes(data)
                data.extend(chunk)
                if len(data) > 64 * 1024 * 1024:
                    raise _ProviderFailure("response_too_large")
    except urllib.error.HTTPError as error:
        raise _ProviderFailure(f"http_{error.code}", error.code == 429 or error.code >= 500) from None
    except (TimeoutError, socket.timeout):
        # 服务可能已经生成成功；不自动重新提交或切备用，以免重复计费。
        raise _ProviderFailure("outcome_unknown", unknown=True) from None
    except urllib.error.URLError as error:
        if isinstance(error.reason, (TimeoutError, socket.timeout)):
            raise _ProviderFailure("outcome_unknown", unknown=True) from None
        raise _ProviderFailure("connection_failed", retryable=True) from None


def _post_json(url: str, payload: dict, api_key: str) -> dict:
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST", headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {api_key}",
    })
    try:
        return json.loads(_read(request))
    except (ValueError, UnicodeError):
        raise _ProviderFailure("invalid_response", unknown=True) from None


def _image_bytes(url: str) -> bytes:
    try:
        data = load_image(url)
    except Exception:
        raise ImageCallFailure("参考照片无法读取，请重新上传或检查资产库素材")
    if len(data) > 30 * 1024 * 1024 or not (
        data.startswith(b"\x89PNG\r\n\x1a\n") or data.startswith(b"\xff\xd8\xff")
    ):
        raise ImageCallFailure("参考照片需要为不超过 30 MB 的 JPG 或 PNG")
    return data


def _seedream_image(photo_urls: list[str], prompt: str, seed: int, references: list[dict]) -> bytes:
    images = []
    for url in photo_urls + [item["url"] for item in references]:
        data = _image_bytes(url)
        mime = "png" if data.startswith(b"\x89PNG") else "jpeg"
        images.append(f"data:image/{mime};base64," + base64.b64encode(data).decode())
    scope = _ACTIVE_SCOPE.get()
    payload = {
        "model": settings.seedream_model, "prompt": prompt, "image": images,
        "response_format": "b64_json",
        # 方舟默认会在图角加"AI 生成"标；预览水印由前端叠加，这里关掉服务端水印。
        "watermark": False,
        "size": "2K",  # 默认 2K；scope.parameters 里有 size（如修图方案指定）时以它为准
    }
    if scope:
        payload.update(scope.parameters)
    # 不传 seed、negative_prompt、n、sequential_image_generation 等 Pro 不支持的字段。
    response = _post_json(settings.llm_base_url.rstrip("/") + "/images/generations",
                          payload, settings.llm_api_key)
    items = response.get("data")
    if response.get("error") or not isinstance(items, list) or len(items) != 1:
        raise _ProviderFailure("generation_rejected")
    if items[0].get("error"):
        raise _ProviderFailure("generation_rejected")
    try:
        image = base64.b64decode(items[0]["b64_json"], validate=True)
    except (KeyError, ValueError, TypeError):
        raise _ProviderFailure("invalid_image", unknown=True) from None
    if not image.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff")):
        raise _ProviderFailure("invalid_image", unknown=True)
    used = response.get("usage") or {}
    usage.record("seedream", response.get("model", settings.seedream_model), "image", used.get("input_tokens", 0),
                 used.get("output_tokens", 0), used.get("total_tokens"), images=used.get("generated_images", len(items)))
    if scope:
        scope.engine = "seedream"
        scope.effective_seed = -1
        scope.response_metadata = {
            "model": response.get("model", settings.seedream_model),
            "size": items[0].get("size"), "usage": response.get("usage", {}),
            "request_id": scope.request_id,
        }
    return image


def _runninghub_mapping() -> dict | None:
    path = Path(__file__).with_name("runninghub_mapping.json")
    mapping = json.loads(path.read_text(encoding="utf-8"))
    return mapping if mapping.get("photo_nodes") and mapping.get("prompt_node") else None


def _runninghub_ready() -> bool:
    return bool(settings.runninghub_api_key and settings.runninghub_workflow_id
                and _runninghub_mapping())


def _runninghub_image(photo_urls: list[str], prompt: str, seed: int, references: list[dict]) -> bytes:
    mapping = _runninghub_mapping()
    if not mapping or len(mapping["photo_nodes"]) < len(photo_urls) or (
        len(mapping.get("reference_nodes", [])) < len(references)
    ):
        raise _ProviderFailure("workflow_mapping_missing")
    base = "https://www.runninghub.cn"
    key = settings.runninghub_api_key

    def upload(url: str) -> str:
        image = _image_bytes(url)
        boundary = "wedding-" + uuid.uuid4().hex
        parts = []
        for name, value in (("apiKey", key), ("fileType", "input")):
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
        mime, extension = ("image/png", "png") if image.startswith(b"\x89PNG") else ("image/jpeg", "jpg")
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="input.{extension}"\r\nContent-Type: {mime}\r\n\r\n'.encode()
                     + image + f"\r\n--{boundary}--\r\n".encode())
        request = urllib.request.Request(base + "/task/openapi/upload",
            data=b"".join(parts), method="POST", headers={
                "Authorization": f"Bearer {key}", "Content-Type": f"multipart/form-data; boundary={boundary}",
            })
        result = json.loads(_read(request))
        if result.get("code") != 0:
            raise _ProviderFailure("upload_failed")
        return result["data"]["fileName"]

    def binding(node: dict, value) -> dict:
        return {"nodeId": str(node["nodeId"]), "fieldName": node["fieldName"], "fieldValue": str(value)}

    nodes = [binding(node, upload(url)) for node, url in zip(mapping["photo_nodes"], photo_urls)]
    nodes += [binding(node, upload(reference["url"]))
              for node, reference in zip(mapping.get("reference_nodes", []), references)]
    nodes.append(binding(mapping["prompt_node"], prompt))
    if mapping.get("seed_node"):
        nodes.append(binding(mapping["seed_node"], seed))
    result = _post_json(base + "/task/openapi/create", {
        "apiKey": key, "workflowId": settings.runninghub_workflow_id, "nodeInfoList": nodes,
    }, key)
    if result.get("code") != 0:
        raise _ProviderFailure("workflow_rejected")
    task_id = result["data"]["taskId"]
    while True:
        result = _post_json(base + "/task/openapi/outputs", {"apiKey": key, "taskId": task_id}, key)
        if result.get("code") == 0:
            outputs = result.get("data", [])
            if not isinstance(outputs, list) or len(outputs) != 1:
                raise _ProviderFailure("workflow_must_return_one_image")
            image = _read(urllib.request.Request(outputs[0]["fileUrl"]))
            usage.record("runninghub", settings.runninghub_workflow_id, "image", images=1)
            scope = _ACTIVE_SCOPE.get()
            if scope:
                scope.engine = "runninghub"
                scope.effective_seed = seed if mapping.get("seed_node") else -1
                scope.response_metadata = {"workflow_id": settings.runninghub_workflow_id,
                                           "task_id": task_id}
            return image
        if result.get("code") not in {804, 813}:
            raise _ProviderFailure("workflow_failed")
        time.sleep(min(1, _remaining()))


def generate_image(photo_urls: list[str], prompt: str, seed: int, references: list[dict]) -> bytes:
    """固定接口。主备参数都来自 settings；不改写最终提示词。"""
    if settings.fake_for("generation"):
        raise ImageCallFailure("示例模式请通过 generate 节点运行")
    if not photo_urls or not prompt.strip():
        raise ImageCallFailure("需要照片和完整的拍摄指令")
    if len(references) > settings.max_reference_images or len(photo_urls) + len(references) > 10:
        raise ImageCallFailure("参考图数量超过生图模型限制")
    if not settings.llm_api_key or not settings.seedream_model:
        log.warning("seedream_configuration_missing")
        raise ImageCallFailure("拍摄服务暂时未就绪，请稍后重试")
    scope = _ACTIVE_SCOPE.get()
    if scope is None:
        scope = _Scope(_Budget(settings.max_images_per_task),
                       time.monotonic() + settings.image_timeout_seconds)
        with _call_scope(scope):
            return generate_image(photo_urls, prompt, seed, references)
    backends = [("seedream", _seedream_image)]
    if _runninghub_ready():
        backends.append(("runninghub", _runninghub_image))
    for index, (engine, backend) in enumerate(backends):
        _remaining()
        scope.budget.reserve()
        started = time.monotonic()
        status, code = "succeeded", None
        scope.response_metadata = {}
        try:
            return backend(photo_urls, prompt, seed, references)
        except _ProviderFailure as error:
            status, code = ("unknown" if error.unknown else "failed"), error.code
            if error.retryable and not error.unknown and index + 1 < len(backends):
                continue
            raise ImageCallFailure(
                "生成结果暂时无法确认，请稍后查看服务记录" if error.unknown else "生图服务暂时不可用，请稍后重试",
                retryable=error.retryable and not error.unknown,
            )
        except ImageCallFailure:
            status, code = "failed", "input_or_budget_invalid"
            raise
        except Exception:
            status, code = "unknown", "client_error"
            raise ImageCallFailure("生图响应无法处理，请稍后查看服务记录")
        finally:
            event = {
                "engine": engine,
                "model": settings.seedream_model if engine == "seedream" else settings.runninghub_workflow_id,
                "seed": None if engine == "seedream" else scope.effective_seed,
                "seed_supported": engine != "seedream" and scope.effective_seed >= 0,
                "parameters": scope.parameters, "status": status, "error_code": code,
                "response": scope.response_metadata,
                "seconds": round(time.monotonic() - started, 3),
            }
            scope.records.append(event)
            log.info("generation_attempt %s", json.dumps(event, ensure_ascii=False))
    raise ImageCallFailure("生图服务暂时不可用")

