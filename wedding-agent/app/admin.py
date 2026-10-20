"""后台管理接口 /api/admin/*（独立站点 admin/，/abordadmin/ 或 abordadmin.BASE；只给 ADMIN_HOLDERS，默认 lyk）：邀请码、任务（只读）、审计。

IP 白名单、CSRF、审计见 app/portal.py；账号密码登录见 app/login.py。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app import access, audit_feed, reference_wall
from app.common.config import settings
from app.common.log import get_logger
from app.common.progress import store
from app.portal import PortalError, admin, read_audit

log = get_logger("admin")
status_router = admin.status_router()
router = APIRouter(prefix="/api/admin", dependencies=[Depends(admin.require)])


# ---- 邀请码 ----


@router.get("/access")
def access_overview():
    return access.overview() | {"admins": settings.admin_holders, "members": settings.gallery_members,
                                "system": sorted(access.SYSTEM_HOLDERS)}


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


def _rel(url) -> str | None:
    """用户站图片绝对地址 → 相对路径 /files/...（后台站点自己代理）；不是本站图片返回 None。"""
    base = settings.public_base_url
    return url[len(base):] if isinstance(url, str) and url.startswith(base + "/files/") else None


def _relative(value) -> list[str]:
    """从字符串 / 列表 / 字典里按顺序取出所有本站图片地址（去重）。"""
    found: list[str] = []
    def walk(item):
        if isinstance(item, str):
            url = _rel(item)
            if url and url not in found:
                found.append(url)
        elif isinstance(item, dict):
            for v in item.values():
                walk(v)
        elif isinstance(item, list):
            for v in item:
                walk(v)
    walk(value)
    return found


@router.get("/tasks")
def tasks(limit: int = 100):
    return {"items": [
        {"task_id": task_id, "updated_at": updated, "status": info.status, "step": info.step,
         "operator": info.operator, "operator_source": info.operator_source,
         "step_text": info.step_text, "error": info.error, "user_redo_count": info.user_redo_count}
        for task_id, updated, info in store.recent(max(1, min(limit, 500)))
    ]}


# 任务详情里按顺序展示的工单字段：(字段, 标题)；其余字段不展示
DETAIL_FIELDS = [
    ("description", "用户描述"), ("consent", "授权"), ("brief", "小囍·需求单"),
    ("look", "妆造师·造型方案"), ("shot", "摄影师·镜头方案"), ("shots", "摄影师·分镜表"),
    ("identity", "小囍·身份照顺序"), ("references", "小囍·参考图"),
    ("prompt", "小囍·最终提示词（给生图 agent）"), ("shot_prompts", "小囍·分镜提示词"),
    ("generation", "生图·结果"), ("candidates", "生图·候选图"),
    ("scores", "修图师·质检评分"), ("passed", "修图师·是否合格"), ("best_image_id", "修图师·选中"),
    ("quality_note", "修图师·说明"), ("retouch_plan", "修图师·修图方案"),
    ("user_feedback", "用户重做反馈"), ("retry_count", "重试次数"), ("sample_only", "只要样片"),
    ("previews", "预览"), ("deliverables", "交付"), ("message", "小囍·揭幕寄语"),
]


def _local(value):
    """脱敏，并把用户站的图片绝对地址改成相对路径（后台站点自己代理 /files）。"""
    from app.common.trace import mask

    base = settings.public_base_url + "/files/"
    def walk(item):
        if isinstance(item, str):
            return item[len(base) - len("/files/"):] if item.startswith(base) else item
        if isinstance(item, dict):
            return {k: walk(v) for k, v in item.items()}
        if isinstance(item, list):
            return [walk(v) for v in item]
        return item
    return walk(mask(value))


def _uploads(values: dict) -> list[str]:
    return _relative([values.get("photo_urls"), values.get("groom_photo_urls"), values.get("bride_photo_urls")])


def _questions(task_id: str) -> dict:
    """问过用户的问题：从检查点历史里收集（工单里只留当前这轮）。"""
    from app import runner

    found: dict = {}
    try:
        for snapshot in runner.graph.get_state_history(runner._config(task_id), limit=400):
            for question in snapshot.values.get("questions") or []:
                found.setdefault(question.get("question_id"), question)
    except Exception as error:
        log.warning("读任务 %s 的问答历史失败：%s", task_id, type(error).__name__)
    return found


def _answer_label(question: dict | None, value):
    """把选项值换成用户看到的中文标题；文字题或找不到选项时原样返回。"""
    labels = {o.get("value"): o.get("label") for o in (question or {}).get("options") or []}
    if isinstance(value, list):
        return "、".join(str(labels.get(v, v)) for v in value)
    return labels.get(value, value)


@router.get("/tasks/{task_id}")
def task_detail(task_id: str):
    from app import admin_ops, runner
    from app.common import trace, usage

    info = store.peek(task_id)
    if info is None:
        raise PortalError("TASK_NOT_FOUND", "找不到这个任务")
    values = runner.values(task_id)
    questions = _questions(task_id)
    chat = [{"asker": a.get("asker"), "round": a.get("round"), "question": (questions.get(a.get("question_id")) or {}).get("title"),
             "question_id": a.get("question_id"), "answer": a.get("value"),
             "answer_label": _answer_label(questions.get(a.get("question_id")), a.get("value")), "skipped": a.get("skipped")}
            for a in values.get("answers") or []]
    entries = usage.read(task_id=task_id)
    summary = admin_ops.summarize(entries)
    return {
        "task_id": task_id, "status": info.status, "step": info.step, "step_text": info.step_text, "error": info.error,
        "operator": info.operator, "operator_source": info.operator_source, "user_redo_count": info.user_redo_count,
        "generation": values.get("generation"),
        "images": {
            "photos": _uploads(values),
            "candidates": _relative(values.get("candidates")),
            "previews": _relative(values.get("previews")),
            "deliverables": _relative(values.get("deliverables")),
        },
        "chat": _local(chat),
        "pending_questions": _local(values.get("questions") or []),
        "fields": [{"key": key, "label": label, "value": _local(values[key])} for key, label in DETAIL_FIELDS
                   if values.get(key) not in (None, "", [], {})],
        "trace": [{**_local(item), "step_label": usage.step_label(item.get("step"))} for item in trace.read(task_id)],
        "usage": {
            "total": summary["total"],
            "steps": [{"step": k, "label": usage.step_label(k), **v} for k, v in summary["steps"].items()],
            "step_models": [{"step": s, "label": usage.step_label(s), "provider": p, "model": m, "kind": k, **v}
                            for (s, p, m, k), v in summary["step_models"].items()],
            "records": [{**e, "label": usage.step_label(e.get("step")), "cost": usage.cost(e)} for e in entries],
        },
    }


# ---- 生成记录（只读）：按 操作人 → 任务 → 分类 浏览所有产出 ----

PROMPT_FIELDS = [("brief", "小囍·需求单"), ("look", "妆造师·造型方案"), ("shot", "摄影师·镜头方案"),
                 ("shots", "摄影师·分镜表"), ("prompt", "小囍·最终提示词（给生图 agent）"),
                 ("shot_prompts", "小囍·分镜提示词"), ("message", "小囍·揭幕寄语")]
REVIEW_FIELDS = [("passed", "是否合格"), ("best_image_id", "选中"), ("quality_note", "说明"), ("retouch_plan", "修图方案")]


def _text(value) -> str:
    """方案字段转成好读的文字：有 text 就用 text；列表逐项；其余缩进 JSON。"""
    import json

    if isinstance(value, str):
        return value
    if isinstance(value, dict) and isinstance(value.get("text"), str):
        rest = {k: v for k, v in value.items() if k != "text" and v not in (None, "", [], {})}
        return value["text"] + ("\n\n" + json.dumps(rest, ensure_ascii=False, indent=2) if rest else "")
    if isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
        return "\n\n".join(f"#{v.get('slot', i)} " + (v.get("prompt") or v.get("text") or json.dumps(v, ensure_ascii=False))
                            for i, v in enumerate(value))
    return json.dumps(value, ensure_ascii=False, indent=2)


def _outputs(task_id: str, values: dict) -> dict:
    """一个任务的全部产出。每张候选图尽量配上产生它的提示词：过程记录里有就用（上线后的任务，含各轮），
    否则按当前一轮的位置 = 镜头号取分镜提示词（旧任务只知道当前一轮）。"""
    from app.common import trace

    by_url: dict[str, dict] = {}
    for event in trace.read(task_id):
        if event.get("kind") == "candidates":
            for item in event.get("items") or []:
                url = _rel(item.get("url"))
                if url:
                    by_url[url] = {"prompt": item.get("prompt"), "slot": item.get("slot"), "stage": event.get("stage"),
                                   "at": event.get("at"), "source": "过程记录"}
    slots = {item.get("slot"): item.get("prompt") for item in values.get("shot_prompts") or []}
    stage = (values.get("generation") or {}).get("stage")
    scores = {s.get("image_id"): s for s in values.get("scores") or [] if isinstance(s, dict)}
    best = values.get("best_image_id")
    candidates, by_id = [], {}
    for slot, item in enumerate(values.get("candidates") or []):
        url = _rel(item.get("url"))
        if not url:
            continue
        known = by_url.pop(url, None) or {"prompt": slots.get(slot, values.get("prompt")), "slot": slot, "stage": stage,
                                          "source": "当前一轮（按镜头号）"}
        entry = {"url": url, "image_id": item.get("image_id"), "seed": item.get("seed"), **known,
                 "score": _local(scores.get(item.get("image_id"))), "best": item.get("image_id") == best, "current": True}
        candidates.append(entry)
        by_id[item.get("image_id")] = entry
    candidates += [{"url": url, **info, "current": False} for url, info in sorted(by_url.items(), key=lambda x: x[1].get("at") or 0)]
    for entry in candidates:
        entry["prompt"] = _local(entry.get("prompt"))
    previews = [{"url": _rel(p.get("url")), "label": "预览" + (" · 选中" if p.get("is_best") else ""),
                 "prompt": (by_id.get(p.get("image_id")) or {}).get("prompt")}
                for p in values.get("previews") or [] if _rel(p.get("url"))]
    deliverables = []
    delivered = values.get("deliverables") or {}
    ordered = [by_id.get(best)] + [c for c in candidates if c.get("current") and c.get("image_id") != best]
    for key, value in delivered.items():
        urls = value if isinstance(value, list) else [value]
        for index, url in enumerate(urls):
            url = _rel(url)
            if not url:
                continue
            source = ordered[index] if key == "photos" and index < len(ordered) else by_id.get(best)
            deliverables.append({"url": url, "label": key if len(urls) == 1 else f"{key} #{index + 1}",
                                 "prompt": (source or {}).get("prompt")})
    prompts = [{"label": label, "text": _local(_text(values[key]))} for key, label in PROMPT_FIELDS
               if values.get(key) not in (None, "", [], {})]
    review = [{"label": f"质检 · {s.get('image_id')}", "text": _text(_local(s))} for s in scores.values()]
    review += [{"label": label, "text": _text(_local(values[key]))} for key, label in REVIEW_FIELDS
               if values.get(key) not in (None, "", [], {})]
    return {"uploads": _uploads(values), "candidates": candidates, "previews": previews,
            "deliverables": deliverables, "prompts": prompts, "review": review}


@router.get("/outputs")
def outputs(limit: int = 300):
    from app import runner

    items = []
    for task_id, updated, info in store.recent(max(1, min(limit, 1000))):
        try:
            values = runner.values(task_id)
        except Exception:
            values = {}
        uploads = _uploads(values)
        candidates = _relative(values.get("candidates"))
        delivered = _relative(values.get("deliverables"))
        items.append({"task_id": task_id, "updated_at": updated, "status": info.status, "step_text": info.step_text,
                      "operator": info.operator, "operator_source": info.operator_source,
                      "cover": (delivered or candidates or uploads or [None])[0],
                      "counts": {"uploads": len(uploads), "candidates": len(candidates), "deliverables": len(delivered),
                                 "prompts": sum(1 for k, _ in PROMPT_FIELDS if values.get(k)),
                                 "review": len(values.get("scores") or [])}})
    return {"items": items}


@router.get("/outputs/{task_id}")
def task_outputs(task_id: str):
    from app import runner

    info = store.peek(task_id)
    if info is None:
        raise PortalError("TASK_NOT_FOUND", "找不到这个任务")
    return {"task_id": task_id, "status": info.status, "operator": info.operator, **_outputs(task_id, runner.values(task_id))}


# ---- 审计 ----


@router.get("/audit")
def audit_log(limit: int = 2000):
    """审计时间线：先把 nginx / fail2ban 新增的限流、封禁并进来；风格编号附上名字，前端拼中文句子。"""
    audit_feed.sync_logs()
    names = reference_wall.style_names()
    items = read_audit(max(1, min(limit, 5000)))
    for item in items:
        style = (item.get("detail") or {}).get("style")
        if style and style in names:
            item["detail"] = {**item["detail"], "style_name": names[style]}
    return {"items": items, "system_holders": sorted(access.SYSTEM_HOLDERS)}
