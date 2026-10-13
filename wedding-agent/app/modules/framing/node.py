"""摄影师：写出镜头描述 shot。

不是 agent，不做多步循环。默认沿用原图姿势；换姿势时只能从资产库的姿势模板里选，
模板按身高差分 3 档：close（5cm 以内）、medium（5–15cm）、large（15cm 以上）。
"""

from pathlib import Path

from app.modules.assets import get_template
from app.state import Brief, WeddingState

PROMPTS = Path(__file__).parent / "prompts"
KEEP_ORIGINAL = "keep_original"
BACKGROUNDS = {
    "keep_original": "保持原图的地点、构图和光线",
    "studio": "简洁的室内影棚，柔和的正面光，半身到全身构图",
}


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
    brief = Brief(**state.get("brief", {}))
    plan = state.get("retouch_plan") or {}
    pose = brief.pose

    # 修图方案指向 shot（比如身材比例不对）：先改回原图姿势
    if plan.get("target") == "shot":
        pose = KEEP_ORIGINAL

    pose_ref_url = None
    if pose != KEEP_ORIGINAL:
        pose_ref_url = get_template(f"poses/{pose}.png")
        if pose_ref_url is None:  # 模板还没做好时退回原图姿势
            pose = KEEP_ORIGINAL

    if len(brief.heights_cm) == 2:
        height = f"两人身高 {brief.heights_cm[0]}cm 和 {brief.heights_cm[1]}cm，保持这个身高差"
    else:
        height = "保持原图里两人的身高差和体型"
    pose_text = "沿用原图的姿势和互动" if pose == KEEP_ORIGINAL else "按参考图的姿势站立，动作自然"

    template = (PROMPTS / "shot.md").read_text(encoding="utf-8").strip()
    text = template.format(background=BACKGROUNDS.get(brief.background, BACKGROUNDS["keep_original"]), height=height, pose=pose_text)
    if plan.get("target") == "shot" and plan.get("patch"):
        text += f"调整：{plan['patch']}。"
    # TODO(摄影师)：3 档身高差各准备至少 1 套姿势模板（放资产库 templates/poses/），按 height_band 选择
    return {"shot": {"text": text, "pose": pose, "pose_ref_url": pose_ref_url}}
