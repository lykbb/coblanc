"""生图 Agent：先出样片、确认后出套图；Pi 运行计划，线程池执行有限次数的生图调用。"""

import copy
import re
import secrets
import threading
import time
from pathlib import Path

from app.common.config import settings
from app.common.errors import ModuleError
from app.common.log import current_task
from app.modules.assets import load_image, save_image
from app.state import WeddingState

from .client import ImageCallFailure, _Budget, _Scope, _call_scope, generate_image
from .pi_bridge import run_pi


def _parameters(patch: str) -> dict:
    parameters = {"optimize_prompt_options": {"mode": "standard"}}
    match = re.search(r"size\s*=\s*(1K|1\.5K|2K|[1-9]\d*x[1-9]\d*)", patch)
    if match:
        size = match.group(1)
        if "x" in size:
            width, height = map(int, size.split("x"))
            if not 921600 <= width * height <= 4624220 or not 1 / 16 <= width / height <= 16:
                raise ModuleError("GENERATION_FAILED", "修图尺寸超出生图模型支持范围")
        parameters["size"] = size
    return parameters


# 一次任务分两个阶段：先出 1 张样片（sample），用户确认后再出 9 张套图（set）。
# 重做时沿用当前阶段的张数；累计张数到 settings.max_images_per_task 就停。
STAGE_COUNTS = {"sample": "sample_candidates", "set": "set_candidates"}


def generate(state: WeddingState) -> dict:
    prompt = state.get("prompt", "")
    identity = state.get("identity") or []
    # 发图顺序 = 身份照清单（与提示词开头的"图几是谁"一致），再接参考图；总数不超过 10 张。
    photos = [item["url"] for item in identity if item.get("url")] or list(state.get("photo_urls", []))
    references = copy.deepcopy(state.get("references", []))[: max(0, 10 - len(photos))]
    previous = state.get("generation") or {}
    stage = previous.get("stage") if previous.get("stage") in STAGE_COUNTS else "sample"  # 套图阶段由框架在样片确认后写入
    count = getattr(settings, STAGE_COUNTS[stage])
    used = previous.get("total_images", 0)
    remaining = settings.max_images_per_task - used
    if count <= 0 or remaining < count:
        raise ModuleError("GENERATION_FAILED", "这次的生成次数用完了，请稍后重新开始")
    if not photos or not prompt.strip():
        raise ModuleError("GENERATION_FAILED", "需要合照和完整的拍摄指令")
    # 每张用自己镜头的提示词：样片用 slot 0，套图用 slot 0~8；没有分镜时都用统一 prompt。
    by_slot = {item["slot"]: item["prompt"] for item in state.get("shot_prompts") or []}
    slot_prompts = [by_slot.get(slot, prompt) for slot in range(count)]
    started = time.monotonic()
    workflow = "with_references" if references else "keep_original"
    results: dict[int, dict] = {}

    if settings.fake_for("generation"):
        try:
            image = load_image(photos[0])
        except Exception:
            raise ModuleError("FILE_INVALID", "合照无法读取，请重新上传")
        for slot in range(count):
            results[slot] = {"image": image, "seed": 1000 + used + slot, "engine": "fake"}
        engine, workflow = "fake", "fake"
    else:
        if count > settings.max_agent_steps:
            raise ModuleError("GENERATION_FAILED", "生成数量超过 Agent 工具调用上限")
        deadline = started + settings.image_timeout_seconds
        budget = _Budget(remaining)
        lock = threading.Lock()
        seen: set[int] = set()
        errors: list[Exception] = []
        plan = state.get("retouch_plan") or {}
        parameters = _parameters(plan.get("patch", "") if plan.get("target") == "generate" else "")
        seeds = [secrets.randbelow(2**31) for _ in range(count)]
        task_id = state.get("task_id", "")

        def execute(name: str, arguments: dict) -> dict:
            slot = arguments.get("slot")
            if name != "generate_candidate" or not isinstance(slot, int) or not 0 <= slot < count:
                raise ValueError("无效的生成计划")
            with lock:
                if slot in seen or arguments.get("seed") != seeds[slot]:
                    raise ValueError("重复或无效的生成计划")
                seen.add(slot)
            seed = seeds[slot]
            scope = _Scope(budget, deadline, parameters=parameters)
            token = current_task.set(task_id)
            try:
                with _call_scope(scope):
                    for attempt in range(settings.max_retouch + 1):
                        try:
                            image = generate_image(photos, slot_prompts[slot], seed, references)
                            value = {"image": image, "seed": scope.effective_seed, "engine": scope.engine}
                            with lock:
                                results[slot] = value
                            return {"slot": slot, "seed": value["seed"], "engine": value["engine"]}
                        except ImageCallFailure as error:
                            if not error.retryable or attempt >= settings.max_retouch:
                                raise
                            seed = secrets.randbelow(2**31)
                raise ImageCallFailure("生成未完成")
            except Exception as error:
                with lock:
                    errors.append(error)
                raise
            finally:
                current_task.reset(token)

        system = Path(__file__).with_name("prompts").joinpath("agent.md").read_text("utf-8")
        try:
            run_pi({
                "system": system, "model": settings.seedream_model,
                "max_steps": settings.max_agent_steps, "parallelism": count,
                "jobs": [{"slot": slot, "seed": seeds[slot]} for slot in range(count)],
            }, None, execute, timeout=settings.image_timeout_seconds)
        except ModuleError:
            if errors and isinstance(errors[0], ModuleError):
                raise errors[0]
            raise
        if len(results) != count:
            raise ModuleError("GENERATION_FAILED", "部分候选图未生成成功，请稍后重试")
        engine = "+".join(sorted({item["engine"] for item in results.values()}))

    candidates = []
    try:
        for slot in range(count):
            item = results[slot]
            candidates.append({
                "image_id": f"img_{used + slot + 1}",
                "url": save_image(item["image"], "candidate"), "seed": item["seed"],
            })
    except Exception:
        raise ModuleError("GENERATION_FAILED", "候选图保存失败，请稍后重试")
    step_text = f"正在生成 {count} 张样片" if stage == "sample" else f"正在生成 {count} 张婚礼套图"
    return {
        "candidates": candidates,
        "generation": {
            "engine": engine, "workflow": workflow,
            "seconds": round(time.monotonic() - started, 2),
            "total_images": used + len(candidates),
            "stage": stage,
        },
        "step_text": step_text,
    }

