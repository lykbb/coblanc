"""审计的“浏览与安全”部分：页面访问、nginx 层的拒绝 / 限流、fail2ban 封禁、任务创建回填。

- 页面访问：nginx 每个请求都 auth_request 问 /internal/gate/<名>（app/login.py），带 X-Original-URI/Host/IP。
  只记页面导航（不记接口、静态资源），同一人（或同一 IP）同一站点 30 分钟内只记一次 → action visit。
- 拒绝：图墙 / 后台的 gate 返回 403（IP 不在白名单）时记 forbidden（reason=ip），同 IP 同站点 10 分钟一次。
- 限流（nginx limit_req 的 429）和 fail2ban 封禁不经过后端：打开审计页时增量读 nginx access.log、fail2ban.log
  新增的部分（记住 inode + 偏移，只读新字节，2GB 小机器也不吃力）→ rate_limited / banned / unbanned。
- 回填：python -m app.audit_feed backfill 从 access.log(.1)、fail2ban.log、任务轨迹补上线前的访问、403、429、封禁、
  任务创建，带 backfilled: true；成员按“同 IP + 同 UA 的绑定设备”识别（device），否则按 IP 推断（ip）。可重复执行，不会重复写。
"""

from __future__ import annotations

import json
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from fastapi import Request

from app import access, portal
from app.common.config import settings

VISIT_WINDOW = 30 * 60
DENY_WINDOW = 10 * 60
ACCESS_LOGS = [Path("/var/log/nginx/access.log.1"), Path("/var/log/nginx/access.log")]
FAIL2BAN_LOG = Path("/var/log/fail2ban.log")
SITE_PREFIXES = {"/gallery/": "gallery", "/abordadmin/": "admin"}
_seen: dict[tuple, float] = {}
_seen_lock = threading.Lock()
_sync_lock = threading.Lock()


def site_of(uri: str, host: str, gate: str) -> str:
    if gate == "front":
        return "front"
    sub = host.split(".", 1)[0]
    if sub in ("gallery", "abordadmin"):
        return "gallery" if sub == "gallery" else "admin"
    for prefix, site in SITE_PREFIXES.items():
        if uri == prefix.rstrip("/") or uri.startswith(prefix):
            return site
    return "admin" if gate == "admin" else "front"


def is_page(uri: str, fetch_mode: str = "") -> bool:
    """页面导航：浏览器说明了 navigate 就信它；否则按路径猜（不是接口 / 静态资源 / 文件）。"""
    if fetch_mode:
        return fetch_mode == "navigate"
    path = uri.split("?", 1)[0]
    for prefix in SITE_PREFIXES:
        if path.startswith(prefix):
            path = "/" + path[len(prefix):]
    if re.match(r"^/(api|files|assets|templates|docs|openapi\.json|redoc|vendor|lib)(/|$)", path):
        return False
    return "." not in path.rsplit("/", 1)[-1]


def _first(key: tuple, window: float, now: float) -> bool:
    with _seen_lock:
        if now - _seen.get(key, 0) < window:
            return False
        _seen[key] = now
        if len(_seen) > 5000:
            for k in [k for k, t in _seen.items() if now - t > max(VISIT_WINDOW, DENY_WINDOW)]:
                del _seen[k]
        return True


def on_gate(request: Request, gate: str, ip: str, status: int, holder: str | None) -> None:
    """gate 的结果：204 且是页面导航 → visit；403 → forbidden。其他不记。"""
    uri = request.headers.get("x-original-uri", "")
    if not uri:
        return
    site = site_of(uri, request.headers.get("x-original-host", ""), gate)
    now = time.time()
    path = uri.split("?", 1)[0][:200]
    if status == 403:
        if _first(("deny", ip, site), DENY_WINDOW, now):
            portal.write_audit(request, site, None, "forbidden", {"path": path, "reason": "ip"}, ip=ip)
    elif status == 204 and is_page(uri, request.headers.get("sec-fetch-mode", "")):
        user, _ = portal.member_of(request, ip)
        if _first(("visit", user or holder or ip, site), VISIT_WINDOW, now):
            portal.write_audit(request, site, holder, "visit", {"path": path}, ip=ip)


# ---- 日志解析 ----

LINE = re.compile(r'^(\S+) \S+ (\S+) \[([^\]]+)\] "(\S+) (\S+)[^"]*" (\d{3}) \S+ "[^"]*" "([^"]*)"')
BAN = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ fail2ban\.actions\s+\[\d+\]: NOTICE\s+\[([^\]]+)\] (Ban|Unban|Restore Ban) (\S+)")


