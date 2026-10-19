"""内部站点的防护（后台 admin、图墙 gallery 共用；用户站见 app/access.py，账号密码登录见 app/login.py）。

- 图墙：只认来源 IP 白名单（access.portal_ips：团队成员有效前台设备的最近 IP + state/portal-extra-ips.txt），
  没有登录、密码和邀请码；白名单外的 IP 在 nginx 就被 403，后端再核一次。上传人按 IP 对应的成员记（access.ip_holder）。
- 后台：IP 白名单 + 账号密码登录会话（app/login.py，Cookie xx_admin，Path 限定站点前缀，HttpOnly、SameSite=Strict，空闲超时）。
- 部署方式（deploy.sh 的 SITE_MODE）：path（默认，同一 IP 下 /gallery/、/abordadmin/）或 subdomain（gallery.BASE、abordadmin.BASE）。
  nginx 把站点的 <前缀>api/ 转到后端 /api/<站点>/，并用 X-Forwarded-Prefix 告诉后端站点前缀。
- CSRF：改动类请求必须带 X-Portal-CSRF: 1（跨站表单发不了自定义头），Origin 若存在须与 Host 一致；
  path 模式下 Referer 还必须来自本站前缀（站点页面 Referrer-Policy: same-origin），同 IP 下的其他页面发不了。
- 审计：登录成败、越权、拦截、所有改动和导出都写 state_dir/portal_audit.jsonl（按月归档到 state_dir/archive/；带站点名、UA），后台可查看；
  页面访问、nginx 层的拒绝 / 限流 / 封禁见 app/audit_feed.py。
"""

from __future__ import annotations

import ipaddress
import time
from dataclasses import dataclass
import re
from urllib.parse import urlsplit

from fastapi import APIRouter, Request

from app import access
from app.common.config import settings
from app.common.errors import ModuleError
from app.common.monthly_log import MonthlyLog

CSRF_HEADER = "x-portal-csrf"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class PortalError(ModuleError):
    pass


TRUSTED_PROXIES = {"127.0.0.1", "::1"}  # 只信本机 nginx 传来的 X-Real-IP


class RealClientIP:
    """最外层 ASGI 中间件：请求来自本机代理且带合法 X-Real-IP 时，把连接地址换成真实客户端 IP。
    之后所有地方（白名单、审计、限流、uvicorn 访问日志）都只看 request.client。"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket") and scope.get("client") and scope["client"][0] in TRUSTED_PROXIES:
            real = dict(scope.get("headers") or []).get(b"x-real-ip", b"").decode("latin-1").strip()
            try:
                ipaddress.ip_address(real)
                scope["client"] = (real, scope["client"][1])
            except ValueError:
                pass
        await self.app(scope, receive, send)


def client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


def member_of(request: Request, ip: str | None = None) -> tuple[str | None, str | None]:
    """这次操作是哪位成员：用户站设备凭证（邀请码绑定）→ device；否则按 IP 对应的设备持有人 → ip（推断）。"""
    holder = access.holder_for(request.cookies.get(access.COOKIE))
    if holder:
        return holder, "device"
    member = access.member_for_ip(client_ip(request) if ip is None else ip)
    return (member, "ip") if member else (None, None)


AUDIT = MonthlyLog("portal_audit", mode=0o600)  # 当月 state_dir/portal_audit.jsonl，往月归档到 state_dir/archive/


def append_audit(entries: list[dict]) -> None:
    AUDIT.append(entries)


def write_audit(request: Request, site: str, holder: str | None, action: str, detail: dict | None = None,
                ip: str | None = None) -> None:
    """ip：nginx auth_request 子请求的连接方是本机，真实 IP 由调用方从 X-Original-IP 传入。"""
    ip = client_ip(request) if ip is None else ip
    user, source = member_of(request, ip)
    append_audit([{"at": time.time(), "site": site, "holder": holder, "user": user, "user_source": source, "ip": ip,
                   "ua": request.headers.get("user-agent", "")[:200], "action": action, "detail": detail or {}}])


def read_audit(limit: int) -> list[dict]:
    """最新在前（回填的记录是后追加的，按时间取最新 limit 条）；只读到够数为止，不翻全部归档。"""
    items = AUDIT.newest(limit)
    for item in items:  # 旧记录没有 user：按 IP 推断
        if "user" not in item:
            item["user"] = access.member_for_ip(item.get("ip", ""))
            item["user_source"] = "ip" if item["user"] else None
    return items


def site_prefix(request: Request) -> str:
    """nginx 传来的站点前缀，如 /gallery/；子域名模式或直连后端时是 /。"""
    prefix = request.headers.get("x-forwarded-prefix", "/")
    return prefix if re.fullmatch(r"/(?:[a-z]+/)?", prefix) else "/"


def cookie_path(request: Request) -> str:
    return site_prefix(request).rstrip("/") or "/"


@dataclass
class Portal:
    site: str  # admin / gallery

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
        """当前访问人；不能进返回 None。"""
        ip = client_ip(request)
        if ip not in access.portal_ips():
            return None
        if self.site == "gallery":
            return access.ip_holder(ip)
        return access.holder_for(request.cookies.get(access.LOGIN_COOKIES["admin"]), kind="admin")

    def require(self, request: Request) -> str:
        """接口依赖：返回访问人。IP 不在白名单 403（记审计），后台未登录 401，CSRF 不对 403。"""
        if client_ip(request) not in access.portal_ips():
            self.audit(request, None, "forbidden", {"path": request.url.path})
            raise PortalError("IP_NOT_ALLOWED", "这个网络不在团队白名单里")
        holder = self.current(request)
        if holder is None:
            raise PortalError("PORTAL_UNAUTHORIZED", "请先登录")
        self.check_csrf(request)
        return holder

    def status_router(self) -> APIRouter:
        router = APIRouter(prefix=self.prefix)

        @router.get("/status")
        def status(request: Request):
            holder = self.current(request)
            return {"authorized": holder is not None, "holder": holder}

        return router


admin = Portal("admin")
gallery = Portal("gallery")
