"""按月归档的 JSONL 记录（框架维护）：用量 usage、余额 balance、审计 portal_audit 共用。

- 当月写 state_dir/<name>.jsonl；进入新的月份后第一次写入前，把旧文件整体改名为
  state_dir/archive/<name>-YYYY-MM.jsonl（月份取文件里最晚一条的时间），不删任何数据。
- 读的时候只打开时间窗口用得到的文件：当月文件 + 月份不早于 since 的归档。
- 每条记录必须带 at（Unix 秒）。
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Callable, Iterable

from app.common.config import settings


def _month(at: float) -> str:
    return time.strftime("%Y-%m", time.localtime(at))


def _month_start(at: float) -> float:
    t = time.localtime(at)
    return time.mktime((t.tm_year, t.tm_mon, 1, 0, 0, 0, 0, 0, -1))


def _month_end(month: str) -> float:
    year, mon = map(int, month.split("-"))
    year, mon = (year + 1, 1) if mon == 12 else (year, mon + 1)
    return time.mktime((year, mon, 1, 0, 0, 0, 0, 0, -1))


def _parse(line: str) -> dict | None:
    try:
        item = json.loads(line)
    except ValueError:
        return None
    return item if isinstance(item, dict) else None


class MonthlyLog:
    def __init__(self, name: str, mode: int | None = None) -> None:
        self.name, self.mode = name, mode
        self.lock = threading.RLock()
        self._pattern = re.compile(rf"^{re.escape(name)}-(\d{{4}}-\d{{2}})(?:\.(\d+))?\.jsonl$")

    @property
    def path(self) -> Path:
        return settings.state_dir / f"{self.name}.jsonl"

    @property
    def archive_dir(self) -> Path:
        return settings.state_dir / "archive"

    def archives(self) -> list[tuple[str, Path]]:
        """（月份, 文件），按月份从早到晚。"""
        found = []
        if self.archive_dir.exists():
            for path in self.archive_dir.iterdir():
                match = self._pattern.match(path.name)
                if match:
                    found.append((match.group(1), int(match.group(2) or 0), path))
        return [(month, path) for month, _, path in sorted(found)]

    def _chmod(self, path: Path) -> None:
        if self.mode is not None:
            path.chmod(self.mode)

    def rotate(self, now: float | None = None) -> Path | None:
        """当月文件里第一条早于本月：整体归档。返回归档后的路径（没归档返回 None）。"""
        with self.lock:
            path = self.path
            try:
                with path.open(encoding="utf-8") as f:
                    first = next((item for item in map(_parse, f) if item), None)
            except FileNotFoundError:
                return None
            if not first or first.get("at", 0) >= _month_start(now or time.time()):
                return None
            latest = max((item.get("at", 0) for item in self._items(path)), default=first.get("at", 0))
            month = _month(latest)
            self.archive_dir.mkdir(parents=True, exist_ok=True)
            target, n = self.archive_dir / f"{self.name}-{month}.jsonl", 1
            while target.exists():
                target, n = self.archive_dir / f"{self.name}-{month}.{n}.jsonl", n + 1
            os.replace(path, target)
            return target

    def append(self, entries: Iterable[dict]) -> None:
        lines = "".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in entries)
        if not lines:
            return
        with self.lock:
            self.rotate()
            path = self.path
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(lines)
            self._chmod(path)

    def files(self, since: float = 0) -> list[Path]:
        """时间窗口要用到的文件，从早到晚：月份不早于 since 的归档 + 当月文件。"""
        first = _month(since) if since > 0 else ""
        return [path for month, path in self.archives() if month >= first] + [self.path]

    @staticmethod
    def _items(path: Path) -> list[dict]:
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        return [item for item in map(_parse, text.splitlines()) if item]

    def read(self, since: float = 0) -> list[dict]:
        """since 之后的记录（按文件顺序，不排序）。"""
        return [item for path in self.files(since) for item in self._items(path) if item.get("at", 0) >= since]

    def newest(self, limit: int) -> list[dict]:
        """最新的 limit 条（按 at 倒序）。从当月往前读，够数且更早的归档不可能更新时就停。"""
        items = self._items(self.path)
        for month, path in reversed(self.archives()):
            if sum(1 for item in items if item.get("at", 0) >= _month_end(month)) >= limit:
                break
            items += self._items(path)
        items.sort(key=lambda item: item.get("at", 0), reverse=True)
        return items[:limit]

    def rewrite(self, keep: Callable[[dict], bool], add: list[dict]) -> int:
        """改写全部记录（当月 + 归档）：去掉 keep 为假的，改过的文件先备份为 <文件>.bak-<时间>；add 追加到当月文件。返回去掉的条数。"""
        stamp = time.strftime("%Y%m%d-%H%M%S")
        dropped = 0
        with self.lock:
            self.rotate()
            for path in [p for _, p in self.archives()] + [self.path]:
                if not path.exists():
                    continue
                lines = path.read_text(encoding="utf-8").splitlines()
                kept = [line for line in lines if (item := _parse(line)) is None or keep(item)]
                if len(kept) == len(lines):
                    continue
                dropped += len(lines) - len(kept)
                path.with_name(f"{path.name}.bak-{stamp}").write_text("\n".join(lines) + "\n", encoding="utf-8")
                tmp = path.with_suffix(".tmp")
                tmp.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
                tmp.replace(path)
                self._chmod(path)
            self.append(add)
        return dropped
