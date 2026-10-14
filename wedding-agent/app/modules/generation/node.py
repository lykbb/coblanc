"""生图 agent：拿小囍写好的最终提示词和参考图，生成样片或套图候选。

提示词由小囍负责，这里不改写。agent 只在三件事上自己判断：用哪条工作流（原图复刻或带参考图）、
主力服务失败时是否切到备用、某张失败时换种子重试。其余按规则走，所有上限从 settings 读。
"""

import time

from app.common.config import settings
from app.common.errors import ModuleError
from app.modules.assets import load_image, save_image
from app.state import WeddingState

from .client import generate_image


# 一次任务分两个阶段：先出 1 张样片（sample），用户确认后再出 9 张套图（set）。
# 重做时沿用当前阶段的张数；累计张数到 settings.max_images_per_task 就停。
STAGE_COUNTS = {"sample": "sample_candidates", "set": "set_candidates"}


def generate(state: WeddingState) -> dict:
    prompt = state["prompt"]
    references = state.get("references", [])
    previous = state.get("generation") or {}
    stage = previous.get("stage") if previous.get("stage") in STAGE_COUNTS else "sample"  # 套图阶段由框架在样片确认后写入
    count = getattr(settings, STAGE_COUNTS[stage])
    used = previous.get("total_images", 0)
    if used + count > settings.max_images_per_task:
        raise ModuleError("GENERATION_FAILED", "这次的生成次数用完了，请稍后重新开始")
    seeds = [1000 + used + i for i in range(count)]
    workflow = "with_references" if references else "keep_original"
    started = time.monotonic()

    if settings.fake_for("generation"):
        # 示例数据：直接用用户上传的照片当候选图
        photo = load_image(state["photo_urls"][0])
        images = [photo for _ in seeds]
        engine, workflow = "fake", "fake"
    else:
        # TODO(生图 agent)：套图阶段 9 张并行（在函数内部用 concurrent.futures.ThreadPoolExecutor）；
        # 单张超时 settings.image_timeout_seconds；失败换种子重试；主力服务失败时切到备用；
        # retouch_plan 的 target 为 generate 时按 patch 调整参数（比如加强人脸参考）
        images = [generate_image(state["photo_urls"], prompt, seed, references) for seed in seeds]
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
        "stage": stage,
    }
    step_text = f"正在生成 {count} 张样片" if stage == "sample" else f"正在生成 {count} 张婚礼套图"
    return {"candidates": candidates, "generation": generation, "step_text": step_text}
