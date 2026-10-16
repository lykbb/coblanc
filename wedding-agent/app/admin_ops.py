"""后台只读运维页：模型用量 /api/admin/usage、服务器 /api/admin/server、项目文件 /api/admin/files/*。

都挂在后台路由下（IP 白名单 + 后台登录会话，见 app/portal.py）。项目文件只读、限定在项目根目录，
敏感文件（.env*、密钥、证书、htpasswd、access.json 等）一律拒绝；查看和下载记审计。
"""

from __future__ import annotations

import mimetypes
import os
import platform
import re
import shutil
import subprocess
import time
from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse

from app import reference_wall
from app.common import usage
from app.common.config import ROOT, settings
from app.common.progress import store
from app.portal import PortalError, admin

router = APIRouter(prefix="/api/admin", dependencies=[Depends(admin.require)])

# ---- 模型用量 ----

PERIODS = {"today": None, "7d": 7, "30d": 30}


def _since(period: str) -> float:
    if period == "today":
        now = time.localtime()
        return time.mktime((now.tm_year, now.tm_mon, now.tm_mday, 0, 0, 0, 0, 0, -1))
    return time.time() - PERIODS[period] * 86400


def _bucket() -> dict:
    return {"calls": 0, "input": 0, "output": 0, "total": 0, "images": 0, "cost": None, "currency": None}


def _add(bucket: dict, entry: dict, priced: tuple[float, str] | None) -> None:
    bucket["calls"] += 1
    for key in ("input", "output", "total", "images"):
        bucket[key] += entry.get(key, 0)
    if priced:
        bucket["cost"] = (bucket["cost"] or 0) + priced[0]
        bucket["currency"] = priced[1]


@router.get("/usage")
def usage_summary(period: str = "7d"):
    if period not in PERIODS:
        raise PortalError("FILE_INVALID", "时间范围不对")
    entries = usage.read(_since(period))
    table = usage.prices()
    models: dict = defaultdict(_bucket)
    tasks: dict = defaultdict(_bucket)
    days: dict = defaultdict(_bucket)
    total = _bucket()
    for entry in entries:
        priced = usage.cost(entry, table)
        _add(models[(entry["provider"], entry["model"], entry["kind"])], entry, priced)
        _add(tasks[entry.get("task_id") or "—"], entry, priced)
        _add(days[time.strftime("%Y-%m-%d", time.localtime(entry["at"]))], entry, priced)
        _add(total, entry, priced)
    return {
        "period": period, "total": total, "priced_models": sorted(table),
        "models": [{"provider": p, "model": m, "kind": k, **v} for (p, m, k), v in sorted(models.items(), key=lambda x: -x[1]["total"])],
        "tasks": [{"task_id": t, **v} for t, v in sorted(tasks.items(), key=lambda x: -x[1]["total"])][:200],
        "days": [{"day": d, **v} for d, v in sorted(days.items())],
    }


# ---- 服务器 ----


def _read(path: str) -> str:
    try:
        return Path(path).read_text()
    except OSError:
        return ""


def _meminfo() -> dict:
    info = {}
    for line in _read("/proc/meminfo").splitlines():
        key, _, value = line.partition(":")
        if value.strip().endswith("kB"):
            info[key] = int(value.split()[0]) * 1024
    return info


def _cpu_percent() -> float | None:
    def sample():
        fields = _read("/proc/stat").split("\n", 1)[0].split()[1:]
        values = [int(v) for v in fields]
        return (values[3] + (values[4] if len(values) > 4 else 0)), sum(values)
    if not _read("/proc/stat"):
        return None
    idle1, total1 = sample()
    time.sleep(0.3)
    idle2, total2 = sample()
    return round(100 * (1 - (idle2 - idle1) / max(1, total2 - total1)), 1)


def _service(name: str) -> str:
    try:
        return subprocess.run(["systemctl", "is-active", name], capture_output=True, text=True, timeout=3).stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _os_name() -> str:
    match = re.search(r'^PRETTY_NAME="?([^"\n]+)', _read("/etc/os-release"), re.M)
    return match.group(1) if match else platform.platform()


