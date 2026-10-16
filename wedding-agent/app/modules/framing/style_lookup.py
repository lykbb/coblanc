"""摄影师查风格案例库（PR #14 的 01–07 离线数据）：业务风格 → 数据二级分类 → 少量案例的构图/姿态/光线文字。

只读本地 JSON，不联网、不读图片；数据缺失或格式不对时返回空，不影响主流程。
链接（飞书/微博/小红书）、service_url、水印信息一律不进提示词。
"""

from __future__ import annotations

import json
from pathlib import Path

from app.common.log import get_logger

log = get_logger("wedding.style_lookup")

DATA_ROOT = Path(__file__).resolve().parents[1] / "intake" / "knowledge" / "wedding-style-data"

# 业务风格编号（妆造师 look.style）→ 数据二级分类，按优先级排列
STYLE_MAP: dict[str, tuple[str, ...]] = {
    "chinese_red_gold": ("02-01", "02-02"),   # 传统红金喜嫁、俏皮喜嫁
    "korean_studio": ("03-08", "03-01"),      # 韩式甜蜜互动、奶油暖调柔光
    "french_editorial": ("06-12", "06-01"),   # 高定杂志封面、极简缎面高定
    "forest": ("04-03", "04-01"),             # 深林静谧童话、阳光草坪清新
    "retro": ("02-08", "05-03"),              # 民国海派、黑纱暗黑浪漫
    "cinematic": ("05-01", "07-03"),          # 极简黑纱时装、哥特古堡神秘
    # keep_original：沿用原图场景，不查案例
}

# 不能作参考的案例：双造型混在一组
EXCLUDED_CASES = {"SET000073"}
FLAG_CONSTRAINTS = {"composite_layout_not_single_shot", "orientation_review_required"}
MAX_CASES = 3
MAX_CHARS_PER_CASE = 600
MAX_TOTAL_CHARS = 1800


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _flagged(set_id: str) -> bool:
    case = DATA_ROOT / "cases" / set_id
    try:
        shots = _load(case / "shots.json")
        assets = _load(case / "assets.json")
    except Exception:
        return True
    if any(item.get("is_composite") for item in shots):
        return True
    return any(FLAG_CONSTRAINTS & set(item.get("reference_constraints") or []) for item in assets)


def pick_cases(style: str | None, limit: int = MAX_CASES) -> list[str]:
    secondaries = STYLE_MAP.get(style or "")
    if not secondaries:
        return []
    try:
        cases = _load(DATA_ROOT / "catalog.json").get("cases") or []
    except Exception as error:
        log.info("风格案例库不可用：%s", type(error).__name__)
        return []
    picked: list[str] = []
    for secondary in secondaries:
        for case in sorted(cases, key=lambda c: c.get("set_id", "")):
            set_id = case.get("set_id", "")
            if (case.get("secondary") != secondary or not case.get("independent_style_evidence")
                    or set_id in EXCLUDED_CASES or set_id in picked or _flagged(set_id)):
                continue
            picked.append(set_id)
            if len(picked) >= limit:
                return picked
    return picked


def _case_text(set_id: str) -> str:
    case = DATA_ROOT / "cases" / set_id
    recipe = _load(case / "recipe.json")
    shots = _load(case / "shots.json")
    keep = {"场景", "构图", "光线", "光影", "互动", "姿态", "道具", "配色", "景别"}
    obs = [o.get("statement", "") for o in recipe.get("observations") or [] if o.get("dimension") in keep]
    lines = [f"[{set_id}] {recipe.get('name', '')}：{recipe.get('description', '')}"]
    lines += [f"- {s}" for s in obs[:4]]
    for shot in shots[:4]:
        lines.append(f"- 镜头：{shot.get('shot', '')}；{shot.get('action', '')}；{shot.get('composition', '')}")
    text = "\n".join(line for line in lines if line.strip("- "))
    return text[:MAX_CHARS_PER_CASE]


def style_references(style: str | None) -> tuple[list[str], str]:
    """返回 (案例编号, 给摄影师的参考文字)。没有映射或数据缺失时返回 ([], "")。"""
    ids, parts, total = [], [], 0
    for set_id in pick_cases(style):
        try:
            text = _case_text(set_id)
        except Exception:
            continue
        if total + len(text) > MAX_TOTAL_CHARS:
            break
        ids.append(set_id)
        parts.append(text)
        total += len(text)
    return ids, "\n\n".join(parts)
