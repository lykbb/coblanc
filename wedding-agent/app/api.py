"""前后端接口（框架维护）。字段和错误码以《小囍接口约定》为准，改这里之前先改文档。

启动：uv run uvicorn app.api:app --reload --port 8000
接口说明页：http://127.0.0.1:8000/docs
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import runner
from app.modules.intake import photo_rules
from app.common.config import settings
from app.common.errors import ModuleError
from app.common.log import get_logger
from app.common.progress import store
from app.modules.assets import purge_expired, save_image
from app.modules.assets.node import TEMPLATES_DIR
from app.state import Consent

log = get_logger("api")
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
HTTP_STATUS = {
    "PHOTO_INVALID": 400,
    "FILE_INVALID": 400,
    "TASK_NOT_FOUND": 404,
    "WRONG_STATUS": 409,
    "REDO_LIMIT": 409,
    "GENERATION_FAILED": 500,
}
# file_id → 图片地址。demo 阶段放内存里，服务重启后需要重新上传。
class _Uploads(dict):
    """上传编号 → 地址。内存里没有时按文件名到 storage/upload 里找（服务重启后仍可用）。"""

    def _find(self, file_id: str) -> str | None:
        if not isinstance(file_id, str) or not file_id.startswith("f_") or not file_id[2:].isalnum():
            return None
        folder = settings.storage_dir / "upload"
        for path in folder.glob(file_id[2:] + ".*") if folder.exists() else []:
            return f"{settings.public_base_url}/files/upload/{path.name}"
        return None

    def __contains__(self, file_id) -> bool:
        return dict.__contains__(self, file_id) or self._find(file_id) is not None

    def __getitem__(self, file_id):
        if dict.__contains__(self, file_id):
            return dict.__getitem__(self, file_id)
        url = self._find(file_id)
        if url is None:
            raise KeyError(file_id)
        return url


uploads: dict[str, str] = _Uploads()


class ApiError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message


@asynccontextmanager
async def lifespan(_: FastAPI):
    removed = purge_expired()
    if removed:
        log.info("删除了 %d 个过期文件", removed)
    for task_id in store.purge_expired():
        try:
            runner.forget(task_id)
        except Exception:
            pass
    yield


app = FastAPI(title="小囍 API", description="字段和错误码以《小囍接口约定》为准", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])
settings.storage_dir.mkdir(parents=True, exist_ok=True)
app.mount("/files", StaticFiles(directory=settings.storage_dir), name="files")
app.mount("/templates", StaticFiles(directory=TEMPLATES_DIR), name="templates")


@app.exception_handler(ApiError)
@app.exception_handler(ModuleError)
async def _handle_error(_: Request, error):
    status = HTTP_STATUS.get(error.code, 400)
    return JSONResponse({"error": {"code": error.code, "message": error.message}}, status_code=status)


def _task(task_id: str):
    info = store.get(task_id)
    if info is None:
        raise ApiError("TASK_NOT_FOUND", "找不到这个任务，可能已经过期了")
    return info


def _take(task_id: str, expected: str, new: str = "running") -> None:
    _task(task_id)
    if not store.transition(task_id, expected, new):
        raise ApiError("WRONG_STATUS", "现在还不能做这一步，请刷新一下")


# ---- 1. 上传图片 ----


@app.post("/api/uploads")
async def upload_image(file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise ApiError("FILE_INVALID", "图片不能超过 10 MB")
    try:
        url = save_image(data, "upload")
    except ValueError:
        raise ApiError("FILE_INVALID", "只支持 jpg 和 png 图片")
    file_id = "f_" + url.rsplit("/", 1)[1].split(".")[0]
    uploads[file_id] = url
    return {"file_id": file_id, "url": url}


# ---- 2. 创建任务 ----


class CreateTaskBody(BaseModel):
    # 主入口：photo_file_ids，一个上传框，合照单人照混传；规则见 intake/photo_rules.py，由小囍分出新郎新娘。
    # groom_photo_file_ids / bride_photo_file_ids 是分开上传的旧写法，保留兼容。
    photo_file_ids: list[str] = Field(default_factory=list)
    groom_photo_file_ids: list[str] = Field(default_factory=list)
    bride_photo_file_ids: list[str] = Field(default_factory=list)
    description: str = ""
    consent: Consent | None = None


@app.post("/api/tasks")
def create_task(body: CreateTaskBody):
    grouped = bool(body.groom_photo_file_ids or body.bride_photo_file_ids)
    if grouped and (not body.groom_photo_file_ids or not body.bride_photo_file_ids):
        raise ApiError("PHOTO_INVALID", "请分别上传新郎和新娘各 1～10 张正面生活照")
    if grouped and (
        not 1 <= len(body.groom_photo_file_ids) <= 10
        or not 1 <= len(body.bride_photo_file_ids) <= 10
    ):
        raise ApiError("PHOTO_INVALID", "新郎和新娘的照片数量都必须是 1～10 张")
    if not grouped:
        body.photo_file_ids = photo_rules.dedupe(body.photo_file_ids)
        problem = photo_rules.count_problem(len(body.photo_file_ids))
        if problem:
            raise ApiError("PHOTO_INVALID", problem)
    file_ids = body.groom_photo_file_ids + body.bride_photo_file_ids if grouped else body.photo_file_ids
    missing = [file_id for file_id in file_ids if file_id not in uploads]
    if missing:
        raise ApiError("FILE_INVALID", "找不到上传的照片，请重新上传")
    groom_urls = [uploads[file_id] for file_id in body.groom_photo_file_ids]
    bride_urls = [uploads[file_id] for file_id in body.bride_photo_file_ids]
    task_id = runner.start(
        [uploads[file_id] for file_id in file_ids],
        body.description,
        groom_photo_urls=groom_urls or None,
        bride_photo_urls=bride_urls or None,
        consent=body.consent.model_dump() if body.consent else None,
    )
    return {"task_id": task_id, "status": "running"}


# ---- 3. 查询任务 ----


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str):
    info = _task(task_id)
    values = runner.values(task_id)
    status = info.status
    return {
        "task_id": task_id,
        "status": status,
        "step": info.step,
        "step_text": info.step_text,
        "questions": values.get("questions", []) if status == "waiting_user" else [],
        "consent": values.get("consent"),
        # 生图阶段和累计数量让前端能区分 1 张样片与 9 张套图。
        "generation": values.get("generation"),
        "photo_counts": {
            "groom": len(values.get("groom_photo_urls", [])),
            "bride": len(values.get("bride_photo_urls", [])),
            "legacy": len(values.get("photo_urls", [])) if not values.get("groom_photo_urls") else 0,
        },
        "previews": values.get("previews", []) if status == "preview_ready" else [],
        "quality_note": values.get("quality_note") if status == "preview_ready" else None,
        "deliverables": values.get("deliverables") if status == "done" else None,
        "message": values.get("message") if status == "done" else None,
        "error": info.error if status == "failed" else None,
        "plan": _plan(values),
    }


def _plan(values: dict) -> dict:
    """只读的方案进度，给前端画布显示。只挑用户能看的字段，提示词、评分等内部信息不外露。"""
    brief = values.get("brief")
    return {
        "photos": {
            "groom": list(values.get("groom_photo_urls") or []),
            "bride": list(values.get("bride_photo_urls") or []),
            "all": list(values.get("photo_urls") or []),
        },
        "brief": {key: brief.get(key) for key in ("heights_cm", "materials", "invitation", "keep_features", "beautify")}
        if brief else None,
        "look": values.get("look"),
        "shot": values.get("shot"),
        "shots": list(values.get("shots") or []),
    }


# ---- 4. 提交回答 ----


class Answer(BaseModel):
    question_id: str
    value: Any = None
    skipped: bool = False


class AnswersBody(BaseModel):
    answers: list[Answer]


def _attach_upload_urls(task_id: str, answers: list[dict]) -> list[dict]:
    """补传照片题（type 为 upload）：value 是上传编号（一个或一组），框架换成地址放进 urls。

    value 原样保留；跳过的回答不附 urls。要不要用这些地址、换哪几张，由提问的模块自己决定。
    """
    _task(task_id)
    upload_ids = {q["question_id"] for q in runner.values(task_id).get("questions") or [] if q.get("type") == "upload"}
    result = []
    for answer in answers:
        if answer["question_id"] in upload_ids and not answer.get("skipped"):
            value = answer.get("value")
            file_ids = [value] if isinstance(value, str) else (value or [])
            # 允许只留言不传图（例如“小狗要一起入镜”），此时 urls 为空
            if not isinstance(file_ids, list) or not all(isinstance(item, str) for item in file_ids):
                raise ApiError("PHOTO_INVALID", "请上传照片后再提交")
            missing = [file_id for file_id in file_ids if file_id not in uploads]
            if missing:
                raise ApiError("FILE_INVALID", "找不到上传的照片，请重新上传")
            answer = {**answer, "urls": [uploads[file_id] for file_id in file_ids]}
        result.append(answer)
    return result


@app.post("/api/tasks/{task_id}/retry")
def retry_task(task_id: str):
    error = _task(task_id).error or {}
    if not error.get("retryable"):
        raise ApiError("WRONG_STATUS", "这个任务不能重试，请重新开始")
    _take(task_id, "failed")
    runner.retry(task_id)
    return {"status": "running"}


@app.post("/api/tasks/{task_id}/answers")
def submit_answers(task_id: str, body: AnswersBody):
    answers = _attach_upload_urls(task_id, [answer.model_dump() for answer in body.answers])
    _take(task_id, "waiting_user")
    runner.resume(task_id, answers)
    return {"status": "running"}


# ---- 5. 确认或重做 ----


class ReviewBody(BaseModel):
    # confirm：样片阶段 → 出 9 张套图；套图阶段 → 去支付。
    # sample_only：只在样片阶段可用，跳过套图，直接用这张样片去支付和交付。
    action: Literal["confirm", "redo", "sample_only"]
    image_id: str
    reason: Literal["face", "body", "hands", "style", "other"] | None = None
    note: str | None = None


@app.post("/api/tasks/{task_id}/review")
def review(task_id: str, body: ReviewBody):
    info = _task(task_id)
    values = runner.values(task_id)
    previews = values.get("previews", [])
    if body.image_id not in {item["image_id"] for item in previews}:
        raise ApiError("WRONG_STATUS", "找不到这张预览图，请刷新一下")
    stage = (values.get("generation") or {}).get("stage")
    if body.action == "sample_only" and stage != "sample":
        raise ApiError("WRONG_STATUS", "只有样片阶段可以选择只要这一张")
    if body.action == "redo" and info.user_redo_count >= settings.max_user_redo:
        raise ApiError("REDO_LIMIT", f"已经重做 {settings.max_user_redo} 次了，请联系人工帮你调整")
    _take(task_id, "preview_ready")
    if body.action == "redo":
        store.update(task_id, user_redo_count=info.user_redo_count + 1)
    runner.resume(task_id, body.model_dump())
    # 样片确认会继续跑套图；套图确认才进入支付。
    sample_confirmed = body.action == "confirm" and stage == "sample"
    return {"status": "running" if sample_confirmed or body.action == "redo" else "awaiting_payment"}


# ---- 6. 模拟支付 ----


class PayBody(BaseModel):
    method: str = "mock"


@app.post("/api/tasks/{task_id}/pay")
def pay(task_id: str, body: PayBody):
    _take(task_id, "awaiting_payment", "delivering")
    runner.resume(task_id, {"method": body.method})
    return {"status": "delivering"}
