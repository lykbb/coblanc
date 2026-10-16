"""团队参考图墙：按 01–07 风格（+ 00 待分类）收集好/坏参考图，供以后选风格和训练用。

- 存在 settings.reference_dir（默认 wedding-agent/reference_library/），和任务文件分开，不受 7 天清理影响。
- 每张图存三份：原图（去掉 EXIF 等元数据）、大图 webp（长边 ≤ 2048）、缩略图 webp（长边 ≤ 400）。
- 元数据在同目录 refs.sqlite。总容量上限 REFERENCE_CAP_GB（默认 15 GB）。
- 图墙站点（gallery/，gallery.BASE）专用：接口在 /api/gallery/refs，只给 GALLERY_MEMBERS（app/portal.py）；上传人取自登录人；改动和导出写审计。

导出元数据（在 wedding-agent 目录）：
  uv run python -m app.reference_wall export json > refs.json
  uv run python -m app.reference_wall export csv > refs.csv
"""

from __future__ import annotations

import csv
import io
import json
import re
import sqlite3
import sys
import threading
import time
import uuid
import zipfile
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, Response
from starlette.background import BackgroundTask
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field

from app.portal import gallery
from app.common.config import settings
from app.common.errors import ModuleError

STYLE_SKILL = Path(__file__).resolve().parent / "modules" / "intake" / "knowledge" / "wedding-style-data" / "SKILL.md"
MAX_FILE_BYTES = 10 * 1024 * 1024  # 和任务上传一致；nginx client_max_body_size 是 50m，前端一次传一张
LARGE_SIDE, THUMB_SIDE = 2048, 400
FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}
Image.MAX_IMAGE_PIXELS = 80_000_000
FIELDS = ("id", "style", "verdict", "source_url", "note", "uploader", "created_at", "original_name", "width", "height", "bytes")

router = APIRouter(prefix="/api/gallery/refs", dependencies=[Depends(gallery.require)])
_lock = threading.Lock()


def styles() -> list[dict]:
    """风格分类以风格数据 SKILL.md 的一级路由为准（01大理…07城堡），前面加 00 待分类。"""
    found = re.findall(r"\[(0[1-9])([^\]]+)\]\(levels/", STYLE_SKILL.read_text(encoding="utf-8"))
    return [{"id": "00", "name": "待分类"}] + [{"id": code, "name": name} for code, name in found]


def _style_ids() -> set[str]:
    return {item["id"] for item in styles()}


def _root() -> Path:
    root = settings.reference_dir
    (root / "images").mkdir(parents=True, exist_ok=True)
    return root


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(_root() / "refs.sqlite")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE IF NOT EXISTS refs (id TEXT PRIMARY KEY, style TEXT, verdict TEXT, source_url TEXT, note TEXT,"
        " uploader TEXT, created_at REAL, original_name TEXT, original_ext TEXT, width INT, height INT, bytes INT)"
    )
    return conn


def _error(code: str, message: str) -> ModuleError:
    return ModuleError(code, message)


def used_bytes() -> int:
    return sum(p.stat().st_size for p in (_root() / "images").iterdir() if p.is_file())


def _clean_tmp(max_age: float = 3600) -> None:
    """删掉中断下载留下的旧临时 zip。"""
    for path in (_root() / "tmp").glob("*.zip") if (_root() / "tmp").exists() else []:
        if time.time() - path.stat().st_mtime > max_age:
            path.unlink(missing_ok=True)


def _files(ref_id: str, ext: str) -> dict[str, Path]:
    folder = _root() / "images"
    return {"original": folder / f"{ref_id}.orig.{ext}", "large": folder / f"{ref_id}.webp", "thumb": folder / f"{ref_id}.thumb.webp"}


def _row(row: sqlite3.Row) -> dict:
    item = {key: row[key] for key in FIELDS}
    base = f"/api/gallery/refs/{row['id']}/image"
    item.update(thumb_url=f"{base}?size=thumb", large_url=f"{base}?size=large", original_url=f"{base}?size=original")
    return item


def _encode(image: Image.Image, fmt: str, **kwargs) -> bytes:
    out = io.BytesIO()
    image.save(out, fmt, **kwargs)  # 不传 exif/icc 以外的元数据，EXIF、GPS 一律丢掉
    return out.getvalue()


def _clean_text(value: str | None, limit: int) -> str:
    return (value or "").strip()[:limit]


