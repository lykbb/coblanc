"""账号密码登录页（前台 front、后台 admin），取代 nginx 的浏览器弹窗认证；图墙不登录，只认 IP 白名单。

- 账号密码就用服务器上原来的 htpasswd（settings.htpasswd_dir：.htpasswd 前台、.htpasswd-admin 后台；apr1 / bcrypt），
  改密码照旧：sudo htpasswd /etc/nginx/.htpasswd-admin 用户名。后端服务进程要能读这两个文件（deploy.sh 给服务加 www-data 组）。
- 登录成功开会话（app/access.py 设备表，kind=front/admin），Cookie HttpOnly、SameSite=Strict、Path 限定站点前缀；后台另有空闲超时。
- nginx 每个请求 auth_request 问 /internal/gate/<站点>：204 放行；401 → 跳登录页；403（后台/图墙 IP 不在白名单）直接拒绝。
- 防暴力破解：同一 IP 10 分钟错 10 次后端锁定（429）；nginx limit_req；fail2ban 按 access.log 里登录 POST 的 401 计数封 IP。
"""

from __future__ import annotations

import hashlib
import hmac
import html
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from urllib.parse import urlsplit

from app import access, audit_feed, portal
from app.common.config import settings

SITES = {  # 站点：(htpasswd 文件名, 品牌副标题)
    "front": (".htpasswd", ""),
    "admin": (".htpasswd-admin", "ADMIN"),
}
router = APIRouter(include_in_schema=False)

# ---- htpasswd 校验 ----

_APR_CHARS = "./0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def _apr1(password: bytes, salt: bytes, magic: bytes = b"$apr1$") -> str:
    """Apache apr1（MD5-crypt）。"""
    final = hashlib.md5(password + salt + password).digest()
    ctx = password + magic + salt
    for i in range(len(password), 0, -16):
        ctx += final[: min(16, i)]
    i = len(password)
    while i:
        ctx += b"\x00" if i & 1 else password[:1]
        i >>= 1
    final = hashlib.md5(ctx).digest()
    for i in range(1000):
        c = (password if i & 1 else final) + (salt if i % 3 else b"") + (password if i % 7 else b"") + (final if i & 1 else password)
        final = hashlib.md5(c).digest()
    out = ""
    for a, b, c in ((0, 6, 12), (1, 7, 13), (2, 8, 14), (3, 9, 15), (4, 10, 5)):
        v = (final[a] << 16) | (final[b] << 8) | final[c]
        for _ in range(4):
            out += _APR_CHARS[v & 0x3F]
            v >>= 6
    v = final[11]
    for _ in range(2):
        out += _APR_CHARS[v & 0x3F]
        v >>= 6
    return magic.decode() + salt.decode() + "$" + out


def check_password(site: str, username: str, password: str) -> bool:
    path: Path = settings.htpasswd_dir / SITES[site][0]
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    for line in lines:
        user, _, stored = line.strip().partition(":")
        if not user or not hmac.compare_digest(user.encode(), username.encode()):
            continue
        if stored.startswith("$apr1$"):
            salt = stored[6:].split("$", 1)[0].encode()
            return hmac.compare_digest(_apr1(password.encode(), salt), stored)
        if stored.startswith(("$2y$", "$2b$", "$2a$")):
            try:
                import bcrypt
            except ImportError:
                return False
            return bcrypt.checkpw(password.encode(), stored.replace("$2y$", "$2b$", 1).encode())
        return False
    return False


# ---- 页面 ----

