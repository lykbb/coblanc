"""任务进度登记（框架内部用）：节点开始时登记 step，接口查询时从这里读状态。"""

import threading
from dataclasses import dataclass, field

STEP_TEXT = {
    "intake": "小囍正在看你们的照片",
    "styling": "妆造师在设计造型",
    "framing": "摄影师在安排构图和姿势",
    "generating": "正在拍摄 4 张候选",
    "checking": "修图师在逐张质检",
    "retouching": "修图师在调整不满意的地方",
    "packaging": "正在制作请柬和婚礼物料",
}


@dataclass
class TaskInfo:
    status: str = "running"
    step: str | None = None
    step_text: str | None = None
    error: dict | None = None
    user_redo_count: int = 0
    run_lock: threading.Lock = field(default_factory=threading.Lock)


class TaskStore:
    def __init__(self) -> None:
        self._tasks: dict[str, TaskInfo] = {}
        self._guard = threading.Lock()

    def create(self, task_id: str) -> TaskInfo:
        with self._guard:
            info = self._tasks[task_id] = TaskInfo()
            return info

    def get(self, task_id: str) -> TaskInfo | None:
        return self._tasks.get(task_id)

    def update(self, task_id: str, **fields) -> None:
        with self._guard:
            info = self._tasks[task_id]
            for key, value in fields.items():
                setattr(info, key, value)

    def transition(self, task_id: str, expected: str, new: str) -> bool:
        """状态是 expected 时才改成 new，避免同一个操作被提交两次。"""
        with self._guard:
            info = self._tasks.get(task_id)
            if info is None or info.status != expected:
                return False
            info.status = new
            return True


store = TaskStore()
