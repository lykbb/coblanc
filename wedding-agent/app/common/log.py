"""日志（框架维护）：每条日志自动带上当前任务编号。不要把用户照片或密钥打进日志。"""

import contextvars
import logging

current_task: contextvars.ContextVar[str] = contextvars.ContextVar("current_task", default="-")
# 当前流水线步骤（graph 节点名，如 intake / style / frame / generate / check），用量和过程记录按它归到 agent
current_step: contextvars.ContextVar[str] = contextvars.ContextVar("current_step", default="-")


class _TaskFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.task_id = current_task.get()
        return True


_root = logging.getLogger("wedding")
if not _root.handlers:
    _handler = logging.StreamHandler()
    _handler.addFilter(_TaskFilter())
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(task_id)s] %(name)s: %(message)s"))
    _root.addHandler(_handler)
    _root.setLevel(logging.INFO)
    _root.propagate = False


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"wedding.{name}")