def _check_url(url: str) -> str:
    url = _clean_text(url, 1000)
    if url and not re.match(r"^https?://", url, re.I):
        raise _error("FILE_INVALID", "来源链接要以 http:// 或 https:// 开头")
    return url


def add(data: bytes, filename: str, style: str, verdict: str, source_url: str, note: str, uploader: str) -> dict:
    if style not in _style_ids():
        raise _error("FILE_INVALID", "没有这个风格分类")
    if verdict not in ("good", "bad"):
        raise _error("FILE_INVALID", "请选择好图或坏图")
    if len(data) > MAX_FILE_BYTES:
        raise _error("FILE_INVALID", f"{filename} 超过 10 MB")
    try:
        image = Image.open(io.BytesIO(data))
        fmt = image.format
        image = ImageOps.exif_transpose(image)
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError):
        raise _error("FILE_INVALID", f"{filename} 不是能识别的图片（支持 jpg、png、webp）")
    if fmt not in FORMATS:
        raise _error("FILE_INVALID", f"{filename} 格式不支持（支持 jpg、png、webp）")
    icc = image.info.get("icc_profile")
    rgb = image.convert("RGBA" if image.mode in ("RGBA", "LA", "P") and fmt != "JPEG" else "RGB")
    original = _encode(rgb, fmt, **({"quality": 95} if fmt in ("JPEG", "WEBP") else {}), **({"icc_profile": icc} if icc else {}))
    large = rgb.copy()
    large.thumbnail((LARGE_SIDE, LARGE_SIDE), Image.LANCZOS)
    thumb = rgb.copy()
    thumb.thumbnail((THUMB_SIDE, THUMB_SIDE), Image.LANCZOS)
    blobs = {"original": original, "large": _encode(large, "WEBP", quality=88), "thumb": _encode(thumb, "WEBP", quality=80)}
    ref_id = uuid.uuid4().hex[:12]
    ext = FORMATS[fmt]
    with _lock:
        cap = int(settings.reference_cap_gb * 1024**3)
        if used_bytes() + sum(map(len, blobs.values())) > cap:
            raise _error("REFERENCE_FULL", f"参考图库已满（上限 {settings.reference_cap_gb:g} GB），请先删掉一些")
        for kind, path in _files(ref_id, ext).items():
            path.write_bytes(blobs[kind])
        with _db() as conn:
            conn.execute(
                "INSERT INTO refs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (ref_id, style, verdict, _check_url(source_url), _clean_text(note, 200), uploader, time.time(),
                 _clean_text(filename, 200), ext, rgb.width, rgb.height, sum(map(len, blobs.values()))),
            )
    return get(ref_id)


def get(ref_id: str) -> dict:
    with _db() as conn:
        row = conn.execute("SELECT * FROM refs WHERE id = ?", (ref_id,)).fetchone()
    if row is None:
        raise _error("REFERENCE_NOT_FOUND", "这张参考图不存在或已被删除")
    return _row(row)


def query(style: str | None = None, verdict: str | None = None) -> list[dict]:
    sql, args = "SELECT * FROM refs WHERE 1=1", []
    if style:
        sql, args = sql + " AND style = ?", args + [style]
    if verdict:
        sql, args = sql + " AND verdict = ?", args + [verdict]
    with _db() as conn:
        return [_row(row) for row in conn.execute(sql + " ORDER BY created_at DESC", args)]


def update(ref_id: str, changes: dict) -> dict:
    get(ref_id)
    if "style" in changes and changes["style"] not in _style_ids():
        raise _error("FILE_INVALID", "没有这个风格分类")
    if "source_url" in changes:
        changes["source_url"] = _check_url(changes["source_url"])
    if "note" in changes:
        changes["note"] = _clean_text(changes["note"], 200)
    if changes:
        with _db() as conn:
            conn.execute(f"UPDATE refs SET {', '.join(f'{k} = ?' for k in changes)} WHERE id = ?", [*changes.values(), ref_id])
    return get(ref_id)


def delete(ref_id: str) -> None:
    with _db() as conn:
        row = conn.execute("SELECT original_ext FROM refs WHERE id = ?", (ref_id,)).fetchone()
        if row is None:
            raise _error("REFERENCE_NOT_FOUND", "这张参考图不存在或已被删除")
        conn.execute("DELETE FROM refs WHERE id = ?", (ref_id,))
    for path in _files(ref_id, row["original_ext"]).values():
        path.unlink(missing_ok=True)


