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

COOKIE = "xx_device"
PROTECTED = ("/api/", "/files/", "/templates/")
OPEN = ("/api/access/redeem", "/api/access/status")
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
    return required() and path.startswith(PROTECTED) and path not in OPEN


def holder_for(token: str | None) -> str | None:
    """凭证有效就返回持有人，否则 None。"""
    if not token:
        return None
    with _lock:
        data = _load()
        device = data["devices"].get(_hash(token))
        if not device or device["expires"] < time.time():
            return None
        if time.time() - device.get("last_seen", 0) > 3600:  # 最近使用时间每小时最多写一次
            device["last_seen"] = time.time()
            _save(data)
        return device["holder"]


def too_many_fails(ip: str) -> bool:
    now = time.time()
    recent = [t for t in _fails.get(ip, []) if now - t < FAIL_WINDOW]
    _fails[ip] = recent
    return len(recent) >= MAX_FAILS


def redeem(code: str, ip: str, user_agent: str = "") -> tuple[str, str] | None:
    """兑换邀请码。成功返回 (设备凭证, 持有人)，邀请码随即作废；失败返回 None 并记一次失败。"""
    with _lock:
        data = _load()
        entry = data["codes"].get(_hash(_normalize(code)))
        if not entry or entry.get("used_at"):
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
            "expires": now + settings.access_days * 86400,
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
        for holder, code in create([f"{args[1]}-{i:0{len(str(count))}d}" for i in range(1, count + 1)]):
            print(f"{holder}\t{code}")
    elif command == "list":
        data = _load()
        for entry in data["codes"].values():
            print(f"邀请码\t{entry['holder']}\t创建 {_fmt(entry['created'])}\t使用 {_fmt(entry.get('used_at'))}")
        for d in data["devices"].values():
            print(f"设备 {d['id']}\t{d['holder']}\t最近 {_fmt(d['last_seen'])}\t到期 {_fmt(d['expires'])}\t{d['ip']}\t{d['user_agent'][:60]}")
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
