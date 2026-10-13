"""生图 agent。

agent 只在三件事上自己判断：用哪条工作流（原图复刻或姿势参考）、主力服务失败时是否切到备用、
某张失败时换种子重试。其余按规则走，所有上限从 settings 读。
"""

import time
from pathlib import Path

from app.common.config import settings
from app.common.errors import ModuleError
from app.modules.assets import load_image, save_image
from app.state import WeddingState

from .client import generate_image

PROMPTS = Path(__file__).parent / "prompts"


def build_prompt(state: WeddingState) -> str:
    opening = (PROMPTS / "opening.md").read_text(encoding="utf-8").strip()
    parts = [opening, (state.get("look") or {}).get("text", ""), (state.get("shot") or {}).get("text", "")]
    plan = state.get("retouch_plan") or {}
    if plan.get("target") == "generate" and plan.get("patch"):
        parts.append(f"特别注意：{plan['patch']}。")
    return "".join(part for part in parts if part)


def generate(state: WeddingState) -> dict:
    prompt = build_prompt(state)
    used = (state.get("generation") or {}).get("total_images", 0)
    count = min(settings.candidates_per_round, settings.max_images_per_task - used)
    if count <= 0:
        raise ModuleError("GENERATION_FAILED", "这次的生成次数用完了，请稍后重新开始")
    seeds = [1000 + used + i for i in range(count)]
    pose_ref_url = (state.get("shot") or {}).get("pose_ref_url")
    workflow = "pose_reference" if pose_ref_url else "keep_original"
    started = time.monotonic()

    if settings.fake_for("generation"):
        # 示例数据：直接用用户上传的照片当候选图
        photo = load_image(state["photo_urls"][0])
        images = [photo for _ in seeds]
        engine, workflow = "fake", "fake"
    else:
        # TODO(生图 agent)：4 张并行；单张超时 settings.image_timeout_seconds；
        # 失败换种子重试；主力服务失败时切到备用；到 max_images_per_task 就停
        images = [generate_image(state["photo_urls"], prompt, seed, pose_ref_url) for seed in seeds]
        engine = "main"

    candidates = [
        {"image_id": f"img_{used + i + 1}", "url": save_image(image, "candidate"), "seed": seed}
        for i, (image, seed) in enumerate(zip(images, seeds))
    ]
    generation = {
        "engine": engine,
        "workflow": workflow,
        "seconds": round(time.monotonic() - started, 2),
        "total_images": used + len(candidates),
    }
    return {"prompt": prompt, "candidates": candidates, "generation": generation}
