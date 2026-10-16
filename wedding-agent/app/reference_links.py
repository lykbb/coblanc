"""图墙 00 来源链接：链接卡片（标题、域名、标签、预览图），只有管理员（ADMIN_HOLDERS，即 lyk，按 IP 对应的成员识别）能增删改，其他人只读。

预览图：服务器端抓网页的 og:image / twitter:image / 第一张图，存成本地缩略图；抓不到时可手动上传。
抓取防 SSRF：只允许 http/https 的 80/443 端口；每一跳（含重定向，最多 3 次）都先解析域名，所有地址必须是公网地址，
然后直接连接已校验的 IP（防 DNS 重绑定）；超时 6 秒，网页最多读 1 MB，图片最多 8 MB。
"""

from __future__ import annotations

import http.client
import io
import ipaddress
import json
import re
import socket
import ssl
import time
import uuid
from html import unescape
from urllib.parse import urljoin, urlsplit

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field

from app.common.config import settings
from app.portal import gallery
from app.reference_wall import _db, _error, _root, clean_tags, matches

router = APIRouter(prefix="/api/gallery/links", dependencies=[Depends(gallery.require)])
TIMEOUT, PAGE_LIMIT, IMAGE_LIMIT, MAX_REDIRECTS, PREVIEW_SIDE = 6, 1024 * 1024, 8 * 1024 * 1024, 3, 640
UA = "Mozilla/5.0 (compatible; COBLANC-preview/1.0)"


# ---- 安全抓取 ----


def _public_ips(host: str, port: int) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError):
        raise _error("LINK_FETCH_FAILED", "域名解析失败")
    ips = []
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if getattr(ip, "ipv4_mapped", None):
            ip = ip.ipv4_mapped
        if not ip.is_global or ip.is_multicast or ip.is_reserved or ip.is_private or ip.is_loopback or ip.is_link_local:
            raise _error("LINK_FETCH_FAILED", "不允许访问内网地址")
        ips.append(str(ip))
    if not ips:
        raise _error("LINK_FETCH_FAILED", "域名解析失败")
    return ips


