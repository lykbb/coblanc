"""离线报告元数据和文件写入，不改工单，不记录照片或密钥。"""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from app.common.config import settings
from app.common.llm import model_name
from app.common.errors import ModuleError

from .model_calls import read_prompt
from .face_compare import provider_metadata


def run_metadata(mode: str, dataset_version: str) -> dict:
    if not isinstance(dataset_version, str) or not dataset_version.strip():
        raise ModuleError("FILE_INVALID", "请为运行报告提供非空数据集版本")
    prompts = read_prompt("vision.md") + read_prompt("retouch.md")
    provider = provider_metadata()
    return {
        "mode": mode,
        "dataset_version": dataset_version,
        "face_model": "synthetic_fixture" if mode == "mock" else provider["face_model"],
        "score_scale": "synthetic_0_1" if mode == "mock" else provider["score_scale"],
        "vision_model": "mock" if mode == "mock" else model_name("vision") or "unconfigured",
        "agent_model": "mock" if mode == "mock" else model_name("agent") or "unconfigured",
        "prompt_version": hashlib.sha256(prompts.encode("utf-8")).hexdigest(),
        "face_sim_threshold": settings.face_sim_threshold,
    }


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_report(path: Path, report: object) -> None:
    """不覆盖已有报告；新文件仅当前用户可读写。"""
    try:
        content = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
    except (OSError, TypeError, ValueError):
        raise ModuleError("FILE_INVALID", "报告无法保存：请检查输出目录，并使用尚不存在的文件名") from None
