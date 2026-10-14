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


# 一次完整任务由两个阶段组成：先生成一张样片，用户确认后再生成九张套图。
# 旧工单仍然受 settings.max_images_per_task 限制；新流程的阶段数量固定，
# 这样用户在样片或套图阶段重做时仍会得到完整的 1 张或 9 张结果。
GENERATION_STAGES = {"sample", "set"}


def generate(state: WeddingState) -> dict:
    prompt = state["prompt"]
    references = state.get("references", [])
    previous = state.get("generation") or {}
    # 没有 stage 的工单是旧契约，继续遵循 candidates_per_round，便于存量工单重放。
    # 新流程的首个生图调用没有 generation，默认走 sample；graph 在用户确认后写入 set。
    stage = previous.get("stage")
    if stage not in GENERATION_STAGES:
        stage = "sample" if "generation" not in state else None
    target = (
        settings.sample_candidates
        if stage == "sample"
        else settings.set_candidates
        if stage == "set"
        else settings.candidates_per_round
    )
    used = previous.get("total_images", 0)
    count = target if stage else min(target, settings.max_images_per_task - used)
    if count <= 0:
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
        # retouch_plan 的 target 为 generate 时按 patch 调整参数（比如加强人脸参考）；旧工单到 max_images_per_task 就停
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
    }
    if stage:
        generation["stage"] = stage
    step_text = "正在生成 1 张样片" if stage == "sample" else "正在生成 9 张婚礼套图" if stage == "set" else None
    update = {"candidates": candidates, "generation": generation}
    if step_text:
        update["step_text"] = step_text
    return update
