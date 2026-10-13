"""摄影师（agent）：负责背景、构图、景别、光线、姿势，写出镜头描述 shot。

在妆造师之后上场，可以参考妆造师的 look：以摄影师身份用 questions 和用户确认两人关系、互动方式、场景、季节和灯光，
确认后写 shot。姿势骨架图、背景参考图用资产库的 search_assets 去找。默认沿用原图姿势；
换姿势时只能用资产库里的姿势，按身高差分 3 档：close（5cm 以内）、medium（5–15cm）、large（15cm 以上）。
每次调用都要返回一版 shot（还在问问题时给的是按推荐选项写的草稿）。
fake 模式用下面的规则版；真实实现是一个 agent，按 TODO 补。
"""

from pathlib import Path

from app.common.config import settings
from app.modules.assets import search_assets
from app.state import Brief, WeddingState

PROMPTS = Path(__file__).parent / "prompts"
KEEP_ORIGINAL = "keep_original"
BACKGROUNDS = {
    "keep_original": "保持原图的地点、构图和光线",
    "studio": "简洁的室内影棚，半身到全身构图",
}
QUESTIONS = [
    {
        "question_id": "q_interaction",
        "type": "single_choice",
        "title": "你们平时相处更像哪种状态？",
        "options": [
            {"value": "gaze", "label": "牵手对视", "image": None},
            {"value": "hug", "label": "相拥微笑", "image": None},
            {"value": "side", "label": "并肩看镜头", "image": None},
        ],
        "recommended": "gaze",
        "allow_skip": True,
    },
    {
        "question_id": "q_light",
        "type": "single_choice",
        "title": "喜欢什么样的光线？",
        "options": [
            {"value": "soft", "label": "柔和自然光", "image": None},
            {"value": "warm", "label": "温暖的室内灯光", "image": None},
            {"value": "backlight", "label": "傍晚逆光", "image": None},
        ],
        "recommended": "soft",
        "allow_skip": True,
    },
]


def height_band(heights_cm: list[int]) -> str | None:
    if len(heights_cm) != 2:
        return None
    diff = abs(heights_cm[0] - heights_cm[1])
    if diff <= 5:
        return "close"
    if diff <= 15:
        return "medium"
    return "large"


def frame(state: WeddingState) -> dict:
    if settings.fake_for("framing"):
        return _rule_shot(state)
    # TODO(摄影师)：用 get_llm("agent") 做一个 agent，工具是 search_assets（kind 用 pose / background），
    #   以摄影师身份写 step_text 和 questions，和用户确认两人关系、互动、场景、季节、灯光；
    #   最多调用 settings.max_agent_steps 次工具；每次都返回一版 shot；
    #   默认沿用原图姿势，换姿势只能从资产库按身高档挑；描述里写明两人身高关系；
    #   retouch_plan 的 target 为 shot 时（比如身材比例不对）换姿势或改回原图姿势，不再问用户。返回格式和 _rule_shot 一样。
    raise NotImplementedError("摄影师的真实实现还没写，见《小囍模块接入规范》模块卡片 4")


def _choose(question: dict, answer: dict | None) -> dict:
    if answer and not answer.get("skipped"):
        for option in question["options"]:
            if option["value"] == answer.get("value"):
                return option
    return next(option for option in question["options"] if option["value"] == question["recommended"])


def _rule_shot(state: WeddingState) -> dict:
    brief = Brief(**state.get("brief", {}))
    plan = state.get("retouch_plan") or {}
    answers = {item["question_id"]: item for item in state.get("answers", []) if item.get("asker") == "framing"}
    interaction, light = (_choose(question, answers.get(question["question_id"])) for question in QUESTIONS)

    pose = brief.pose
    if plan.get("target") == "shot":  # 修图方案指向镜头（比如身材比例不对）：先改回原图姿势
        pose = KEEP_ORIGINAL
    references = []
    if pose != KEEP_ORIGINAL:
        matches = [item for item in search_assets("pose") if item["asset_id"] == f"pose_{pose}"]
        if matches:
            references.append({"url": matches[0]["url"], "role": "pose"})
        else:  # 资产库里还没有这个姿势：退回原图姿势
            pose = KEEP_ORIGINAL

    if len(brief.heights_cm) == 2:
        height = f"两人身高 {brief.heights_cm[0]}cm 和 {brief.heights_cm[1]}cm，保持这个身高差"
    else:
        height = "保持原图里两人的身高差和体型"
    pose_text = "沿用原图的姿势" if pose == KEEP_ORIGINAL else "按参考图的姿势站立"

    template = (PROMPTS / "shot.md").read_text(encoding="utf-8").strip()
    text = template.format(
        background=BACKGROUNDS.get(brief.background, BACKGROUNDS["keep_original"]),
        height=height,
        pose=pose_text,
        interaction=interaction["label"],
        light=light["label"],
    )
    if plan.get("target") == "shot" and plan.get("patch"):
        text += f"调整：{plan['patch']}。"

    shot = {"text": text, "pose": pose, "references": references}
    if answers or state.get("candidates"):  # 已经和用户确认过，或已经在修图阶段：不再问
        return {"shot": shot}
    return {"shot": shot, "questions": QUESTIONS, "step_text": "我是摄影师，想再了解一下你们平时怎么相处，喜欢什么样的光线。"}