def export(fmt: str) -> str:
    items = [{key: item[key] for key in FIELDS} for item in query()]
    if fmt == "json":
        return json.dumps(items, ensure_ascii=False, indent=1)
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(items)
    return out.getvalue()


def _download_name(item: dict, ext: str) -> str:
    return f"{item['style']}-{item['verdict']}-{item['id']}.{ext}"


# ---- 接口 ----


@router.get("/styles")
def list_styles():
    return {"styles": styles(), "used_bytes": used_bytes(), "cap_bytes": int(settings.reference_cap_gb * 1024**3)}


@router.get("")
def list_refs(style: str | None = None, verdict: Literal["good", "bad"] | None = None):
    return {"items": query(style, verdict)}


@router.post("")
async def upload_refs(
    request: Request,
    holder: str = Depends(gallery.require),
    files: list[UploadFile] = File(...),
    style: str = Form("00"),
    verdict: Literal["good", "bad"] = Form(...),
    source_url: str = Form(""),
    note: str = Form(""),
):
    items = [add(await f.read(), f.filename or "图片", style, verdict, source_url, note, holder) for f in files]
    gallery.audit(request, holder, "refs_uploaded", {"ids": [i["id"] for i in items], "style": style, "verdict": verdict})
    return {"items": items}


class RefPatch(BaseModel):
    style: str | None = None
    verdict: Literal["good", "bad"] | None = None
    source_url: str | None = Field(None, max_length=1000)
    note: str | None = Field(None, max_length=200)


@router.patch("/{ref_id}")
def edit_ref(ref_id: str, body: RefPatch, request: Request, holder: str = Depends(gallery.require)):
    changes = body.model_dump(exclude_none=True)
    item = update(ref_id, changes)
    gallery.audit(request, holder, "ref_edited", {"id": ref_id, **changes})
    return item


@router.delete("/{ref_id}")
def delete_ref(ref_id: str, request: Request, holder: str = Depends(gallery.require)):
    delete(ref_id)
    gallery.audit(request, holder, "ref_deleted", {"id": ref_id})
    return {"deleted": ref_id}


@router.get("/export")
def export_refs(request: Request, format: Literal["csv", "json"] = "json", holder: str = Depends(gallery.require)):
    gallery.audit(request, holder, "refs_exported", {"format": format})
    media = "application/json" if format == "json" else "text/csv; charset=utf-8"
    return Response(export(format), media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="references.{format}"'})


@router.get("/zip")
def zip_refs(request: Request, style: str | None = None, verdict: Literal["good", "bad"] | None = None,
             holder: str = Depends(gallery.require)):
    _clean_tmp()
    gallery.audit(request, holder, "refs_zipped", {"style": style, "verdict": verdict})
    items = query(style, verdict)
    if not items:
        raise _error("REFERENCE_NOT_FOUND", "当前筛选下没有图片")
    # 写到磁盘临时文件再发，不在内存里组装（库可能有几十 GB 级别）；发完由后台任务删掉
    tmp_dir = _root() / "tmp"
    tmp_dir.mkdir(exist_ok=True)
    path = tmp_dir / f"{uuid.uuid4().hex}.zip"
    try:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as archive:  # webp 已压缩，不再压
            for item in items:
                archive.write(_files(item["id"], "")["large"], _download_name(item, "webp"))
            archive.writestr("references.json", json.dumps(items, ensure_ascii=False, indent=1))
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    name = f"references-{style or 'all'}-{verdict or 'all'}.zip"
    return FileResponse(path, media_type="application/zip", filename=name,
                        background=BackgroundTask(path.unlink, missing_ok=True))


@router.get("/{ref_id}/image")
def ref_image(ref_id: str, size: Literal["thumb", "large", "original"] = "large", download: bool = False):
    item = get(ref_id)
    with _db() as conn:
        ext = conn.execute("SELECT original_ext FROM refs WHERE id = ?", (ref_id,)).fetchone()["original_ext"]
    path = _files(ref_id, ext)[size]
    name = _download_name(item, ext if size == "original" else "webp")
    return FileResponse(path, headers={"Cache-Control": "private, max-age=31536000, immutable"},
                        filename=name if download else None)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "export" and sys.argv[2] in ("csv", "json"):
        sys.stdout.write(export(sys.argv[2]))
    else:
        print(__doc__)
        sys.exit(1)
