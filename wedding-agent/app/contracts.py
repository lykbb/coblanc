"""模块接口契约（框架维护）：每个对外函数允许写哪些工单字段、每个字段长什么样。

流程每跑完一个模块都会用 validate_update 检查一次；组员替换实现后运行
uv run pytest tests/test_contracts.py，全部通过就能直接接入。
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from app.state import Brief


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Reference(_Strict):
    url: str
    role: Literal["style", "outfit", "makeup", "pose", "background"]


class Look(_Strict):
    text: str
    style: str
    references: list[Reference] = Field(default_factory=list)


class Shot(_Strict):
    text: str
    pose: str
    references: list[Reference] = Field(default_factory=list)


class Candidate(_Strict):
    image_id: str
    url: str
    seed: int


class Generation(_Strict):
    engine: str
    workflow: str
    seconds: float
    total_images: int


class Score(_Strict):
    image_id: str
    face_sim: Annotated[list[float], Field(min_length=2, max_length=2)]
    body_ok: bool
    hands_ok: bool
    issues: list[str]
    total: float


class RetouchPlan(_Strict):
    target: Literal["look", "shot", "prompt", "generate", "none"]
    patch: str
    image_id: str | None = None


class Option(_Strict):
    value: str
    label: str
    image: str | None = None


class Question(_Strict):
    question_id: str
    type: Literal["single_choice", "multi_choice", "text", "upload"]
    title: str
    options: list[Option] = Field(default_factory=list)
    recommended: Any = None
    placeholder: str | None = None
    allow_skip: bool = True


class Preview(_Strict):
    image_id: str
    url: str
    is_best: bool


class Deliverables(BaseModel):
    model_config = ConfigDict(extra="allow")  # 其余键是物料名，值是地址
    photo: str


FIELD_TYPES = {
    "brief": Brief,
    "questions": list[Question],
    "message": str,
    "look": Look,
    "shot": Shot,
    "prompt": str,
    "references": list[Reference],
    "candidates": list[Candidate],
    "generation": Generation,
    "scores": list[Score],
    "best_image_id": str | None,
    "passed": bool,
    "retouch_plan": RetouchPlan,
    "previews": list[Preview],
    "deliverables": Deliverables,
    "step_text": str,
}

# 对外函数名 → 允许写的工单字段（step_text 任何模块都可以写）
MODULE_WRITES = {
    "intake": {"brief", "questions"},
    "compose": {"prompt", "references"},
    "reveal": {"message"},
    "style": {"look", "questions"},
    "frame": {"shot", "questions"},
    "generate": {"candidates", "generation"},
    "check": {"scores", "best_image_id", "passed"},
    "retouch": {"retouch_plan"},
    "make_previews": {"previews"},
    "package": {"deliverables"},
}

# 每次调用都必须返回的字段（问用户的 questions 是可选的；问问题时也要先给出一版主要输出，
# 这样用户不回答或轮数用完时，流程照样能往下走）
MODULE_REQUIRES = {
    "intake": {"brief"},
    "compose": {"prompt", "references"},
    "reveal": {"message"},
    "style": {"look"},
    "frame": {"shot"},
    "generate": {"candidates", "generation"},
    "check": {"scores", "best_image_id", "passed"},
    "retouch": {"retouch_plan"},
    "make_previews": {"previews"},
    "package": {"deliverables"},
}

_ADAPTERS = {key: TypeAdapter(value) for key, value in FIELD_TYPES.items()}


class ContractError(Exception):
    """模块的返回值不符合契约。"""


def validate_update(function: str, update: dict) -> None:
    if not isinstance(update, dict):
        raise ContractError(f"{function} 必须返回 dict，实际返回了 {type(update).__name__}")
    allowed = MODULE_WRITES[function] | {"step_text"}
    extra = sorted(set(update) - allowed)
    if extra:
        raise ContractError(f"{function} 返回了不允许写的字段 {extra}，允许的是 {sorted(allowed)}")
    missing = sorted(MODULE_REQUIRES[function] - set(update))
    if missing:
        raise ContractError(f"{function} 少返回了必须有的字段 {missing}")
    for key, value in update.items():
        try:
            _ADAPTERS[key].validate_python(value)
        except Exception as error:
            raise ContractError(f"{function} 写的 {key} 格式不对：{error}") from error
        if key == "deliverables" and not all(isinstance(url, str) for url in value.values()):
            raise ContractError(f"{function} 写的 deliverables 里每个值都必须是地址字符串")
