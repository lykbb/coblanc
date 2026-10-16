"""任务进度登记（框架内部用）：节点开始时登记 step，接口查询时从这里读状态。"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

STEP_TEXT = {
    "intake": "小囍正在看你们的照片",
    "styling": "妆造师在设计造型",
    "framing": "摄影师在设计镜头",
    "composing": "小囍在把方案写成拍摄指令",
    "generating": "正在生成样片 / 套图",
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


PERSIST_FIELDS = ("status", "step", "step_text", "error", "user_redo_count")
# 重启时还在跑的任务：线程已经没了，标成可重试的系统错误，点「重试」从检查点继续
INTERRUPTED = {"running", "delivering"}


class TaskStore:
    """任务进度：内存里一份，同时写到 state_dir/tasks/<id>.json，服务重启后能读回来。"""

    def __init__(self, directory: Path | None = None, ttl_days: int | None = None) -> None:
        self._tasks: dict[str, TaskInfo] = {}
        self._guard = threading.Lock()
        self._dir = directory
        self._ttl_days = ttl_days

    def _directory(self) -> Path | None:
        if self._dir is None:
            try:
                from app.common.config import settings
                self._dir, self._ttl_days = settings.state_dir / "tasks", settings.retention_days
            except Exception:
                return None
        return self._dir

    def _path(self, task_id: str) -> Path | None:
        directory = self._directory()
        if directory is None or not task_id.replace("_", "").isalnum():
            return None
        return directory / f"{task_id}.json"

    def _save(self, task_id: str, info: TaskInfo) -> None:
        path = self._path(task_id)
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps({key: getattr(info, key) for key in PERSIST_FIELDS}, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
        except Exception:
            pass

    def _load(self, task_id: str) -> TaskInfo | None:
        path = self._path(task_id)
        if path is None or not path.exists():
            return None
        try:
            if self._ttl_days is not None and time.time() - path.stat().st_mtime > self._ttl_days * 86400:
                return None
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        info = TaskInfo(**{key: data.get(key) for key in PERSIST_FIELDS if key in data})
        from app.common.errors import normalize_error
        info.error = normalize_error(info.error, info.step)
        if info.status in INTERRUPTED:
            info.status = "failed"
            info.error = {"code": "GENERATION_FAILED", "category": "system", "step": info.step, "retryable": True,
                          "title": "服务刚重启，这一步被中断了",
                          "message": "服务更新重启打断了处理（不是你们的问题），点「重试」会从中断的那一步继续。"}
        return info

    def create(self, task_id: str) -> TaskInfo:
        with self._guard:
            info = self._tasks[task_id] = TaskInfo()
            self._save(task_id, info)
            return info

    def get(self, task_id: str) -> TaskInfo | None:
        info = self._tasks.get(task_id)
        if info is not None:
            return info
        with self._guard:
            if task_id not in self._tasks:
                loaded = self._load(task_id)
                if loaded is None:
                    return None
                self._tasks[task_id] = loaded
                self._save(task_id, loaded)
            return self._tasks[task_id]

    def update(self, task_id: str, **fields) -> None:
        self.get(task_id)
        with self._guard:
            info = self._tasks[task_id]
            for key, value in fields.items():
                setattr(info, key, value)
            self._save(task_id, info)

    def transition(self, task_id: str, expected: str, new: str) -> bool:
        """状态是 expected 时才改成 new，避免同一个操作被提交两次。"""
        self.get(task_id)
        with self._guard:
            info = self._tasks.get(task_id)
            if info is None or info.status != expected:
                return False
            info.status = new
            self._save(task_id, info)
            return True

    def purge_expired(self) -> list[str]:
        """删除超过保存天数的任务记录，返回被删的任务编号。"""
        directory = self._directory()
        if directory is None or not directory.exists() or self._ttl_days is None:
            return []
        deadline = time.time() - self._ttl_days * 86400
        removed = []
        for path in directory.glob("*.json"):
            if path.stat().st_mtime < deadline:
                path.unlink(missing_ok=True)
                removed.append(path.stem)
        return removed


store = TaskStore()