def parse_access(line: str) -> dict | None:
    m = LINE.match(line)
    if not m:
        return None
    ip, user, ts, method, uri, status, ua = m.groups()
    try:
        at = datetime.strptime(ts, "%d/%b/%Y:%H:%M:%S %z").timestamp()
    except ValueError:
        return None
    return {"at": at, "ip": ip, "method": method, "uri": uri, "status": int(status), "ua": ua}


def parse_ban(line: str) -> dict | None:
    m = BAN.match(line)
    if not m:
        return None
    ts, jail, kind, ip = m.groups()
    return {"at": time.mktime(time.strptime(ts, "%Y-%m-%d %H:%M:%S")), "jail": jail, "ip": ip,
            "action": "unbanned" if kind == "Unban" else "banned", "restore": kind == "Restore Ban"}


def _site_from_uri(uri: str) -> str:
    return site_of(uri, "", "")


def match_member(ip: str, ua: str) -> tuple[str | None, str | None]:
    """日志里没有 Cookie：同 IP 且同 UA 的绑定设备 → device；否则按 IP 推断。"""
    devices = [d for d in access._load()["devices"].values()
               if d.get("kind", "site") == "site" and d.get("ip") == ip and d.get("user_agent") == ua[:200]
               and d["holder"] not in access.SYSTEM_HOLDERS]
    if devices:
        return max(devices, key=lambda d: d.get("last_seen", 0))["holder"], "device"
    member = access.member_for_ip(ip)
    return (member, "ip") if member else (None, None)


def _entry(at: float, site: str, ip: str, ua: str, action: str, detail: dict, backfilled: bool, holder=None) -> dict:
    user, source = match_member(ip, ua) if ip else (None, None)
    entry = {"at": at, "site": site, "holder": holder, "user": user, "user_source": source, "ip": ip,
             "ua": ua[:200], "action": action, "detail": detail}
    if backfilled:
        entry["backfilled"] = True
    return entry


def nginx_events(rec: dict) -> str | None:
    """access.log 一行属于哪类事件：429 → rate_limited；只用于回填的：页面访问 visit、门禁 403 forbidden。"""
    if rec["status"] == 429:
        return "rate_limited"
    site = _site_from_uri(rec["uri"])
    if rec["status"] == 403 and site in ("gallery", "admin"):
        return "forbidden"
    if rec["method"] == "GET" and rec["status"] in (200, 304) and is_page(rec["uri"]) \
            and not rec["uri"].startswith(("/login", "/abordadmin/login", "/coblanc-film")):
        return "visit"
    return None


def _offsets_path() -> Path:
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    return settings.state_dir / "audit_log_offsets.json"


def _read_new(path: Path, offsets: dict) -> list[str]:
    """读 path 自上次以来的新行；日志轮转（inode 变了）时先把轮转后的旧文件剩下的读完。"""
    try:
        st = path.stat()
    except OSError:
        return []
    key = str(path)
    prev = offsets.get(key)
    lines: list[str] = []
    if prev and prev["inode"] != st.st_ino:
        rotated = Path(key + ".1")
        try:
            if rotated.stat().st_ino == prev["inode"]:
                with rotated.open("rb") as f:
                    f.seek(prev["offset"])
                    lines += f.read().decode("utf-8", "replace").splitlines()
        except OSError:
            pass
        prev = None
    start = prev["offset"] if prev and prev["offset"] <= st.st_size else 0
    with path.open("rb") as f:
        f.seek(start)
        data = f.read()
    end = start + data.rfind(b"\n") + 1
    offsets[key] = {"inode": st.st_ino, "offset": end}
    return lines + data[: end - start].decode("utf-8", "replace").splitlines()


def _mark_end(offsets: dict) -> None:
    for path in (ACCESS_LOGS[-1], FAIL2BAN_LOG):
        try:
            st = path.stat()
            offsets[str(path)] = {"inode": st.st_ino, "offset": st.st_size}
        except OSError:
            pass