PAGE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>登录 · COBLANC</title>
<style>
:root{--bg:#f3f2f8;--panel:#fff;--ink:#26232e;--muted:#6b6675;--line:#ebe8f1;--peach-ink:#a9533c;--peach-line:#f3cdbe;--coral:#d9775e;
--grad-btn:linear-gradient(90deg,#f5bc9e 0%,#ef9c88 100%);--btn-ink:#4a2418;--brand:'Didot','Bodoni 72',Georgia,'Times New Roman',serif;
--sans:-apple-system,BlinkMacSystemFont,'PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif}
*{box-sizing:border-box}html,body{height:100%;margin:0}
body{display:grid;place-items:center;background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:14px}
form{width:min(320px,86vw);display:flex;flex-direction:column;gap:14px}
.brand{font-family:var(--brand);font-size:26px;letter-spacing:.32em;text-align:center;margin-bottom:18px}
.brand span{display:block;margin-top:8px;font-family:var(--sans);font-size:10px;letter-spacing:.3em;color:var(--muted)}
input{height:46px;border:1px solid var(--line);border-radius:12px;background:var(--panel);padding:0 16px;font:inherit;font-size:15px;color:inherit;outline:none;transition:border-color .2s}
input:focus{border-color:var(--peach-line)}input::placeholder{color:var(--muted)}
button{height:44px;border:0;border-radius:12px;background:var(--grad-btn);color:var(--btn-ink);font:inherit;cursor:pointer;letter-spacing:.2em}
button:focus-visible,input:focus-visible{outline:2px solid var(--coral);outline-offset:2px}
.err{min-height:18px;margin:0;text-align:center;color:var(--peach-ink);font-size:12px}
</style></head><body>
<form method="post" action="{action}" autocomplete="on">
<div class="brand">COBLANC{sub}</div>
<input name="username" placeholder="账号" autocomplete="username" autocapitalize="off" spellcheck="false" maxlength="64" required autofocus value="{username}">
<input name="password" type="password" placeholder="密码" autocomplete="current-password" maxlength="256" required>
<input type="hidden" name="next" value="{next}">
<button type="submit">登录</button>
<p class="err" role="alert">{error}</p>
</form></body></html>"""


def _prefix(request: Request) -> str:
    return portal.site_prefix(request)


def _safe_next(request: Request, value: str) -> str:
    prefix = _prefix(request)
    ok = value.startswith(prefix) and not value.startswith("//") and "\\" not in value and not value.startswith(prefix + "login")
    return value if ok else prefix


def _page(request: Request, site: str, status: int = 200, error: str = "", username: str = "", next_url: str = "") -> HTMLResponse:
    sub = SITES[site][1]
    values = {"action": html.escape(_prefix(request) + "login"), "sub": f"<span>{sub}</span>" if sub else "",
              "username": html.escape(username), "next": html.escape(_safe_next(request, next_url)), "error": html.escape(error)}
    body = PAGE
    for key, value in values.items():
        body = body.replace("{" + key + "}", value)
    return HTMLResponse(body, status_code=status, headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow"})


def _same_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    return not origin or urlsplit(origin).netloc == request.headers.get("host")


def _check_site(site: str) -> None:
    if site not in SITES:
        raise HTTPException(404)


@router.get("/auth/{site}/login")
def login_page(site: str, request: Request, next: str = ""):
    _check_site(site)
    return _page(request, site, next_url=next)


@router.post("/auth/{site}/login")
def login(site: str, request: Request, username: str = Form("", max_length=64), password: str = Form("", max_length=256),
          next: str = Form("", max_length=512)):
    _check_site(site)
    ip = portal.client_ip(request)
    if not _same_origin(request):
        return _page(request, site, 403, "请求来源不对，请刷新页面再试")
    if access.too_many_fails(ip):
        portal.write_audit(request, site, None, "login_locked")
        return _page(request, site, 429, "尝试次数过多，请稍后再试", username, next)
    if not check_password(site, username, password):
        access.record_fail(ip)
        portal.write_audit(request, site, None, "login_failed", {"username": username[:64]})
        return _page(request, site, 401, "账号或密码不对", username, next)
    token = access.start_session(username, site, ip, request.headers.get("user-agent", ""))
    response = RedirectResponse(_safe_next(request, next), status_code=303)
    https = settings.cookie_secure or request.headers.get("x-forwarded-proto") == "https"
    response.set_cookie(access.LOGIN_COOKIES[site], token, max_age=settings.portal_max_days * 86400,
                        httponly=True, samesite="strict", secure=https, path=portal.cookie_path(request))
    portal.write_audit(request, site, username, "login")
    return response


@router.post("/auth/{site}/logout")
def logout(site: str, request: Request):
    _check_site(site)
    if not _same_origin(request):
        return Response(status_code=403)
    cookie = access.LOGIN_COOKIES[site]
    holder = access.holder_for(request.cookies.get(cookie), kind=site)
    access.revoke_token(request.cookies.get(cookie))
    response = RedirectResponse(_prefix(request) + "login", status_code=303)
    response.delete_cookie(cookie, path=portal.cookie_path(request))
    if holder:
        portal.write_audit(request, site, holder, "logout")
    return response


@router.get("/internal/gate/{name}")
def gate(name: str, request: Request):
    """nginx auth_request（只在服务器内部调用，外面访问不到 /internal）：204 放行，401 去登录，403 拒绝。
    team：图墙和后台登录页，只看 IP；admin：IP + 后台会话；front：前台会话。结果交给 audit_feed 记访问 / 拒绝。"""
    ip = request.headers.get("x-original-ip", "")
    holder = None
    if name in ("team", "admin") and ip not in access.portal_ips():
        status = 403
    elif name in ("admin", "front"):
        holder = access.holder_for(request.cookies.get(access.LOGIN_COOKIES[name]), kind=name)
        status = 204 if holder else 401
    elif name == "team":
        holder = access.ip_holder(ip)
        holder, status = (None if holder == ip else holder), 204
    else:
        return Response(status_code=404)
    audit_feed.on_gate(request, name, ip, status, holder)
    return Response(status_code=status)


@router.get("/internal/team-ip/{ip}")
def team_ip(ip: str):
    """fail2ban ignorecommand（只在服务器本机调用）：团队白名单 IP 返回 204（不封），否则 404。"""
    return Response(status_code=204 if ip in access.portal_ips() else 404)
