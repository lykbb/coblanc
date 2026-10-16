"""后台接口 /api/admin/*：只给管理员白名单（ADMIN_HOLDERS，默认 lyk）用，部署在独立站点（admin/）。

安全：
- 鉴权：nginx 访问密码 + 后台凭证（xx_admin，HttpOnly、SameSite=Strict；经 HTTPS 访问（X-Forwarded-Proto）或 COOKIE_SECURE=1 时加 Secure）。
  后台凭证要在后台站点用白名单里的人的邀请码兑换；空闲 ADMIN_SESSION_HOURS 小时失效，最长 ADMIN_MAX_DAYS 天。
  每次请求都重新核对白名单，移出白名单立即失效。
- CSRF：改动类请求必须带 X-Admin-CSRF: 1（跨站表单发不了自定义头），且 Origin 若存在必须与 Host 一致。
- 限流：兑换失败按 IP 锁定（与用户站共用计数）；nginx 另有 limit_req。
- 审计：登录成败、越权、所有改动和导出都写入 state_dir/admin_audit.jsonl，后台可查看。
"""

from __future__ import annotations

import json
import threading
import time
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from app import access
from app.common.config import settings
from app.common.errors import ModuleError
from app.common.progress import store

CSRF_HEADER = "x-admin-csrf"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_audit_lock = threading.Lock()


class AdminError(ModuleError):
    pass


def client_ip(request: Request) -> str:
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "")


def audit(request: Request, holder: str | None, action: str, detail: dict | None = None) -> None:
    entry = {"at": time.time(), "holder": holder, "ip": client_ip(request), "action": action, "detail": detail or {}}
    path = settings.state_dir / "admin_audit.jsonl"
    with _audit_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        path.chmod(0o600)


def read_audit(limit: int) -> list[dict]:
    path = settings.state_dir / "admin_audit.jsonl"
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    return [json.loads(line) for line in reversed(lines) if line.strip()]


def check_csrf(request: Request) -> None:
    if request.method in SAFE_METHODS:
        return
    origin = request.headers.get("origin")
    if request.headers.get(CSRF_HEADER) != "1" or (origin and urlsplit(origin).netloc != request.headers.get("host")):
        audit(request, None, "csrf_rejected", {"path": request.url.path, "origin": origin})
        raise AdminError("ADMIN_CSRF", "请求来源不对，请刷新后台页面再试")


def require_admin(request: Request) -> str:
    """后台接口的依赖：返回管理员名字。未登录 401，不在白名单 403，CSRF 不对 403。"""
    holder = access.holder_for(request.cookies.get(access.ADMIN_COOKIE), kind="admin")
    if holder is None:
        raise AdminError("ADMIN_UNAUTHORIZED", "请先登录后台")
    if holder not in settings.admin_holders:
        audit(request, holder, "forbidden", {"path": request.url.path})
        raise AdminError("ADMIN_FORBIDDEN", "没有后台权限")
    check_csrf(request)
    return holder


open_router = APIRouter(prefix="/api/admin")
router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])


# ---- 登录 ----


@open_router.get("/status")
def status(request: Request):
    holder = access.holder_for(request.cookies.get(access.ADMIN_COOKIE), kind="admin")
    ok = holder is not None and holder in settings.admin_holders
    return {"authorized": ok, "holder": holder if ok else None}


class RedeemBody(BaseModel):
    code: str = Field(max_length=64)


@open_router.post("/redeem")
def redeem(body: RedeemBody, request: Request, response: Response):
    check_csrf(request)
    ip = client_ip(request)
    if access.too_many_fails(ip):
        audit(request, None, "login_locked")
        raise AdminError("ACCESS_LIMITED", "尝试次数过多，请稍后再试")
    result = access.redeem(body.code, ip, request.headers.get("user-agent", ""), kind="admin", holders=settings.admin_holders)
    if result is None:
        audit(request, None, "login_failed")
        raise AdminError("ACCESS_INVALID", "邀请码无效或已被使用")
    token, holder = result
    https = settings.cookie_secure or request.headers.get("x-forwarded-proto") == "https"
    response.set_cookie(access.ADMIN_COOKIE, token, max_age=settings.admin_max_days * 86400,
                        httponly=True, samesite="strict", secure=https, path="/")
    audit(request, holder, "login")
    return {"authorized": True, "holder": holder}


