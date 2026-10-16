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


def _chat(suffix: str, default: str = "") -> str:
    """读 CHAT_<suffix>；没填时兼容旧名 DEEPSEEK_<suffix>。"""
    return _str(f"CHAT_{suffix}") or _str(f"DEEPSEEK_{suffix}") or default


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
    # 任务状态和流程检查点（不在 storage_dir 里，因为 storage_dir 通过 /files 对外公开）
    state_dir: Path
    retention_days: int
    # 流程上限
    max_question_rounds: int
    max_retouch: int
    max_user_redo: int
    max_agent_steps: int
    max_reference_images: int
    sample_candidates: int  # 第一轮只出 1 张样片
    set_candidates: int  # 样片确认后出 9 张套图
    candidates_per_round: int  # 一轮最多几张，等于样片和套图里较大的那个，修图师用它检查候选数量
    max_images_per_task: int  # 每个任务最多生成几张（含重做），到上限就失败，防止费用失控
    image_timeout_seconds: int
    face_sim_threshold: float
    # 大模型
    llm_base_url: str
    llm_api_key: str
    llm_model_agent: str
    llm_model_cheap: str
    llm_model_vision: str
    llm_timeout_seconds: int
    # 对话/看图模型（任意兼容 OpenAI 接口的服务）。填了 CHAT_API_KEY 就优先用它，生图仍用 Seedream
    chat_api_key: str
    chat_base_url: str
    chat_model: str
    chat_model_agent: str
    chat_model_cheap: str
    chat_model_vision: str
    chat_thinking: bool  # CHAT_THINKING=1 才打开思考模式；默认关，结构化输出更稳更快
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
        state_dir=Path(_str("STATE_DIR")) if _str("STATE_DIR") else (Path(storage + "-state") if storage else ROOT / "state"),
        retention_days=_int("RETENTION_DAYS", 7),
        max_question_rounds=_int("MAX_QUESTION_ROUNDS", 2),
        max_retouch=_int("MAX_RETOUCH", 2),
        max_user_redo=_int("MAX_USER_REDO", 2),
        max_agent_steps=_int("MAX_AGENT_STEPS", 6),
        max_reference_images=_int("MAX_REFERENCE_IMAGES", 2),
        sample_candidates=_int("SAMPLE_CANDIDATES", 1),
        set_candidates=_int("SET_CANDIDATES", 9),
        candidates_per_round=max(_int("SAMPLE_CANDIDATES", 1), _int("SET_CANDIDATES", 9)),
        max_images_per_task=_int("MAX_IMAGES_PER_TASK", 30),
        image_timeout_seconds=_int("IMAGE_TIMEOUT_SECONDS", 120),
        face_sim_threshold=_float("FACE_SIM_THRESHOLD", 0.5),
        llm_base_url=_str("LLM_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
        llm_api_key=_str("LLM_API_KEY"),
        llm_model_agent=_str("LLM_MODEL_AGENT"),
        llm_model_cheap=_str("LLM_MODEL_CHEAP"),
        llm_model_vision=_str("LLM_MODEL_VISION"),
        llm_timeout_seconds=_int("LLM_TIMEOUT_SECONDS", 60),
        chat_api_key=_chat("API_KEY"),
        chat_base_url=_chat("BASE_URL", "https://api.deepseek.com"),
        chat_model=_chat("MODEL", "deepseek-flash"),
        chat_model_agent=_chat("MODEL_AGENT"),
        chat_model_cheap=_chat("MODEL_CHEAP"),
        chat_model_vision=_chat("MODEL_VISION"),
        chat_thinking=_bool("CHAT_THINKING", False),
        runninghub_api_key=_str("RUNNINGHUB_API_KEY"),
        runninghub_workflow_id=_str("RUNNINGHUB_WORKFLOW_ID"),
        seedream_model=_str("SEEDREAM_MODEL"),
    )


settings = load_settings()
