"""按资产库地址独立诊断 check／vision／face／retouch，默认 mock。"""

import argparse
import json
import sys
from pathlib import Path
from time import monotonic

from app.common.config import settings
from app.common.errors import ModuleError
from app.modules.assets import load_image

from .face_compare import compare_faces, provider_metadata
from .model_calls import CallStats
from .node import _candidates
from .quality import face_threshold, passes, validate_scores, validate_feedback
from .real import check_real, propose_retouch
from .reporting import run_metadata, save_report, timestamp
from .synthetic import make_couple_png
from .vision import inspect_candidates
from .asset_inputs import read_images
from app.common.llm import llm_config, llm_ready


def readiness() -> dict:
    return {"vision_configured": llm_ready("vision"), "agent_configured": llm_ready("agent"), "face_provider_connected": provider_metadata()["connected"]}


def _live_authorization(entry: dict, stage: str) -> None:
    consent = entry.get("consent")
    if not isinstance(consent, dict) or consent.get("both_people_authorized") is not True or not isinstance(consent.get("evidence_reference"), str) or not consent["evidence_reference"].strip():
        raise ModuleError("PHOTO_INVALID", "真实诊断需要双方授权记录及凭据编号")
    if stage != "face":
        services = consent.get("approved_services")
        if not isinstance(services, list) or llm_config("vision")["base_url"] not in services:
            raise ModuleError("GENERATION_FAILED", "当前模型服务不在此样本的获准服务名单中")
        config = readiness()
        if stage in {"vision", "check"} and not config["vision_configured"]:
            raise ModuleError("GENERATION_FAILED", "视觉模型配置不完整")
        if stage == "retouch" and not config["agent_configured"]:
            raise ModuleError("GENERATION_FAILED", "返工模型配置不完整")
    if settings.fake_for("review"):
        raise ModuleError("GENERATION_FAILED", "review 仍处于 fake 模式；真实调用前请配置 REAL_MODULES=review")
    if stage in {"check", "face"} and not readiness()["face_provider_connected"]:
        raise ModuleError("GENERATION_FAILED", "人脸服务尚未接入，不能运行完整真实质检或人脸诊断")


def diagnose(entry: dict, *, mode: str = "mock", stage: str = "check", image_id: str | None = None, dataset_version: str = "diagnostic_v1") -> dict:
    if mode not in {"mock", "live"} or stage not in {"check", "vision", "face", "retouch"}:
        raise ModuleError("FILE_INVALID", "诊断模式或步骤不正确")
    if not isinstance(entry, dict) or not isinstance(entry.get("sample_id"), str) or not entry["sample_id"].strip() or not isinstance(entry.get("state"), dict):
        raise ModuleError("FILE_INVALID", "诊断输入需要匿名 sample_id 和现有工单格式的 state")
    state = entry["state"]
    face_threshold()
    candidates = _candidates(state)
    if image_id is not None:
        candidates = [candidate for candidate in candidates if candidate["image_id"] == image_id]
        if not candidates:
            raise ModuleError("FILE_INVALID", "指定图片不在当前候选中")
        if stage == "retouch":
            raise ModuleError("FILE_INVALID", "返工决策需要整轮评分，不能截取单张")
    if mode == "live":
        _live_authorization(entry, stage)
    stats = CallStats()
    metadata = run_metadata(mode, dataset_version)
    report = {"sample_id": entry["sample_id"], "stage": stage, "metadata": metadata, "started_at": timestamp(), "source": "synthetic_fixture" if mode == "mock" else "asset_library", "timing": {}}
    image = make_couple_png() if mode == "mock" else None
    loader = (lambda _: image) if mode == "mock" else load_image
    comparator = (lambda *_: [0.9, 0.88]) if mode == "mock" else compare_faces

    def mock_call(kind, schema, messages, stats=None):
        if kind == "vision":
            value = {"findings": [{"image_id": candidate["image_id"], "body_ok": True, "hands_ok": True, "subject_count_ok": True, "text_ok": True, "requirements_ok": True, "assessable": True, "issues": []} for candidate in candidates]}
        else:
            payload = json.loads(messages[1][1])
            feedback = payload["user_feedback"]
            target = {"face": "generate", "hands": "generate", "body": "shot", "style": "look", "other": "prompt"}[feedback.get("reason") or "other"] if feedback else payload["required_target_without_feedback"]
            value = {"target": target, "patch": "模拟建议：保留人物特征并修正已报告问题", "image_id": payload["qualified_image_ids"][0] if target == "none" else None}
        if stats is not None:
            stats.record(kind, 0.0, 0, True, simulated=True)
        return schema.model_validate(value)

    caller = mock_call if mode == "mock" else None
    start = monotonic()
    try:
        if stage == "check":
            scores = validate_scores(check_real(state, candidates, caller=caller, comparator=comparator, loader=loader, stats=stats, simulated=mode == "mock"), candidates, complete=True)
            qualified = [score for score in scores if passes(score)]
            report["result"] = {"scores": scores, "best_image_id": max(qualified, key=lambda score: score["total"])["image_id"] if qualified else None, "passed": bool(qualified)}
        elif stage == "retouch":
            scores = validate_scores(state.get("scores") or [], candidates, complete=True)
            feedback = validate_feedback(state.get("user_feedback"), candidates)
            report["retouch_plan"] = propose_retouch(state, scores, feedback, {score["image_id"] for score in scores if passes(score)}, caller=caller, stats=stats)
        else:
            source, images = read_images(state, candidates, loader=loader)
            if stage == "vision":
                findings = inspect_candidates(source, images, state.get("brief") or {}, caller=caller, stats=stats)
                report["visual_findings"] = [finding.model_dump() for finding in findings.values()]
            else:
                results = []
                for candidate_id, data in images:
                    started = monotonic()
                    success = False
                    try:
                        score = validate_scores([{"image_id": candidate_id, "face_sim": comparator(source, data), "body_ok": True, "hands_ok": True, "issues": [], "total": 0.0}], [{"image_id": candidate_id}], complete=True)[0]
                        results.append({"image_id": candidate_id, "face_sim": score["face_sim"]})
                        success = True
                    except ModuleError:
                        raise
                    except Exception:
                        raise ModuleError("GENERATION_FAILED", "人脸诊断服务调用失败，请稍后重试")
                    finally:
                        stats.record("face", monotonic() - started, 0, success, simulated=mode == "mock")
                report["face_scores"] = results
    except ModuleError as error:
        report["error"] = {"code": error.code, "message": error.message}
    report["timing"]["retouch_seconds" if stage == "retouch" else "check_seconds"] = monotonic() - start
    report["timing"].update(stats.summary())
    report["finished_at"] = timestamp()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("entry", type=Path)
    parser.add_argument("--mode", choices=["mock", "live"], default="mock")
    parser.add_argument("--stage", choices=["check", "vision", "face", "retouch"], default="check")
    parser.add_argument("--image-id")
    parser.add_argument("--dataset-version", default="diagnostic_v1")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        entry = json.loads(args.entry.read_text(encoding="utf-8"))
        report = diagnose(entry, mode=args.mode, stage=args.stage, image_id=args.image_id, dataset_version=args.dataset_version)
        if args.output:
            save_report(args.output, report)
        else:
            sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        return int("error" in report)
    except (OSError, ValueError):
        sys.stderr.write("FILE_INVALID: 无法读取有效的诊断 JSON\n")
    except ModuleError as error:
        sys.stderr.write(f"{error.code}: {error.message}\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
