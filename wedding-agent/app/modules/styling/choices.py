"""妆造师给用户的三个选项（唯一来源）：风格、妆容、衣服。新娘和新郎共用一个风格、一个妆容方向、一套衣服。

- 风格：7 个婚礼风格（编号也是 look.style，摄影师、前端都按它取名字和图）。
- 妆容：一个"妆容方向"自动配好新娘和新郎各一类妆，分类和文字摘要读 PR #15 的离线数据
  （knowledge/makeup_candidates/*/catalog.json，只读文字，不读图片、不联网，跳过 hold_ai_label 等不可默认检索的案例）。
- 衣服：一套婚纱 + 西装。资产库有 outfit 物料（tags 带风格编号）时用物料，否则用下面的文字套装。
发型、配饰不让用户选，由妆造师按风格、妆容、衣服搭配。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.common.log import get_logger

log = get_logger("styling.choices")
MAKEUP_DATA = Path(__file__).parent / "knowledge" / "makeup_candidates"
DEFAULT_STYLE = "keep_original"

# 风格编号 → (名字, 一句描述)
STYLES = {
    "chinese_red_gold": ("中式红金", "红金喜嫁，端庄喜庆"),
    "korean_studio": ("韩式影棚", "干净棚拍，清透柔和"),
    "french_editorial": ("法式杂志", "松弛高级，杂志质感"),
    "forest": ("森系", "自然清新，花草相伴"),
    "retro": ("复古", "经典红唇，怀旧胶片味"),
    "cinematic": ("电影感", "有故事的光影氛围"),
    "keep_original": ("保留原图场景", "沿用照片里的场景，只换造型"),
}

# 用户描述里的常见风格说法：描述已经说清风格时跳过风格题
STYLE_ALIASES = {
    "korean_studio": ("韩式", "韩国", "korean", "影棚"),
    "chinese_red_gold": ("中式", "红金", "国风"),
    "french_editorial": ("法式", "法风", "editorial"),
    "forest": ("森系", "自然", "花园"),
    "retro": ("复古", "retro"),
    "cinematic": ("电影感", "电影", "cinematic"),
    "keep_original": ("原图", "保持原样", "保留原图"),
}

# 妆容方向 → (名字, 新娘分类编号, 新郎分类编号)；分类编号是 PR #15 各自妆容库的 01–07
MAKEUPS = {
    "makeup_korean_dewy": ("韩式水光", "01", "03"),
    "makeup_french_retro": ("法式复古", "02", "05"),
    "makeup_bold_glam": ("浓颜精致", "03", "04"),
    "makeup_noble": ("贵气端庄", "04", "04"),
    "makeup_new_chinese": ("新中式", "05", "01"),
    "makeup_soft_matte": ("低饱和柔雾", "06", "02"),
    "makeup_mood": ("氛围感", "07", "06"),
}
STYLE_MAKEUPS = {  # 每个风格推荐的 3 个妆容方向，第一个是推荐项
    "chinese_red_gold": ("makeup_new_chinese", "makeup_noble", "makeup_soft_matte"),
    "korean_studio": ("makeup_korean_dewy", "makeup_soft_matte", "makeup_mood"),
    "french_editorial": ("makeup_french_retro", "makeup_mood", "makeup_soft_matte"),
    "forest": ("makeup_soft_matte", "makeup_korean_dewy", "makeup_mood"),
    "retro": ("makeup_french_retro", "makeup_bold_glam", "makeup_noble"),
    "cinematic": ("makeup_mood", "makeup_bold_glam", "makeup_french_retro"),
    "keep_original": ("makeup_soft_matte", "makeup_korean_dewy", "makeup_mood"),
}

# 文字套装：风格 → [(编号, 名字, 新娘婚纱, 新郎西装)]，第一个是推荐项
OUTFITS = {
    "chinese_red_gold": (
        ("outfit_chinese_red_gold_classic", "经典秀禾", "刺绣红金秀禾礼服配精致发饰", "深色中式礼服配简洁胸针"),
        ("outfit_chinese_red_gold_modern", "现代红裙", "现代剪裁红色礼服配小巧耳饰", "黑色立领礼服配低调胸针"),
    ),
    "korean_studio": (
        ("outfit_korean_studio_satin", "缎面", "缎面抹胸婚纱配长头纱和珍珠耳饰", "黑色修身西装配白衬衫"),
        ("outfit_korean_studio_lace", "蕾丝", "细腻蕾丝长袖婚纱配小巧耳饰", "深灰西装配白衬衫和简洁领结"),
        ("outfit_korean_studio_minimal", "极简", "无装饰极简婚纱配细链耳饰", "纯黑西装配白衬衫"),
    ),
    "french_editorial": (
        ("outfit_french_editorial_silk", "真丝", "简洁真丝婚纱配少量金属耳饰", "深色剪裁西装配窄领带"),
        ("outfit_french_editorial_clean", "极简", "线条简洁的婚纱配极简耳饰", "炭灰西装配白衬衫和低调腕表"),
    ),
    "forest": (
        ("outfit_forest_flower", "花意", "轻盈婚纱配细小花材头饰", "浅色西装配小花胸针"),
        ("outfit_forest_linen", "亚麻", "轻薄婚纱配温和色彩耳饰", "亚麻色西装配简洁胸花"),
    ),
    "retro": (
        ("outfit_retro_wave", "波浪", "复古剪裁婚纱配珍珠耳饰", "深色复古西装配窄领带"),
        ("outfit_retro_classic", "经典", "经典礼服配小巧复古耳饰", "黑色礼服配白色胸花"),
    ),
    "cinematic": (
        ("outfit_cinematic_mono", "黑白", "线条简洁的白色婚纱配克制耳饰", "黑色西装配白衬衫"),
        ("outfit_cinematic_warm", "暖调", "质感缎面婚纱配细致耳饰", "深棕西装配简洁领带"),
    ),
    "keep_original": (
        ("outfit_keep_original_classic", "经典婚礼", "简洁婚纱配克制配饰", "经典西装配简洁胸花"),
        ("outfit_keep_original_natural", "自然", "轻盈简洁婚纱配小巧配饰", "干净西装配简洁胸花"),
    ),
}


def style_ids() -> list[str]:
    return list(STYLES)


def style_option(style_id: str, image: str | None = None) -> dict:
    label, description = STYLES.get(style_id, (style_id, ""))
    return {"value": style_id, "label": label, "image": image, "description": description}


@lru_cache(maxsize=2)
def _makeup_categories(side: str) -> dict[str, dict]:
    """PR #15 数据：分类编号 → {name, summaries}。只取可默认检索的案例；数据缺失时返回空，不影响流程。"""
    try:
        data = json.loads((MAKEUP_DATA / f"{side}_makeup_data" / "catalog.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        log.warning("妆容数据读不到（%s）：%s", side, type(error).__name__)
        return {}
    held = set(data.get("held_case_ids") or [])
    out: dict[str, dict] = {}
    for case in data.get("cases") or []:
        if case.get("case_id") in held or case.get("status") == "hold_ai_label" or not case.get("default_retrieval_eligible"):
            continue
        entry = out.setdefault(str(case.get("category_id")), {"name": str(case.get("category_name") or ""), "summaries": []})
        if case.get("summary"):
            entry["summaries"].append(str(case["summary"]))
    return out


def makeup_detail(makeup_id: str) -> dict:
    """{value, label, bride, groom, bride_notes, groom_notes}：bride/groom 是分类名，notes 是案例摘要（给妆造师参考）。"""
    label, bride_cat, groom_cat = MAKEUPS[makeup_id]
    bride = _makeup_categories("bride").get(bride_cat, {})
    groom = _makeup_categories("groom").get(groom_cat, {})
    return {"value": makeup_id, "label": label,
            "bride": bride.get("name") or label, "groom": groom.get("name") or label,
            "bride_notes": bride.get("summaries", [])[:2], "groom_notes": groom.get("summaries", [])[:2]}


def makeup_options(style_id: str) -> list[dict]:
    out = []
    for makeup_id in STYLE_MAKEUPS.get(style_id, STYLE_MAKEUPS[DEFAULT_STYLE]):
        detail = makeup_detail(makeup_id)
        out.append({"value": makeup_id, "label": detail["label"], "image": None,
                    "description": f"新娘{detail['bride']}，新郎{detail['groom']}"})
    return out


def outfit_options(style_id: str, assets: list[dict]) -> list[dict]:
    """资产库 outfit 物料优先（description 写婚纱 + 西装）；没有就用文字套装。每项另带 bride / groom 两边文字。"""
    out = []
    for item in assets[:3]:
        asset_id = str(item.get("asset_id") or "")
        if asset_id:
            text = str(item.get("description") or "")
            out.append({"value": asset_id, "label": str(item.get("name") or asset_id), "image": item.get("url"),
                        "description": text, "bride": text, "groom": ""})
    if out:
        return out
    for outfit_id, label, bride, groom in OUTFITS.get(style_id, OUTFITS[DEFAULT_STYLE]):
        out.append({"value": outfit_id, "label": label, "image": None,
                    "description": f"婚纱：{bride}；西装：{groom}", "bride": bride, "groom": groom})
    return out


def legacy_outfit(look_set_id: str) -> str:
    """老任务回答过的 q_look_set（look_set_<风格>_<名字>）→ 同名套装编号 outfit_<风格>_<名字>。"""
    return "outfit_" + look_set_id.removeprefix("look_set_")
