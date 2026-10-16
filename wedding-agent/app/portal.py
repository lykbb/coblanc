"""内部站点的登录与防护（后台 admin、图墙 gallery 共用；用户站见 app/access.py）。

每个站点：独立接口前缀、独立凭证 Cookie（HttpOnly、SameSite=Strict；经 HTTPS 或 COOKIE_SECURE=1 时加 Secure）、
独立名单、空闲超时。凭证用名单里的人的邀请码在该站点兑换；不在名单里的码按无效处理且不作废。
- 每次请求重新核对名单，移出立即失效；不在名单 403 并记审计。
- 部署方式（deploy.sh 的 SITE_MODE）：path（默认，同一 IP 下 /gallery/、/abordadmin/）或 subdomain（gallery.BASE、abordadmin.BASE）。
  nginx 把站点的 <前缀>api/ 转到后端 /api/<站点>/，并用 X-Forwarded-Prefix 告诉后端站点前缀；凭证 Cookie 的 Path 限定在该前缀。
- CSRF：改动类请求必须带 X-Portal-CSRF: 1（跨站表单发不了自定义头），Origin 若存在须与 Host 一致；
  path 模式下 Referer 还必须来自本站前缀（站点页面 Referrer-Policy: same-origin），同 IP 下的其他页面发不了。
- 限流：兑换失败按 IP 锁定（app/access.py）；nginx 另有 limit_req。
- 审计：登录成败、越权、拦截、所有改动和导出都写 state_dir/portal_audit.jsonl（带站点名），后台可查看。
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from typing import Callable
import re
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from app import access
from app.common.config import settings
from app.common.errors import ModuleError

CSRF_HEADER = "x-portal-csrf"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_audit_lock = threading.Lock()


class PortalError(ModuleError):
    pass


def client_ip(request: Request) -> str:
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "")


def _audit_path():
    return settings.state_dir / "portal_audit.jsonl"


def write_audit(request: Request, site: str, holder: str | None, action: str, detail: dict | None = None) -> None:
    entry = {"at": time.time(), "site": site, "holder": holder, "ip": client_ip(request), "action": action, "detail": detail or {}}
    path = _audit_path()
    with _audit_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        path.chmod(0o600)


def read_audit(limit: int) -> list[dict]:
    path = _audit_path()
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    return [json.loads(line) for line in reversed(lines) if line.strip()]


def site_prefix(request: Request) -> str:
    """nginx 传来的站点前缀，如 /gallery/；子域名模式或直连后端时是 /。"""
    prefix = request.headers.get("x-forwarded-prefix", "/")
    return prefix if re.fullmatch(r"/(?:[a-z]+/)?", prefix) else "/"


def cookie_path(request: Request) -> str:
    return site_prefix(request).rstrip("/") or "/"


class RedeemBody(BaseModel):
    code: str = Field(max_length=64)


@dataclass
class Portal:
    site: str  # admin / gallery，也是 access 里的凭证种类
    holders: Callable[[], list[str]]  # 每次调用读当前设置

    @property
    def cookie(self) -> str:
        return access.PORTAL_COOKIES[self.site]

    @property
    def prefix(self) -> str:
        return f"/api/{self.site}"

    def audit(self, request: Request, holder: str | None, action: str, detail: dict | None = None) -> None:
        write_audit(request, self.site, holder, action, detail)

    def check_csrf(self, request: Request) -> None:
        if request.method in SAFE_METHODS:
            return
        origin = request.headers.get("origin")
        host = request.headers.get("host")
        bad = request.headers.get(CSRF_HEADER) != "1" or (origin and urlsplit(origin).netloc != host)
        prefix = site_prefix(request)
        if not bad and prefix != "/":
            referer = urlsplit(request.headers.get("referer", ""))
            bad = referer.netloc != host or not referer.path.startswith(prefix)
        if bad:
            self.audit(request, None, "csrf_rejected", {"path": request.url.path, "origin": origin})
            raise PortalError("PORTAL_CSRF", "请求来源不对，请刷新页面再试")

    def current(self, request: Request) -> str | None:
        holder = access.holder_for(request.cookies.get(self.cookie), kind=self.site)
        return holder if holder in self.holders() else None

    def require(self, request: Request) -> str:
        """接口依赖：返回登录人。未登录 401，不在名单 403（记审计），CSRF 不对 403。"""
        holder = access.holder_for(request.cookies.get(self.cookie), kind=self.site)
        if holder is None:
            raise PortalError("PORTAL_UNAUTHORIZED", "请先登录")
        if holder not in self.holders():
            self.audit(request, holder, "forbidden", {"path": request.url.path})
            raise PortalError("PORTAL_FORBIDDEN", "没有权限")
        self.check_csrf(request)
        return holder

    def login_router(self) -> APIRouter:
        """status / redeem / logout 三个接口。"""
        router = APIRouter(prefix=self.prefix)

        @router.get("/status")
        def status(request: Request):
            holder = self.current(request)
            return {"authorized": holder is not None, "holder": holder}

        @router.post("/redeem")
        def redeem(body: RedeemBody, request: Request, response: Response):
            self.check_csrf(request)
            ip = client_ip(request)
            if access.too_many_fails(ip):
                self.audit(request, None, "login_locked")
                raise PortalError("ACCESS_LIMITED", "尝试次数过多，请稍后再试")
            result = access.redeem(body.code, ip, request.headers.get("user-agent", ""), kind=self.site, holders=self.holders())
            if result is None:
                self.audit(request, None, "login_failed")
                raise PortalError("ACCESS_INVALID", "邀请码无效或已被使用")
            token, holder = result
            https = settings.cookie_secure or request.headers.get("x-forwarded-proto") == "https"
            response.set_cookie(self.cookie, token, max_age=settings.portal_max_days * 86400,
                                httponly=True, samesite="strict", secure=https, path=cookie_path(request))
            self.audit(request, holder, "login")
            return {"authorized": True, "holder": holder}

        @router.post("/logout")
        def logout(request: Request, response: Response, holder: str = Depends(self.require)):
            access.revoke_token(request.cookies.get(self.cookie))
            response.delete_cookie(self.cookie, path=cookie_path(request))
            self.audit(request, holder, "logout")
            return {"ok": True}

        return router


admin = Portal("admin", lambda: settings.admin_holders)
gallery = Portal("gallery", lambda: list(dict.fromkeys(settings.admin_holders + settings.gallery_members)))
