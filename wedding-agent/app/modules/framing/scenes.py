"""摄影师给用户的唯一选项：场景。每个风格 3 个场景 + 保留原图场景。

灯光、季节、互动不再问用户，由风格和场景自动带出；老任务里已经回答过的仍然按回答来。
规则版和真实 agent 共用这里的问题和默认值。
"""

from __future__ import annotations

KEEP_SCENE = "keep_original"
# 场景编号: (标题, 一句话描述, 灯光, 季节氛围)
SCENES: dict[str, tuple[str, str, str, str]] = {
    "keep_original": ("保留原图场景", "沿用原照片的地点和背景", "沿用原图光线", "沿用原图季节"),
    "studio": ("简洁影棚", "纯色背景，干净利落", "柔和棚拍光", "四季皆宜"),
    "garden": ("花园草地", "绿植花丛，自然清新", "柔和自然光", "春日花意"),
    "city_night": ("城市夜景", "街灯霓虹，都市浪漫", "夜晚街灯与霓虹", "秋夜微凉"),
    "courtyard": ("中式庭院", "红墙回廊，古典雅致", "温暖的午后阳光", "秋日暖色"),
    "palace": ("宫殿大殿", "金碧辉煌，庄重大气", "暖金色室内灯光", "冬日喜庆"),
    "red_studio": ("红色影棚", "正红背景，喜庆隆重", "柔和棚拍光", "四季皆宜"),
    "white_studio": ("白色影棚", "纯白背景，清透简约", "明亮柔和的棚拍光", "四季皆宜"),
    "cream_studio": ("奶油色影棚", "暖白纱帘，温柔慵懒", "柔和窗光", "春日温柔"),
    "floral_studio": ("花艺影棚", "鲜花布景，浪漫甜美", "柔和棚拍光", "春日花意"),
    "paris_street": ("巴黎街头", "石板街与老建筑，随性优雅", "柔和自然光", "秋日暖色"),
    "palace_hall": ("宫廷长廊", "雕花长廊，古典华丽", "窗边侧光", "冬日清透"),
    "editorial_studio": ("杂志影棚", "高级灰背景，时装大片感", "硬朗的时装棚拍光", "四季皆宜"),
    "forest_path": ("森林小径", "林间光斑，静谧自然", "林间散射光", "夏日明亮"),
    "lawn": ("草坪", "开阔草地，轻松惬意", "傍晚逆光", "春日花意"),
    "lakeside": ("湖边", "水面倒影，宁静开阔", "清晨柔光", "夏日明亮"),
    "old_villa": ("老洋房", "复古洋房，岁月质感", "温暖的室内灯光", "秋日暖色"),
    "retro_street": ("复古街巷", "老街招牌，港风怀旧", "傍晚暖光", "秋日暖色"),
    "film_studio": ("胶片影棚", "复古布景，胶片色调", "暖色复古棚拍光", "四季皆宜"),
    "castle": ("城堡", "古堡建筑，童话史诗", "戏剧化侧光", "冬日清透"),
    "seaside_dusk": ("黄昏海边", "海浪落日，电影感", "黄昏逆光", "夏日明亮"),
}
OLD_SCENES = {"city": "city_night"}  # 老任务的 q_scene 值
STYLE_SCENES = {
    "chinese_red_gold": ("courtyard", "palace", "red_studio"),
    "korean_studio": ("white_studio", "cream_studio", "floral_studio"),
    "french_editorial": ("paris_street", "palace_hall", "editorial_studio"),
    "forest": ("forest_path", "lawn", "lakeside"),
    "retro": ("old_villa", "retro_street", "film_studio"),
    "cinematic": ("city_night", "castle", "seaside_dusk"),
}
DEFAULT_SCENES = ("studio", "garden", "city_night")
STYLE_INTERACTION = {
    "chinese_red_gold": "并肩端坐，含笑看镜头",
    "korean_studio": "相拥微笑",
    "french_editorial": "牵手并肩，神情从容",
    "forest": "牵手漫步，自然对视",
    "retro": "挽手依偎，回眸看镜头",
    "cinematic": "相拥对视，带一点故事感",
}
OLD_LIGHT = {"soft": "柔和自然光", "warm": "温暖的室内灯光", "backlight": "傍晚逆光"}
OLD_SEASON = {"spring": "春日花意", "summer": "夏日明亮", "autumn": "秋日暖色", "winter": "冬日清透"}
OLD_INTERACTION = {"gaze": "牵手对视", "hug": "相拥微笑", "side": "并肩看镜头"}


def scene_ids(style: str | None) -> list[str]:
    return [*STYLE_SCENES.get(style or "", DEFAULT_SCENES), KEEP_SCENE]


def scene_question(style: str | None) -> dict:
    ids = scene_ids(style)
    return {
        "question_id": "q_scene",
        "type": "single_choice",
        "title": "想在哪种场景拍？",
        "options": [{"value": i, "label": SCENES[i][0], "image": None, "description": SCENES[i][1]} for i in ids],
        "recommended": ids[0],
        "allow_skip": True,
    }


def _value(answer: dict | None) -> str | None:
    if not answer or answer.get("skipped"):
        return None
    value = answer.get("value")
    if isinstance(value, list):
        value = value[0] if value else None
    return str(value) if value else None


def scene_choice(style: str | None, answers: dict[str, dict]) -> dict:
    """按回答（没答用推荐）得出场景以及自动带出的灯光、季节、互动。"""

    ids = scene_ids(style)
    picked = _value(answers.get("q_scene"))
    picked = OLD_SCENES.get(picked, picked)
    scene_id = picked if picked in SCENES else ids[0]
    label, description, light, season = SCENES[scene_id]
    light = OLD_LIGHT.get(_value(answers.get("q_light")) or "", light)
    season = OLD_SEASON.get(_value(answers.get("q_season")) or "", season)
    interaction = OLD_INTERACTION.get(_value(answers.get("q_interaction")) or "",
                                      STYLE_INTERACTION.get(style or "", "牵手对视"))
    return {"value": scene_id, "label": label, "description": description,
            "light": light, "season": season, "interaction": interaction}
