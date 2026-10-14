"""独立视觉／返工联调。默认 mock；live 只发送程序内生成的几何示意图。"""

import argparse
import hashlib
import json
import sys
from time import monotonic

from app.common.config import settings
from app.common.errors import ModuleError

from .model_calls import CallStats, read_prompt
from .real import propose_retouch
from .synthetic import make_couple_png
from .vision import inspect_candidates


def run_smoke(mode: str = "mock", stage: str = "all") -> dict:
    if mode not in {"mock", "live"} or stage not in {"vision", "retouch", "all"}:
        raise ModuleError("FILE_INVALID", "联调模式或步骤不正确")
    if mode == "live" and settings.fake_for("review"):
        raise ModuleError("GENERATION_FAILED", "review 仍处于 fake 模式；真实联调前请配置 REAL_MODULES=review")
    if mode == "live" and (not settings.llm_api_key or (stage in {"vision", "all"} and not settings.llm_model_vision) or (stage in {"retouch", "all"} and not settings.llm_model_agent)):
        raise ModuleError("GENERATION_FAILED", "独立真实联调缺少模型配置，请先由负责人配置现有模型入口")
    ids = [f"img_{i}" for i in range(1, settings.candidates_per_round + 1)]
    if not ids:
        raise ModuleError("GENERATION_FAILED", "候选张数配置必须为正数")
    stats = CallStats()

    def mock_call(kind, schema, messages, stats=None):
        if kind == "vision":
            value = {"findings": [{"image_id": image_id, "body_ok": True, "hands_ok": True, "subject_count_ok": True, "text_ok": True, "requirements_ok": True, "assessable": True, "issues": []} for image_id in ids]}
        else:
            value = {"target": "generate", "patch": "修正手部结构，保留原有身份特征", "image_id": None}
        if stats is not None:
            stats.record(kind, 0.0, 0, True, simulated=True)
        return schema.model_validate(value)

    caller = mock_call if mode == "mock" else None
    report = {"mode": mode, "synthetic_image": True, "face_service_used": False, "timing": {}}
    if stage in {"vision", "all"}:
        start = monotonic()
        image = make_couple_png()
        findings = inspect_candidates(image, [(image_id, image) for image_id in ids], {}, caller=caller, stats=stats)
        report["visual_findings"] = [value.model_dump() for value in findings.values()]
        report["timing"]["check_seconds"] = monotonic() - start
    if stage in {"retouch", "all"}:
        scores = [{"image_id": image_id, "face_sim": [0.9, 0.9], "body_ok": True, "hands_ok": False, "issues": ["手部结构异常"], "total": 0.9} for image_id in ids]
        start = monotonic()
        report["retouch_plan"] = propose_retouch({}, scores, {"image_id": ids[0], "reason": "hands", "note": "修正手部"}, set(), caller=caller, stats=stats)
        report["timing"]["retouch_seconds"] = monotonic() - start
    report["timing"].update(stats.summary())
    report["metadata"] = {
        "mode": mode,
        "vision_model": settings.llm_model_vision if mode == "live" else "mock",
        "agent_model": settings.llm_model_agent if mode == "live" else "mock",
        "face_model": "not_connected",
        "score_scale": "synthetic_0_1",
        "face_sim_threshold": settings.face_sim_threshold,
        "prompt_version": hashlib.sha256((read_prompt("vision.md") + read_prompt("retouch.md")).encode("utf-8")).hexdigest(),
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["mock", "live"], default="mock")
    parser.add_argument("--stage", choices=["vision", "retouch", "all"], default="all")
    args = parser.parse_args()
    try:
        report = run_smoke(args.mode, args.stage)
    except ModuleError as error:
        sys.stderr.write(f"{error.code}: {error.message}\n")
        return 1
    sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
