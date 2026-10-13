"""在后台线程里跑流程（框架维护）：开始、在等用户的地方暂停、收到用户输入后继续。"""

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


def start(photo_urls: list[str], description: str) -> str:
    task_id = f"t_{uuid.uuid4().hex[:8]}"
    store.create(task_id)
    initial = {
        "task_id": task_id,
        "photo_urls": photo_urls,
        "description": description,
        "answers": [],
        "retry_count": 0,
        "user_feedback": None,
    }
    _spawn(task_id, initial)
    return task_id


def resume(task_id: str, value) -> None:
    """接口已经把状态改成 running / delivering 之后调用。"""
    _spawn(task_id, Command(resume=value))


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
            log.warning("模块报错 %s", error.code)
            store.update(task_id, status="failed", error={"code": error.code, "message": error.message})
            return
        except Exception:
            log.exception("流程出错")
            store.update(
                task_id,
                status="failed",
                error={"code": "GENERATION_FAILED", "message": "系统出了点问题，请稍后重新开始"},
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
