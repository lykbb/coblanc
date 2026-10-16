"""访问控制：一次性邀请码 + 设备绑定。

- 邀请码只能兑换一次；兑换后浏览器拿到一个设备凭证（HttpOnly Cookie，默认 180 天），绑定到邀请码的持有人。
- 邀请码和设备凭证都只存 sha256，文件在 state_dir/access.json。
- 开关：ACCESS_INVITE_REQUIRED=0 时全部放行，前端也不显示邀请码页（不用改代码）。
- 没有有效凭证时，/api、/files、/templates 一律 401（兑换和状态接口除外）。

管理（在 wedding-agent 目录）：
  uv run python -m app.access create 张三 李四 grokbot   # 每人生成一个邀请码，只显示这一次
  uv run python -m app.access bulk 200 公测 > codes.tsv  # 批量生成：持有人记为 公测-001…公测-200
  uv run python -m app.access list                       # 持有人、邀请码是否已用、设备
  uv run python -m app.access revoke 张三                 # 作废此人的设备和未用邀请码
  uv run python -m app.access revoke-device <设备编号>      # 只踢掉一台设备
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sys
import threading
import time
from pathlib import Path

from app.common.config import settings

COOKIE = "xx_device"  # 用户站设备凭证
ADMIN_COOKIE = "xx_admin"  # 后台凭证：只在后台站点设置，SameSite=Strict，空闲超时短，见 app/admin.py
PROTECTED = ("/api/", "/files/", "/templates/")
OPEN = ("/api/access/redeem", "/api/access/status")
ADMIN_PREFIX = "/api/admin/"  # 后台接口自己鉴权（管理员白名单 + CSRF），不走这里
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # 去掉 0/O/1/I/L，口头转述不易错
MAX_FAILS, FAIL_WINDOW = 10, 600  # 同一 IP 10 分钟内最多输错 10 次

_lock = threading.Lock()
_fails: dict[str, list[float]] = {}


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _normalize(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch.isalnum())


def _path() -> Path:
    return settings.state_dir / "access.json"


def _load() -> dict:
    try:
        return json.loads(_path().read_text())
    except FileNotFoundError:
        return {"codes": {}, "devices": {}}


def _save(data: dict) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    tmp.chmod(0o600)
    tmp.replace(path)


def required() -> bool:
    return settings.access_required


def needs_check(path: str) -> bool:
    return required() and path.startswith(PROTECTED) and path not in OPEN and not path.startswith(ADMIN_PREFIX)


def allowed(cookies: dict) -> bool:
    """用户站接口和文件：用户站设备凭证有效即可；后台凭证也能看文件（后台任务页要显示图片）。"""
    return bool(holder_for(cookies.get(COOKIE)) or holder_for(cookies.get(ADMIN_COOKIE), kind="admin"))


def holder_for(token: str | None, kind: str = "site") -> str | None:
    """凭证有效就返回持有人，否则 None。后台凭证另有空闲超时（ADMIN_SESSION_HOURS）。"""
    if not token:
        return None
    with _lock:
        data = _load()
        device = data["devices"].get(_hash(token))
        now = time.time()
        if not device or device.get("kind", "site") != kind or device["expires"] < now:
            return None
        if kind == "admin" and now - device.get("last_seen", 0) > settings.admin_session_hours * 3600:
            return None
        if now - device.get("last_seen", 0) > (60 if kind == "admin" else 3600):  # 少写盘
            device["last_seen"] = now
            _save(data)
        return device["holder"]


def too_many_fails(ip: str) -> bool:
    now = time.time()
    recent = [t for t in _fails.get(ip, []) if now - t < FAIL_WINDOW]
    _fails[ip] = recent
    return len(recent) >= MAX_FAILS


def redeem(code: str, ip: str, user_agent: str = "", kind: str = "site", holders: list[str] | None = None) -> tuple[str, str] | None:
    """兑换邀请码。成功返回 (设备凭证, 持有人)，邀请码随即作废；失败返回 None 并记一次失败。

    kind="admin" 时只接受 holders 名单里的人的邀请码；不在名单里的码按无效处理且不作废。
    """
    with _lock:
        data = _load()
        entry = data["codes"].get(_hash(_normalize(code)))
        if not entry or entry.get("used_at") or (holders is not None and entry["holder"] not in holders):
            _fails.setdefault(ip, []).append(time.time())
            return None
        token = secrets.token_urlsafe(32)
        now = time.time()
        entry["used_at"] = now
        data["devices"][_hash(token)] = {
            "id": secrets.token_hex(4),
            "holder": entry["holder"],
            "created": now,
            "last_seen": now,
            "kind": kind,
            "expires": now + (settings.admin_max_days if kind == "admin" else settings.access_days) * 86400,
            "ip": ip,
            "user_agent": user_agent[:200],
        }
        _save(data)
        return token, entry["holder"]


def create(holders: list[str]) -> list[tuple[str, str]]:
    result = []
    with _lock:
        data = _load()
        for holder in holders:
            raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(10))
            data["codes"][_hash(raw)] = {"holder": holder, "created": time.time(), "used_at": None}
            result.append((holder, f"{raw[:5]}-{raw[5:]}"))
        _save(data)
    return result


def revoke(holder: str) -> int:
    """作废此人所有设备和未用邀请码，返回作废数量。"""
    with _lock:
        data = _load()
        codes = {k: v for k, v in data["codes"].items() if v["holder"] == holder and not v.get("used_at")}
        devices = {k for k, v in data["devices"].items() if v["holder"] == holder}
        for key in codes:
            del data["codes"][key]
        for key in devices:
            del data["devices"][key]
        _save(data)
        return len(codes) + len(devices)


def revoke_token(token: str | None) -> None:
    if not token:
        return
    with _lock:
        data = _load()
        if data["devices"].pop(_hash(token), None):
            _save(data)


def overview() -> dict:
    """给后台看的清单：不含任何哈希。"""
    data = _load()
    codes = [{"holder": c["holder"], "created": c["created"], "used_at": c.get("used_at")} for c in data["codes"].values()]
    devices = [{key: d.get(key) for key in ("id", "holder", "created", "last_seen", "expires", "ip", "user_agent")}
               | {"kind": d.get("kind", "site")} for d in data["devices"].values()]
    return {"codes": sorted(codes, key=lambda c: -c["created"]), "devices": sorted(devices, key=lambda d: -d["last_seen"])}


def bulk_holders(count: int, prefix: str) -> list[str]:
    return [f"{prefix}-{i:0{len(str(count))}d}" for i in range(1, count + 1)]


def revoke_device(device_id: str) -> bool:
    with _lock:
        data = _load()
        keys = [k for k, v in data["devices"].items() if v["id"] == device_id]
        for key in keys:
            del data["devices"][key]
        _save(data)
        return bool(keys)


def _fmt(ts: float | None) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)) if ts else "-"


def main(argv: list[str]) -> int:
    command, args = (argv[0], argv[1:]) if argv else ("", [])
    if command == "create" and args:
        for holder, code in create(args):
            print(f"{holder}\t{code}")
        print("邀请码只显示这一次，各自只能用一次。")
    elif command == "bulk" and len(args) == 2 and args[0].isdigit():
        count = int(args[0])
        for holder, code in create(bulk_holders(count, args[1])):
            print(f"{holder}\t{code}")
    elif command == "list":
        data = overview()
        for entry in data["codes"]:
            print(f"邀请码\t{entry['holder']}\t创建 {_fmt(entry['created'])}\t使用 {_fmt(entry.get('used_at'))}")
        for d in data["devices"]:
            print(f"{'后台' if d['kind'] == 'admin' else '设备'} {d['id']}\t{d['holder']}\t最近 {_fmt(d['last_seen'])}\t到期 {_fmt(d['expires'])}\t{d['ip']}\t{d['user_agent'][:60]}")
    elif command == "revoke" and len(args) == 1:
        print(f"已作废 {revoke(args[0])} 项")
    elif command == "revoke-device" and len(args) == 1:
        print("已作废" if revoke_device(args[0]) else "没有这台设备")
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
