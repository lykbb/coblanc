"""资产库。

save_image / load_image / search_assets 是唯一允许其他模块直接调用的函数。
demo 阶段图片存在本地 storage/，以后换对象存储只改这个文件。
物料（风格示例、婚纱、妆容、姿势骨架、背景、版式）登记在 templates/catalog.json，
妆造师和摄影师用 search_assets 来找。
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from app.common.config import settings
from app.state import Brief, WeddingState

TEMPLATES_DIR = Path(__file__).parent / "templates"
CATALOG = TEMPLATES_DIR / "catalog.json"
KINDS = {"upload", "candidate", "preview", "deliverable"}
ASSET_KINDS = {"style", "outfit", "makeup", "pose", "background", "layout"}
# 物料与版式比例；moments 是从主视觉裁出来的朋友圈图
LAYOUTS = {"invitation": "4:5", "welcome_poster": "2:3", "led_screen": "16:9", "moments": "1:1"}


def _ext(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    raise ValueError("只支持 jpg 和 png 图片")


def save_image(data: bytes, kind: str) -> str:
    """保存一张图片，返回可以访问的地址。kind：upload / candidate / preview / deliverable。"""
    if kind not in KINDS:
        raise ValueError(f"kind 只能是 {sorted(KINDS)}，收到 {kind!r}")
    folder = settings.storage_dir / kind
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex[:12]}.{_ext(data)}"
    (folder / name).write_bytes(data)
    return f"{settings.public_base_url}/files/{kind}/{name}"


def _path_from_url(url: str) -> Path:
    prefix = f"{settings.public_base_url}/files/"
    if not url.startswith(prefix):
        raise ValueError(f"不是资产库的地址：{url}")
    root = settings.storage_dir.resolve()
    path = (root / url[len(prefix):]).resolve()
    if root not in path.parents:
        raise ValueError(f"不是资产库的地址：{url}")
    return path


def load_image(url: str) -> bytes:
    """按地址读出图片内容，比如生图前读用户照片。"""
    return _path_from_url(url).read_bytes()


def search_assets(kind: str, tags: list[str] | None = None) -> list[dict]:
    """按种类和标签找物料。kind：style / outfit / makeup / pose / background / layout。

    tags 为空时返回这一类的全部物料；不为空时返回至少带一个标签的物料。
    每项含 asset_id、kind、name、tags、url；文件还没放进来的物料不会返回。
    """
    if kind not in ASSET_KINDS:
        raise ValueError(f"kind 只能是 {sorted(ASSET_KINDS)}，收到 {kind!r}")
    entries = json.loads(CATALOG.read_text(encoding="utf-8")) if CATALOG.is_file() else []
    wanted = set(tags or [])
    found = []
    for entry in entries:
        if entry["kind"] != kind or (wanted and not wanted & set(entry.get("tags", []))):
            continue
        if not (TEMPLATES_DIR / entry["file"]).is_file():
            continue
        found.append(
            {
                "asset_id": entry["asset_id"],
                "kind": entry["kind"],
                "name": entry.get("name", ""),
                "tags": entry.get("tags", []),
                "url": f"{settings.public_base_url}/templates/{entry['file']}",
            }
        )
    return found


def make_previews(state: WeddingState) -> dict:
    best = state.get("best_image_id")
    previews = []
    for candidate in state.get("candidates", []):
        # TODO(资产库)：给预览图加水印（可以用 Pillow），现在直接复制候选图
        url = save_image(load_image(candidate["url"]), "preview")
        previews.append({"image_id": candidate["image_id"], "url": url, "is_best": candidate["image_id"] == best})
    previews.sort(key=lambda item: not item["is_best"])
    return {"previews": previews}


def package(state: WeddingState) -> dict:
    candidates = state["candidates"]
    best = next(c for c in candidates if c["image_id"] == state["best_image_id"])
    data = load_image(best["url"])
    # 套图阶段交付全部 9 张；photo 保留为主视觉，兼容旧客户端和婚礼物料排版。
    stage = (state.get("generation") or {}).get("stage")
    ordered = [best, *[candidate for candidate in candidates if candidate["image_id"] != best["image_id"]]]
    if stage == "set":
        photos = [save_image(load_image(candidate["url"]), "deliverable") for candidate in ordered]
    else:
        photos = [save_image(data, "deliverable")]
    brief = Brief(**state.get("brief", {}))
    deliverables = {"photo": photos[0]}
    # 仅新套图流程暴露 photos 列表；旧工单保持原有 deliverables 键集合。
    if stage == "set":
        deliverables["photos"] = photos
    for key in [*brief.materials, "moments"]:
        if key in LAYOUTS:
            # TODO(资产库)：按 templates/layouts/ 的版式裁成 LAYOUTS[key] 的比例，排上名字、日期、地点，
            # 人脸和文字都在安全区内。现在直接复制高清图。
            deliverables[key] = save_image(data, "deliverable")
    _delete_originals_if_requested(state)
    return {"deliverables": deliverables}


def _delete_originals_if_requested(state: WeddingState) -> None:
    """按已确认的任务授权删除原始照片，忽略外部或已不存在的地址。"""

    consent = state.get("consent") or {}
    if not consent.get("confirmed") or not consent.get("delete_original"):
        return
    urls = (
        set(state.get("groom_photo_urls", []))
        | set(state.get("bride_photo_urls", []))
        | set(state.get("photo_urls", []))
    )
    for url in urls:
        try:
            path = _path_from_url(url)
            if path.is_file():
                path.unlink()
        except (OSError, ValueError):
            continue


def purge_expired() -> int:
    """删除超过保存天数的照片和成片，返回删除的文件数。服务启动时调用。"""
    if not settings.storage_dir.exists():
        return 0
    deadline = time.time() - settings.retention_days * 86400
    removed = 0
    for path in settings.storage_dir.rglob("*"):
        if path.is_file() and path.stat().st_mtime < deadline:
            path.unlink()
            removed += 1
    return removed
