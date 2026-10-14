"""批量诊断现有工单；默认 mock，显式 live 后仍校验每个样本授权。"""

import argparse
import json
import sys
from pathlib import Path

from app.common.errors import ModuleError

from .diagnostics import diagnose, readiness
from .reporting import run_metadata, save_report, timestamp


def run_batch(manifest: dict, *, mode: str = "mock", include_retouch: bool = True) -> dict:
    if not isinstance(manifest, dict) or not isinstance(manifest.get("samples"), list) or not manifest["samples"]:
        raise ModuleError("FILE_INVALID", "批量输入需要非空 samples 列表")
    if mode not in {"mock", "live"}:
        raise ModuleError("FILE_INVALID", "批量运行模式不正确")
    metadata = run_metadata(mode, manifest.get("dataset_version"))
    entries = manifest["samples"]
    if any(not isinstance(entry, dict) or not isinstance(entry.get("sample_id"), str) or not entry["sample_id"].strip() for entry in entries):
        raise ModuleError("FILE_INVALID", "每个样本必须有匿名 sample_id")
    ids = [entry["sample_id"] for entry in entries]
    if len(ids) != len(set(ids)):
        raise ModuleError("FILE_INVALID", "样本编号重复，不能生成可对齐的报告")
    started_at = timestamp()
    records = []
    for entry in entries:
        try:
            if mode == "live" and include_retouch and not readiness()["agent_configured"]:
                raise ModuleError("GENERATION_FAILED", "包含返工的批量评测需要先配置 agent；仅质检可使用 --check-only")
            record = diagnose(entry, mode=mode, stage="check", dataset_version=manifest["dataset_version"])
            if include_retouch and "error" not in record and (not record["result"]["passed"] or entry["state"].get("user_feedback")):
                # 只合并当前运行的分数，不修改输入工单或伪造合格图。
                revised = {**entry, "state": {**entry["state"], **record["result"]}}
                followup = diagnose(revised, mode=mode, stage="retouch", dataset_version=manifest["dataset_version"])
                if "error" in followup:
                    record["error"] = followup["error"]
                    record["failed_stage"] = "retouch"
                else:
                    record["retouch_plan"] = followup["retouch_plan"]
                timing = record["timing"]
                timing["retouch_seconds"] = followup["timing"]["retouch_seconds"]
                for key in ("model_invocations", "simulated_invocations", "request_budget_upper_bound", "model_call_seconds", "face_comparisons", "simulated_face_comparisons", "face_comparison_seconds"):
                    timing[key] += followup["timing"][key]
                record["finished_at"] = followup["finished_at"]
            if "error" in record and "failed_stage" not in record:
                record["failed_stage"] = "check"
        except ModuleError as error:
            record = {"sample_id": entry["sample_id"], "metadata": metadata, "error": {"code": error.code, "message": error.message}, "failed_stage": "preflight"}
        records.append(record)
    # 可直接将 predictions 列表作为 evaluation／regression 输入；有错误的记录须先处理。
    return {
        "started_at": started_at,
        "finished_at": timestamp(),
        "metadata": metadata,
        "summary": {"samples": len(records), "succeeded": sum("error" not in record for record in records), "failed": sum("error" in record for record in records)},
        "predictions": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--mode", choices=["mock", "live"], default="mock")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        report = run_batch(manifest, mode=args.mode, include_retouch=not args.check_only)
        if args.output:
            save_report(args.output, report)
        else:
            sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        return int(report["summary"]["failed"] > 0)
    except (OSError, ValueError):
        sys.stderr.write("FILE_INVALID: 无法读取有效的批量输入 JSON\n")
    except ModuleError as error:
        sys.stderr.write(f"{error.code}: {error.message}\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