class _PinnedHTTP(http.client.HTTPConnection):
    def __init__(self, host, ip, port, **kw):
        super().__init__(host, port, timeout=TIMEOUT, **kw)
        self._ip = ip

    def connect(self):
        self.sock = socket.create_connection((self._ip, self.port), self.timeout)


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, ip, port):
        super().__init__(host, port, timeout=TIMEOUT, context=ssl.create_default_context())
        self._ip = ip

    def connect(self):
        sock = socket.create_connection((self._ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def safe_get(url: str, limit: int, accept: str = "*/*") -> tuple[bytes, str, str]:
    """返回 (内容, Content-Type, 最终地址)。任何不安全情况抛 LINK_FETCH_FAILED。"""
    deadline = time.monotonic() + TIMEOUT * 2
    for _ in range(MAX_REDIRECTS + 1):
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
            raise _error("LINK_FETCH_FAILED", "链接不对")
        port = parts.port or (443 if parts.scheme == "https" else 80)
        if port not in (80, 443):
            raise _error("LINK_FETCH_FAILED", "只支持 80/443 端口")
        ip = _public_ips(parts.hostname, port)[0]
        conn = (_PinnedHTTPS if parts.scheme == "https" else _PinnedHTTP)(parts.hostname, ip, port)
        try:
            path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
            conn.request("GET", path, headers={"Host": parts.netloc, "User-Agent": UA, "Accept": accept, "Accept-Encoding": "identity"})
            response = conn.getresponse()
            if response.status in (301, 302, 303, 307, 308) and response.getheader("Location"):
                url = urljoin(url, response.getheader("Location"))
                continue
            if response.status != 200:
                raise _error("LINK_FETCH_FAILED", f"网页返回 {response.status}")
            data = b""
            while len(data) <= limit:
                if time.monotonic() > deadline:
                    raise _error("LINK_FETCH_FAILED", "抓取超时")
                chunk = response.read(65536)
                if not chunk:
                    break
                data += chunk
            if len(data) > limit:
                raise _error("LINK_FETCH_FAILED", "内容太大")
            return data, response.getheader("Content-Type", ""), url
        except (OSError, http.client.HTTPException, ssl.SSLError):
            raise _error("LINK_FETCH_FAILED", "抓取失败")
        finally:
            conn.close()
    raise _error("LINK_FETCH_FAILED", "重定向太多")


_META = re.compile(r"<meta\b[^>]*>", re.I)
_ATTR = re.compile(r'([a-zA-Z:-]+)\s*=\s*("([^"]*)"|\'([^\']*)\'|([^\s>]+))')
_IMG = re.compile(r"<img\b[^>]*?\bsrc\s*=\s*[\"']([^\"']+)[\"']", re.I)


def find_image(html: str, base: str) -> list[str]:
    found = []
    for tag in _META.findall(html):
        attrs = {m.group(1).lower(): (m.group(3) or m.group(4) or m.group(5) or "") for m in _ATTR.finditer(tag)}
        key = (attrs.get("property") or attrs.get("name") or "").lower()
        if key in ("og:image", "og:image:url", "og:image:secure_url", "twitter:image", "twitter:image:src") and attrs.get("content"):
            found.append(unescape(attrs["content"]))
    found += [unescape(src) for src in _IMG.findall(html)[:8] if not src.startswith("data:")]
    return [urljoin(base, u) for u in dict.fromkeys(found)]


def _thumb(data: bytes) -> bytes:
    try:
        image = Image.open(io.BytesIO(data))
        image = ImageOps.exif_transpose(image).convert("RGB")
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError):
        raise _error("FILE_INVALID", "不是能识别的图片")
    if min(image.size) < 80:
        raise _error("FILE_INVALID", "图片太小")
    image.thumbnail((PREVIEW_SIDE, PREVIEW_SIDE * 2), Image.LANCZOS)
    out = io.BytesIO()
    image.save(out, "WEBP", quality=82)
    return out.getvalue()


def fetch_preview(url: str) -> bytes | None:
    """抓预览图；任何失败都返回 None（可以手动上传）。"""
    try:
        page, ctype, final = safe_get(url, PAGE_LIMIT, "text/html,image/*")
        if ctype.startswith("image/"):
            return _thumb(page)
        for candidate in find_image(page.decode("utf-8", errors="replace"), final)[:4]:
            try:
                data, _, _ = safe_get(candidate, IMAGE_LIMIT, "image/*")
                return _thumb(data)
            except Exception:
                continue
    except Exception:
        return None
    return None


# ---- 存储 ----


def _folder():
    folder = _root() / "links"
    folder.mkdir(exist_ok=True)
    return folder


def _row(row) -> dict:
    return {"id": row["id"], "title": row["title"], "url": row["url"], "domain": row["domain"], "tags": json.loads(row["tags"] or "[]"),
            "uploader": row["uploader"], "created_at": row["created_at"],
            "preview_url": f"links/{row['id']}/preview?v={row['preview']}" if row["preview"] else None}


def get(link_id: str) -> dict:
    with _db() as conn:
        row = conn.execute("SELECT * FROM links WHERE id = ?", (link_id,)).fetchone()
    if row is None:
        raise _error("REFERENCE_NOT_FOUND", "这个链接不存在或已被删除")
    return _row(row)


def _url(url: str) -> tuple[str, str]:
    url = (url or "").strip()[:1000]
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise _error("FILE_INVALID", "链接要以 http:// 或 https:// 开头")
    return url, parts.hostname.removeprefix("www.")


def _title(title: str) -> str:
    title = (title or "").strip()[:60]
    if not title:
        raise _error("FILE_INVALID", "请填标题")
    return title


def _save_preview(link_id: str, data: bytes) -> None:
    (_folder() / f"{link_id}.webp").write_bytes(data)
    with _db() as conn:
        conn.execute("UPDATE links SET preview = ? WHERE id = ?", (uuid.uuid4().hex[:6], link_id))


def _require_admin(holder: str) -> None:
    if holder not in settings.admin_holders:
        raise _error("PORTAL_FORBIDDEN", "只有管理员能改来源链接")


# ---- 接口 ----


class LinkBody(BaseModel):
    title: str = Field(..., max_length=60)
    url: str = Field(..., max_length=1000)
    tags: list[str] = Field(default_factory=list, max_length=12)


class LinkPatch(BaseModel):
    title: str | None = Field(None, max_length=60)
    url: str | None = Field(None, max_length=1000)
    tags: list[str] | None = Field(None, max_length=12)


@router.get("")
def list_links(q: str = "", tag: str | None = None):
    with _db() as conn:
        items = [_row(r) for r in conn.execute("SELECT * FROM links ORDER BY created_at DESC")]
    return {"items": [i for i in items if matches(i, q[:100].strip(), tag, ("title", "uploader", "domain"))]}


@router.post("")
def add_link(body: LinkBody, request: Request, holder: str = Depends(gallery.require)):
    _require_admin(holder)
    url, domain = _url(body.url)
    link_id = uuid.uuid4().hex[:12]
    with _db() as conn:
        conn.execute("INSERT INTO links VALUES (?,?,?,?,?,?,?,?)",
                     (link_id, _title(body.title), url, domain, json.dumps(clean_tags(body.tags), ensure_ascii=False), "", holder, time.time()))
    preview = fetch_preview(url)
    if preview:
        _save_preview(link_id, preview)
    gallery.audit(request, holder, "link_added", {"id": link_id, "domain": domain, "preview": bool(preview)})
    return get(link_id)


@router.patch("/{link_id}")
def edit_link(link_id: str, body: LinkPatch, request: Request, holder: str = Depends(gallery.require)):
    _require_admin(holder)
    get(link_id)
    changes: dict = {}
    if body.title is not None:
        changes["title"] = _title(body.title)
    if body.url is not None:
        changes["url"], changes["domain"] = _url(body.url)
    if body.tags is not None:
        changes["tags"] = json.dumps(clean_tags(body.tags), ensure_ascii=False)
    if changes:
        with _db() as conn:
            conn.execute(f"UPDATE links SET {', '.join(f'{k} = ?' for k in changes)} WHERE id = ?", [*changes.values(), link_id])
    if "url" in changes:
        preview = fetch_preview(changes["url"])
        if preview:
            _save_preview(link_id, preview)
    gallery.audit(request, holder, "link_edited", {"id": link_id, **{k: v for k, v in changes.items() if k != "tags"}})
    return get(link_id)


@router.post("/{link_id}/refetch")
def refetch(link_id: str, request: Request, holder: str = Depends(gallery.require)):
    _require_admin(holder)
    preview = fetch_preview(get(link_id)["url"])
    if not preview:
        raise _error("LINK_FETCH_FAILED", "抓不到预览图，可以手动上传")
    _save_preview(link_id, preview)
    return get(link_id)


@router.post("/{link_id}/preview")
async def upload_preview(link_id: str, request: Request, file: UploadFile = File(...), holder: str = Depends(gallery.require)):
    _require_admin(holder)
    get(link_id)
    data = await file.read(IMAGE_LIMIT + 1)
    if len(data) > IMAGE_LIMIT:
        raise _error("FILE_INVALID", "图片太大")
    _save_preview(link_id, _thumb(data))
    gallery.audit(request, holder, "link_preview_uploaded", {"id": link_id})
    return get(link_id)


@router.get("/{link_id}/preview")
def preview(link_id: str):
    get(link_id)
    path = _folder() / f"{link_id}.webp"
    if not path.exists():
        raise _error("REFERENCE_NOT_FOUND", "没有预览图")
    return FileResponse(path, media_type="image/webp", headers={"Cache-Control": "private, max-age=31536000, immutable"})


@router.delete("/{link_id}")
def delete_link(link_id: str, request: Request, holder: str = Depends(gallery.require)):
    _require_admin(holder)
    get(link_id)
    with _db() as conn:
        conn.execute("DELETE FROM links WHERE id = ?", (link_id,))
    (_folder() / f"{link_id}.webp").unlink(missing_ok=True)
    gallery.audit(request, holder, "link_deleted", {"id": link_id})
    return {"deleted": link_id}
