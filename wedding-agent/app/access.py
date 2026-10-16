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
PROTECTED = ("/api/", "/files/", "/templates/")
OPEN = ("/api/access/redeem", "/api/access/status")
LOGIN_COOKIES = {"front": "xx_login", "admin": "xx_admin"}  # 账号密码登录的会话（前台、后台），见 app/login.py；图墙只认 IP
PORTAL_PREFIXES = ("/api/admin/", "/api/gallery/")  # 内部站点自己鉴权（app/portal.py），不走这里
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # 去掉 0/O/1/I/L，口头转述不易错
MAX_FAILS, FAIL_WINDOW = 10, 600  # 同一 IP 10 分钟内最多输错 10 次

_lock = threading.Lock()
_fails: dict[str, list[float]] = {}
_ip_cache: dict = {}


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
    return required() and path.startswith(PROTECTED) and path not in OPEN and not path.startswith(PORTAL_PREFIXES)


def allowed(cookies: dict, ip: str = "") -> bool:
    """用户站接口和文件：用户站设备凭证有效即可；后台凭证也能看文件（后台任务页要显示图片）。"""
    return bool(holder_for(cookies.get(COOKIE), ip=ip) or holder_for(cookies.get(LOGIN_COOKIES["admin"]), kind="admin"))


def portal_ips() -> set[str]:
    """内部站点（图墙、后台）的来源 IP 白名单：团队成员（ADMIN_HOLDERS ∪ GALLERY_MEMBERS ∪ grokbot）有效用户站设备
    最近使用的 IP + 手工补充文件 + 本机。其他持有人（公开邀请等）兑换前台码后 IP 也不会进白名单。

    nginx 用 auth_request 问 /internal/gate/team、/internal/gate/admin（app/login.py）；作废持有人（删设备）后其 IP 自动移除。按文件修改时间缓存。
    手工补充：state_dir/portal-extra-ips.txt，一行一个 IP，# 开头为注释，改完即时生效。
    """
    paths = (_path(), settings.state_dir / "portal-extra-ips.txt")
    key = tuple(p.stat().st_mtime_ns if p.exists() else 0 for p in paths) + (tuple(settings.admin_holders), tuple(settings.gallery_members))
    if _ip_cache.get("key") != key or time.time() - _ip_cache.get("at", 0) > 60:  # 每分钟也刷新一次（设备过期）
        now = time.time()
        ips = {"127.0.0.1"}
        team = set(settings.admin_holders) | set(settings.gallery_members) | {"grokbot"}
        ips |= {d.get("ip") for d in _load()["devices"].values()
                if d.get("kind", "site") == "site" and d["holder"] in team and d["expires"] > now and d.get("ip")}
        if paths[1].exists():
            ips |= {line.split("#")[0].strip() for line in paths[1].read_text(encoding="utf-8").splitlines()} - {""}
        _ip_cache.update(key=key, at=now, ips=ips)
    return _ip_cache["ips"]


def holder_for(token: str | None, kind: str = "site", ip: str = "") -> str | None:
    """凭证有效就返回持有人，否则 None。kind：site 用户站设备 / front 前台登录 / admin 后台登录（另有空闲超时）。"""
    if not token:
        return None
    with _lock:
        data = _load()
        device = data["devices"].get(_hash(token))
        now = time.time()
        if not device or device.get("kind", "site") != kind or device["expires"] < now:
            return None
        idle_hours = {"admin": settings.admin_session_hours}.get(kind)
        if idle_hours and now - device.get("last_seen", 0) > idle_hours * 3600:
            return None
        if now - device.get("last_seen", 0) > (60 if idle_hours else 3600) or (ip and device.get("ip") != ip):  # 少写盘；IP 变了立即记
            device["last_seen"] = now
            if ip:
                device["ip"] = ip
            _save(data)
        return device["holder"]


def too_many_fails(ip: str) -> bool:
    now = time.time()
    recent = [t for t in _fails.get(ip, []) if now - t < FAIL_WINDOW]
    _fails[ip] = recent
    return len(recent) >= MAX_FAILS


def _new_device(data: dict, holder: str, kind: str, ip: str, user_agent: str, days: float) -> str:
    token = secrets.token_urlsafe(32)
    now = time.time()
    data["devices"][_hash(token)] = {
        "id": secrets.token_hex(4), "holder": holder, "created": now, "last_seen": now, "kind": kind,
        "expires": now + days * 86400, "ip": ip, "user_agent": user_agent[:200],
    }
    return token


def redeem(code: str, ip: str, user_agent: str = "") -> tuple[str, str] | None:
    """兑换用户站邀请码。成功返回 (设备凭证, 持有人)，邀请码随即作废；失败返回 None 并记一次失败。"""
    with _lock:
        data = _load()
        entry = data["codes"].get(_hash(_normalize(code)))
        if not entry or entry.get("used_at"):
            record_fail(ip)
            return None
        entry["used_at"] = time.time()
        token = _new_device(data, entry["holder"], "site", ip, user_agent, settings.access_days)
        _save(data)
        return token, entry["holder"]


def start_session(holder: str, kind: str, ip: str, user_agent: str = "") -> str:
    """账号密码登录成功后开会话（kind：front / admin），返回凭证。"""
    with _lock:
        data = _load()
        token = _new_device(data, holder, kind, ip, user_agent, settings.portal_max_days)
        _save(data)
        return token


def record_fail(ip: str) -> None:
    _fails.setdefault(ip, []).append(time.time())


def ip_holder(ip: str) -> str:
    """图墙按 IP 识别上传人：最近用这个 IP 的团队成员设备，没有就记 IP。"""
    team = set(settings.admin_holders) | set(settings.gallery_members) | {"grokbot"}
    devices = [d for d in _load()["devices"].values() if d.get("kind", "site") == "site" and d.get("ip") == ip and d["holder"] in team]
    return max(devices, key=lambda d: d.get("last_seen", 0))["holder"] if devices else ip


SYSTEM_HOLDERS = {"grokbot", "test", "admin", "xiaoxi", "verify-bot"}  # 系统 / 共享账号，不算具体成员


def member_for_ip(ip: str) -> str | None:
    """这个 IP 最近用的是哪位成员（任意用户站设备的持有人，排除系统账号）；对不上返回 None。"""
    if not ip:
        return None
    devices = [d for d in _load()["devices"].values()
               if d.get("kind", "site") == "site" and d.get("ip") == ip and d["holder"] not in SYSTEM_HOLDERS]
    return max(devices, key=lambda d: d.get("last_seen", 0))["holder"] if devices else None


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
            print(f"{ {'admin': '后台', 'front': '前台'}.get(d['kind'], '设备')} {d['id']}\t{d['holder']}\t最近 {_fmt(d['last_seen'])}\t到期 {_fmt(d['expires'])}\t{d['ip']}\t{d['user_agent'][:60]}")
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