def sync_logs() -> int:
    """审计页打开时调：把新出现的 429、封禁写进审计。第一次只记下当前位置（历史靠回填）。"""
    with _sync_lock:
        path = _offsets_path()
        offsets = json.loads(path.read_text()) if path.exists() else None
        if offsets is None:
            offsets = {}
            _mark_end(offsets)
            path.write_text(json.dumps(offsets))
            return 0
        entries = []
        for line in _read_new(ACCESS_LOGS[-1], offsets):
            rec = parse_access(line)
            if rec and rec["status"] == 429:
                entries.append(_entry(rec["at"], _site_from_uri(rec["uri"]), rec["ip"], rec["ua"], "rate_limited",
                                      {"path": rec["uri"].split("?", 1)[0][:200], "method": rec["method"]}, False))
        for line in _read_new(FAIL2BAN_LOG, offsets):
            ban = parse_ban(line)
            if ban and not ban["restore"]:
                entries.append(_entry(ban["at"], "", ban["ip"], "", ban["action"], {"jail": ban["jail"]}, False))
        if entries:
            portal.append_audit(entries)
        path.write_text(json.dumps(offsets))
        return len(entries)


# ---- 回填 ----


def _task_events(since: float, cutoff: float) -> list[dict]:
    out = []
    for trace in sorted((settings.state_dir / "traces").glob("*.jsonl")):
        try:
            with trace.open(encoding="utf-8") as f:
                at = json.loads(f.readline()).get("at", 0)
        except (OSError, ValueError):
            continue
        if not since <= at < cutoff:
            continue
        task = settings.state_dir / "tasks" / f"{trace.stem}.json"
        operator = json.loads(task.read_text()).get("operator") if task.exists() else None
        out.append({"at": at, "site": "front", "holder": operator, "user": operator,
                    "user_source": "device" if operator else None, "ip": "", "ua": "", "action": "task_created",
                    "detail": {"task_id": trace.stem}, "backfilled": True})
    return out


def backfill(since: float, cutoff: float | None = None) -> dict:
    """since ≤ 时间 < cutoff（默认：最早一条线上记录的访问 / 现在）。按 (action, site, ip, 秒) 去重。"""
    existing = portal.read_audit(10**9)
    live_visits = [e["at"] for e in existing if e["action"] == "visit" and not e.get("backfilled")]
    cutoff = cutoff or (min(live_visits) if live_visits else time.time())
    seen = {(e["action"], e.get("site"), e.get("ip"), int(e["at"])) for e in existing}
    seen |= {("task_created", e["detail"].get("task_id")) for e in existing if e["action"] == "task_created"}
    window: dict[tuple, float] = {}
    out: list[dict] = []
    for log in ACCESS_LOGS:
        try:
            lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            rec = parse_access(line)
            if not rec or not since <= rec["at"] < cutoff:
                continue
            kind = nginx_events(rec)
            if not kind:
                continue
            site = _site_from_uri(rec["uri"])
            user, _ = match_member(rec["ip"], rec["ua"])
            throttle = ("visit", user or rec["ip"], site) if kind == "visit" else (kind, rec["ip"], site)
            if rec["at"] - window.get(throttle, 0) < (VISIT_WINDOW if kind == "visit" else DENY_WINDOW):
                continue
            window[throttle] = rec["at"]
            detail = {"path": rec["uri"].split("?", 1)[0][:200]}
            if kind == "forbidden":
                detail["reason"] = "ip"
            if kind == "rate_limited":
                detail["method"] = rec["method"]
            out.append(_entry(rec["at"], site, rec["ip"], rec["ua"], kind, detail, True))
    try:
        for line in FAIL2BAN_LOG.read_text(encoding="utf-8", errors="replace").splitlines():
            ban = parse_ban(line)
            if ban and not ban["restore"] and since <= ban["at"] < cutoff:
                out.append(_entry(ban["at"], "", ban["ip"], "", ban["action"], {"jail": ban["jail"]}, True))
    except OSError:
        pass
    out = [e for e in out if (e["action"], e["site"], e["ip"], int(e["at"])) not in seen]
    out += [e for e in _task_events(since, cutoff) if ("task_created", e["detail"]["task_id"]) not in seen]
    out.sort(key=lambda e: e["at"])
    if out:
        portal.append_audit(out)
    offsets: dict = {}
    _mark_end(offsets)
    _offsets_path().write_text(json.dumps(offsets))
    counts: dict[str, int] = {}
    for e in out:
        counts[e["action"]] = counts.get(e["action"], 0) + 1
    return {"written": len(out), "cutoff": cutoff, "counts": counts}


def main(argv: list[str]) -> int:
    if argv[:1] != ["backfill"]:
        print("用法：python -m app.audit_feed backfill [--since YYYY-MM-DD]（默认今天 0 点，服务器时区）")
        return 2
    day = argv[argv.index("--since") + 1] if "--since" in argv else time.strftime("%Y-%m-%d")
    since = time.mktime(time.strptime(day, "%Y-%m-%d"))
    print(json.dumps(backfill(since), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