@router.get("/server")
def server():
    mem = _meminfo()
    disk = shutil.disk_usage(ROOT)
    uptime = _read("/proc/uptime").split()
    statuses = [info.status for _, _, info in store.recent(500)]
    return {
        "at": time.time(),
        "cpu": {"percent": _cpu_percent(), "cores": os.cpu_count(), "load": list(os.getloadavg())},
        "memory": {"total": mem.get("MemTotal"), "available": mem.get("MemAvailable"),
                   "swap_total": mem.get("SwapTotal"), "swap_free": mem.get("SwapFree")},
        "disk": {"total": disk.total, "used": disk.used, "free": disk.free},
        "references": {"used": reference_wall.used_bytes(), "cap": int(settings.reference_cap_gb * 1024**3)},
        "uptime_seconds": float(uptime[0]) if uptime else None,
        "os": _os_name(), "kernel": platform.release(), "hostname": platform.node(),
        "services": {name: _service(name) for name in ("wedding-backend", "nginx", "fail2ban")},
        "tasks": {"running": statuses.count("running") + statuses.count("delivering"),
                  "queued": statuses.count("queued") + statuses.count("pending")},
    }


# ---- 项目文件（只读） ----

PROJECT_ROOT = ROOT.parent  # 服务器上是 ~/ai-wedding
PREVIEW_LIMIT = 512 * 1024
SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__"}
_BLOCKED = re.compile(
    r"(^\.env|\.pem$|\.key$|\.p12$|\.pfx$|\.crt$|^id_(rsa|ed25519|ecdsa|dsa)|htpasswd|^access\.json$|secret|credential|"
    r"^(?!token_prices).*token.*\.(json|txt|ya?ml)$|password|\.keystore$|^\.netrc$|^\.npmrc$|^\.pypirc$)", re.I)
IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


def blocked(path: Path) -> bool:
    return any(_BLOCKED.search(part) or part in (".git", "ubuntu@43.142.59.166") for part in path.relative_to(PROJECT_ROOT).parts)


def _resolve(rel: str) -> Path:
    if "\x00" in rel or len(rel) > 1000:
        raise PortalError("FILE_INVALID", "路径不对")
    root = PROJECT_ROOT.resolve()
    target = (root / rel.lstrip("/")).resolve()  # 解析符号链接后必须仍在项目根目录下
    if target != root and root not in target.parents:
        raise PortalError("FILE_FORBIDDEN", "不能访问项目以外的文件")
    if target != root and blocked(target):
        raise PortalError("FILE_FORBIDDEN", "这个文件不能查看")
    if not target.exists():
        raise PortalError("FILE_NOT_FOUND", "找不到这个文件")
    return target


def _rel(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT.resolve()).as_posix()


@router.get("/files/list")
def list_dir(path: str = ""):
    folder = _resolve(path)
    if not folder.is_dir():
        raise PortalError("FILE_INVALID", "不是文件夹")
    items = []
    for child in sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        try:
            real = child.resolve()
            if (real != PROJECT_ROOT.resolve() and PROJECT_ROOT.resolve() not in real.parents) or blocked(real) or child.name in SKIP_DIRS:
                continue
            stat = real.stat()
        except (OSError, ValueError):
            continue
        items.append({"name": child.name, "path": _rel(real), "dir": real.is_dir(), "size": None if real.is_dir() else stat.st_size, "mtime": stat.st_mtime})
    return {"path": "" if folder == PROJECT_ROOT.resolve() else _rel(folder), "items": items}


@router.get("/files/view")
def view(path: str, request: Request, holder: str = Depends(admin.require)):
    target = _resolve(path)
    if not target.is_file():
        raise PortalError("FILE_INVALID", "不是文件")
    size = target.stat().st_size
    admin.audit(request, holder, "file_viewed", {"path": _rel(target)})
    if target.suffix.lower() in IMAGE_TYPES:
        return {"path": _rel(target), "size": size, "kind": "image"}
    with target.open("rb") as f:
        data = f.read(PREVIEW_LIMIT)
    if b"\x00" in data[:8192]:
        return {"path": _rel(target), "size": size, "kind": "binary"}
    return {"path": _rel(target), "size": size, "kind": "text", "text": data.decode("utf-8", errors="replace"), "truncated": size > PREVIEW_LIMIT}


@router.get("/files/raw")
def raw(path: str, request: Request, download: bool = False, holder: str = Depends(admin.require)):
    target = _resolve(path)
    if not target.is_file():
        raise PortalError("FILE_INVALID", "不是文件")
    inline = not download and target.suffix.lower() in IMAGE_TYPES
    if download:
        admin.audit(request, holder, "file_downloaded", {"path": _rel(target)})
    media = mimetypes.guess_type(target.name)[0] if inline else "application/octet-stream"
    return FileResponse(target, media_type=media or "application/octet-stream", filename=target.name,
                        content_disposition_type="inline" if inline else "attachment",
                        headers={"Content-Security-Policy": "sandbox; default-src 'none'", "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})
