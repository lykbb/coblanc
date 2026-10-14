"""本模块统一的一次性结构化调用。提示词和响应均不写日志。"""

from pathlib import Path
from dataclasses import dataclass, field
from time import monotonic
from math import isfinite

from pydantic import BaseModel

from app.common.config import settings
from app.common.errors import ModuleError
from app.common.llm import get_llm

PROMPTS = Path(__file__).parent / "prompts"


@dataclass
class CallStats:
    """单次诊断持有的调用记录，不进入工单，也不包含图片或模型响应。"""

    calls: list[dict] = field(default_factory=list)

    def record(self, kind: str, seconds: float, budget: int, success: bool, simulated: bool = False) -> None:
        self.calls.append({"kind": kind, "seconds": seconds, "request_budget_upper_bound": budget, "success": success, "simulated": simulated})

    def summary(self) -> dict:
        return {
            "model_invocations": sum(not call["simulated"] and call["kind"] != "face" for call in self.calls),
            "simulated_invocations": sum(call["simulated"] and call["kind"] != "face" for call in self.calls),
            "face_comparisons": sum(not call["simulated"] and call["kind"] == "face" for call in self.calls),
            "simulated_face_comparisons": sum(call["simulated"] and call["kind"] == "face" for call in self.calls),
            "request_budget_upper_bound": sum(call["request_budget_upper_bound"] for call in self.calls),
            "model_call_seconds": sum(call["seconds"] for call in self.calls if call["kind"] != "face"),
            "face_comparison_seconds": sum(call["seconds"] for call in self.calls if call["kind"] == "face"),
        }


def read_prompt(name: str) -> str:
    try:
        return (PROMPTS / name).read_text(encoding="utf-8")
    except OSError:
        raise ModuleError("GENERATION_FAILED", "质检提示词文件无法读取，请联系维护人员") from None


def structured_call(kind: str, schema: type[BaseModel], messages: list, stats: CallStats | None = None) -> BaseModel:
    if isinstance(settings.max_agent_steps, bool) or not isinstance(settings.max_agent_steps, int) or settings.max_agent_steps < 1 or isinstance(settings.llm_timeout_seconds, bool) or not isinstance(settings.llm_timeout_seconds, (float, int)) or not isfinite(settings.llm_timeout_seconds) or settings.llm_timeout_seconds <= 0:
        raise ModuleError("GENERATION_FAILED", "模型调用上限或超时配置无效")
    start = monotonic()
    budget = 0
    invoked = success = False
    try:
        model = get_llm(kind)
        if isinstance(model.max_retries, bool) or not isinstance(model.max_retries, int) or model.max_retries < 0:
            raise ModuleError("GENERATION_FAILED", "模型重试配置无效")
        # 公共入口自带有限 SDK 重试；总请求预算不能超过公共步骤上限。
        if model.max_retries + 1 > settings.max_agent_steps:
            raise ModuleError("GENERATION_FAILED", "模型重试次数超过允许的调用上限")
        runnable = model.with_structured_output(schema, method="function_calling")
        budget = model.max_retries + 1
        invoked = True
        response = runnable.invoke(messages)
        result = schema.model_validate(response)
        success = True
        return result
    except ModuleError:
        raise
    except Exception:
        # 不附带原始异常，避免供应商错误内容泄露图片、密钥或用户意见。
        raise ModuleError("GENERATION_FAILED", "质检模型调用失败或输出格式不正确，请检查模型配置后重试") from None
    finally:
        if stats is not None and invoked:
            stats.record(kind, monotonic() - start, budget, success)
