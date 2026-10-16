"""在后台线程里跑流程（框架维护）：开始、在等用户的地方暂停、收到用户输入后继续。"""

from __future__ import annotations

import threading
import uuid

from langgraph.types import Command

from app.common.errors import ModuleError
from app.common.log import current_task, get_logger
from app.common.progress import store
from app.graph import graph

log = get_logger("runner")
PAUSE_STATUS = {"questions": "waiting_user", "review": "preview_ready", "payment": "awaiting_payment"}


def _config(task_id: str) -> dict:
    return {"configurable": {"thread_id": task_id}}


def start(
    photo_urls: list[str],
    description: str,
    *,
    groom_photo_urls: list[str] | None = None,
    bride_photo_urls: list[str] | None = None,
    consent: dict | None = None,
) -> str:
    task_id = f"t_{uuid.uuid4().hex[:8]}"
    store.create(task_id)
    groom = list(groom_photo_urls or [])
    bride = list(bride_photo_urls or [])
    initial = {
        "task_id": task_id,
        "photo_urls": photo_urls,
        "description": description,
        "answers": [],
        "question_rounds": {},
        "retry_count": 0,
        "user_feedback": None,
    }
    if groom or bride:
        initial["groom_photo_urls"] = groom
        initial["bride_photo_urls"] = bride
    if consent is not None:
        initial["consent"] = consent
    _spawn(task_id, initial)
    return task_id


USER_INPUT_CODES = {"PHOTO_INVALID", "FILE_INVALID"}
STEP_NAMES = {
    "intake": "小囍看照片/整理需求", "styling": "妆造师设计造型", "framing": "摄影师设计镜头",
    "composing": "合成生图指令", "generating": "生图", "checking": "审片质检",
    "retouching": "修图", "packaging": "制作婚礼物料",
}


def _error_info(task_id: str, code: str, message: str) -> dict:
    """失败原因分两类：user_input（上传内容不符合要求）/ system（模型、网络、服务异常，可重试）。"""
    step = store.get(task_id).step
    if code in USER_INPUT_CODES:
        return {"code": code, "category": "user_input", "step": step, "retryable": False,
                "title": "上传的照片不符合要求", "message": message}
    where = STEP_NAMES.get(step or "", "处理")
    return {"code": code, "category": "system", "step": step, "retryable": True,
            "title": f"系统异常：{where}这一步没完成",
            "message": f"{message}（模型/网络/服务异常，不是你们的问题），可以点「重试」从这一步继续。"}


def retry(task_id: str) -> None:
    """系统异常后从出错的那一步继续（LangGraph 会重跑未完成的节点）。"""
    store.update(task_id, error=None)
    _spawn(task_id, None)


def resume(task_id: str, value) -> None:
    """接口已经把状态改成 running / delivering 之后调用。"""
    _spawn(task_id, Command(resume=value))


def forget(task_id: str) -> None:
    """过期任务：删掉检查点。"""
    from app.graph import checkpointer
    checkpointer.delete_thread(task_id)


def values(task_id: str) -> dict:
    return graph.get_state(_config(task_id)).values


def _spawn(task_id: str, graph_input) -> None:
    threading.Thread(target=_run, args=(task_id, graph_input), daemon=True).start()


def _run(task_id: str, graph_input) -> None:
    current_task.set(task_id)
    info = store.get(task_id)
    with info.run_lock:
        try:
            graph.invoke(graph_input, _config(task_id))
        except ModuleError as error:
            log.warning("模块报错 %s：%s（步骤 %s）", error.code, error.message, store.get(task_id).step)
            store.update(task_id, status="failed", error=_error_info(task_id, error.code, error.message))
            return
        except Exception:
            log.exception("流程出错")
            store.update(
                task_id,
                status="failed",
                error=_error_info(task_id, "GENERATION_FAILED", "模型或网络暂时异常"),
            )
            return
        _sync_status(task_id)


def _sync_status(task_id: str) -> None:
    if store.get(task_id).status == "failed":
        return
    snapshot = graph.get_state(_config(task_id))
    pending = [item.value for task in snapshot.tasks for item in task.interrupts]
    if pending:
        store.update(task_id, status=PAUSE_STATUS[pending[0]["kind"]])
    elif not snapshot.next:
        store.update(task_id, status="done", step=None, step_text="作品完成啦")
