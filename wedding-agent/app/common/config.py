"""全局配置（框架维护）。

所有密钥和可调参数都从这里读，模块里不要写死。值来自项目根目录的 .env（参考 .env.example）。
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def _str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value and value.strip() else default


def _float(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value and value.strip() else default


def _list(name: str) -> list[str]:
    return [item.strip() for item in _str(name).split(",") if item.strip()]


@dataclass
class Settings:
    # 运行模式
    fake: bool
    real_modules: list[str]
    fake_fail_first_check: bool
    fake_delay_seconds: float
    # 服务
    public_base_url: str
    cors_origins: list[str]
    storage_dir: Path
    retention_days: int
    # 流程上限
    max_question_rounds: int
    max_retouch: int
    max_user_redo: int
    max_agent_steps: int
    max_reference_images: int
    candidates_per_round: int
    max_images_per_task: int
    image_timeout_seconds: int
    face_sim_threshold: float
    # 大模型
    llm_base_url: str
    llm_api_key: str
    llm_model_agent: str
    llm_model_cheap: str
    llm_model_vision: str
    llm_timeout_seconds: int
    # 生图服务
    runninghub_api_key: str
    runninghub_workflow_id: str
    seedream_model: str

    def fake_for(self, module: str) -> bool:
        """这个模块是否用示例数据。FAKE=1 时默认全部用示例数据，REAL_MODULES 里列出的模块除外。"""
        return self.fake and module not in self.real_modules


def load_settings() -> Settings:
    storage = _str("STORAGE_DIR")
    return Settings(
        fake=_bool("FAKE", True),
        real_modules=_list("REAL_MODULES"),
        fake_fail_first_check=_bool("FAKE_FAIL_FIRST_CHECK", False),
        fake_delay_seconds=_float("FAKE_DELAY_SECONDS", 0),
        public_base_url=_str("PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/"),
        cors_origins=_list("CORS_ORIGINS") or ["http://localhost:5173"],
        storage_dir=Path(storage) if storage else ROOT / "storage",
        retention_days=_int("RETENTION_DAYS", 7),
        max_question_rounds=_int("MAX_QUESTION_ROUNDS", 2),
        max_retouch=_int("MAX_RETOUCH", 2),
        max_user_redo=_int("MAX_USER_REDO", 2),
        max_agent_steps=_int("MAX_AGENT_STEPS", 6),
        max_reference_images=_int("MAX_REFERENCE_IMAGES", 2),
        candidates_per_round=_int("CANDIDATES_PER_ROUND", 4),
        max_images_per_task=_int("MAX_IMAGES_PER_TASK", 16),
        image_timeout_seconds=_int("IMAGE_TIMEOUT_SECONDS", 120),
        face_sim_threshold=_float("FACE_SIM_THRESHOLD", 0.5),
        llm_base_url=_str("LLM_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
        llm_api_key=_str("LLM_API_KEY"),
        llm_model_agent=_str("LLM_MODEL_AGENT"),
        llm_model_cheap=_str("LLM_MODEL_CHEAP"),
        llm_model_vision=_str("LLM_MODEL_VISION"),
        llm_timeout_seconds=_int("LLM_TIMEOUT_SECONDS", 60),
        runninghub_api_key=_str("RUNNINGHUB_API_KEY"),
        runninghub_workflow_id=_str("RUNNINGHUB_WORKFLOW_ID"),
        seedream_model=_str("SEEDREAM_MODEL"),
    )


settings = load_settings()
