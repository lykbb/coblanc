"""后台管理接口 /api/admin/*（独立站点 admin/，/abordadmin/ 或 abordadmin.BASE；只给 ADMIN_HOLDERS，默认 lyk）：邀请码、任务（只读）、审计。

IP 白名单、CSRF、审计见 app/portal.py；账号密码登录见 app/login.py。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app import access
from app.common.config import settings
from app.common.progress import store
from app.portal import PortalError, admin, read_audit

status_router = admin.status_router()
router = APIRouter(prefix="/api/admin", dependencies=[Depends(admin.require)])


# ---- 邀请码 ----


@router.get("/access")
def access_overview():
    return access.overview() | {"admins": settings.admin_holders, "members": settings.gallery_members}


class CreateCodes(BaseModel):
    holders: list[str] = Field(default_factory=list, max_length=200)
    count: int = Field(0, ge=0, le=1000)
    prefix: str = Field("", max_length=40)


@router.post("/access/codes")
def create_codes(body: CreateCodes, request: Request, holder: str = Depends(admin.require)):
    names = [name.strip()[:40] for name in body.holders if name.strip()]
    if body.count:
        if not body.prefix.strip():
            raise PortalError("FILE_INVALID", "批量生成要填前缀")
        names += access.bulk_holders(body.count, body.prefix.strip())
    if not names:
        raise PortalError("FILE_INVALID", "请填写持有人")
    codes = access.create(names)
    admin.audit(request, holder, "codes_created", {"holders": names if len(names) <= 20 else names[:20] + [f"…共 {len(names)} 个"]})
    return {"codes": [{"holder": name, "code": code} for name, code in codes]}


class RevokeHolder(BaseModel):
    holder: str = Field(max_length=40)


@router.post("/access/revoke")
def revoke_holder(body: RevokeHolder, request: Request, holder: str = Depends(admin.require)):
    count = access.revoke(body.holder)
    admin.audit(request, holder, "holder_revoked", {"holder": body.holder, "count": count})
    return {"revoked": count}


@router.delete("/access/devices/{device_id}")
def revoke_device(device_id: str, request: Request, holder: str = Depends(admin.require)):
    ok = access.revoke_device(device_id)
    admin.audit(request, holder, "device_revoked", {"device": device_id, "found": ok})
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
         "operator": info.operator, "operator_source": info.operator_source,
         "step_text": info.step_text, "error": info.error, "user_redo_count": info.user_redo_count}
        for task_id, updated, info in store.recent(max(1, min(limit, 500)))
    ]}


@router.get("/tasks/{task_id}")
def task_detail(task_id: str):
    from app import runner

    info = store.get(task_id)
    if info is None:
        raise PortalError("TASK_NOT_FOUND", "找不到这个任务")
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