@router.post("/logout")
def logout(request: Request, response: Response, holder: str = Depends(require_admin)):
    access.revoke_token(request.cookies.get(access.ADMIN_COOKIE))
    response.delete_cookie(access.ADMIN_COOKIE, path="/")
    audit(request, holder, "logout")
    return {"ok": True}


# ---- 邀请码 ----


@router.get("/access")
def access_overview():
    return access.overview() | {"admins": settings.admin_holders}


class CreateCodes(BaseModel):
    holders: list[str] = Field(default_factory=list, max_length=200)
    count: int = Field(0, ge=0, le=1000)
    prefix: str = Field("", max_length=40)


@router.post("/access/codes")
def create_codes(body: CreateCodes, request: Request, holder: str = Depends(require_admin)):
    names = [name.strip()[:40] for name in body.holders if name.strip()]
    if body.count:
        if not body.prefix.strip():
            raise AdminError("FILE_INVALID", "批量生成要填前缀")
        names += access.bulk_holders(body.count, body.prefix.strip())
    if not names:
        raise AdminError("FILE_INVALID", "请填写持有人")
    codes = access.create(names)
    audit(request, holder, "codes_created", {"holders": names if len(names) <= 20 else names[:20] + [f"…共 {len(names)} 个"]})
    return {"codes": [{"holder": name, "code": code} for name, code in codes]}


class RevokeHolder(BaseModel):
    holder: str = Field(max_length=40)


@router.post("/access/revoke")
def revoke_holder(body: RevokeHolder, request: Request, holder: str = Depends(require_admin)):
    count = access.revoke(body.holder)
    audit(request, holder, "holder_revoked", {"holder": body.holder, "count": count})
    return {"revoked": count}


@router.delete("/access/devices/{device_id}")
def revoke_device(device_id: str, request: Request, holder: str = Depends(require_admin)):
    ok = access.revoke_device(device_id)
    audit(request, holder, "device_revoked", {"device": device_id, "found": ok})
    return {"revoked": ok}


# ---- 任务（只读） ----


def _relative(value):
    """任务里的图片地址是用户站的绝对地址；改成相对路径，后台站点自己代理 /files。"""
    if isinstance(value, str):
        base = settings.public_base_url
        return value[len(base):] if value.startswith(base + "/files/") else None
    if isinstance(value, dict):
        return [url for item in value.values() for url in (_relative(item) or [])] or None
    if isinstance(value, list):
        return [url for item in value for url in ([_relative(item)] if isinstance(item, str) else (_relative(item) or [])) if url] or None
    return None


@router.get("/tasks")
def tasks(limit: int = 100):
    return {"items": [
        {"task_id": task_id, "updated_at": updated, "status": info.status, "step": info.step,
         "step_text": info.step_text, "error": info.error, "user_redo_count": info.user_redo_count}
        for task_id, updated, info in store.recent(max(1, min(limit, 500)))
    ]}


@router.get("/tasks/{task_id}")
def task_detail(task_id: str):
    from app import runner

    info = store.get(task_id)
    if info is None:
        raise AdminError("TASK_NOT_FOUND", "找不到这个任务")
    values = runner.values(task_id)
    return {
        "task_id": task_id, "status": info.status, "step": info.step, "error": info.error,
        "generation": values.get("generation"),
        "images": {
            "photos": _relative(values.get("photo_urls")) or (_relative(values.get("groom_photo_urls")) or []) + (_relative(values.get("bride_photo_urls")) or []),
            "previews": _relative(values.get("previews")) or [],
            "deliverables": _relative(values.get("deliverables")) or [],
        },
    }


# ---- 审计 ----


@router.get("/audit")
def audit_log(limit: int = 200):
    return {"items": read_audit(max(1, min(limit, 2000)))}
