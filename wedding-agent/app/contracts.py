"""模块接口契约（框架维护）：每个对外函数允许写哪些工单字段、每个字段长什么样。

流程每跑完一个模块都会用 validate_update 检查一次；组员替换实现后运行
uv run pytest tests/test_contracts.py，全部通过就能直接接入。
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from app.state import PHOTO_GROUP_MAX, PHOTO_GROUP_MIN, Brief, Consent


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Reference(_Strict):
    url: str
    role: Literal["style", "outfit", "makeup", "pose", "background"]


class IdentityPhoto(_Strict):
    """身份照清单的一项（按发图顺序）。"""

    url: str
    role: Literal["groom", "bride", "couple"]


class Look(_Strict):
    text: str
    style: str
    references: list[Reference] = Field(default_factory=list)


class Shot(_Strict):
    text: str
    pose: str
    references: list[Reference] = Field(default_factory=list)
    # 摄影师参考过的风格案例编号（PR #14 数据，仅用于追溯，不展示给用户）
    style_cases: list[str] = Field(default_factory=list)


class ShotPlan(_Strict):
    """分镜表里的一个镜头（摄影师写）。slot 从 0 开始，0 号同时用于样片。"""

    slot: int = Field(ge=0)
    pose: str
    framing: str  # 景别，例如 全身 / 半身 / 特写
    scene: str
    text: str  # 这个镜头的构图、姿势、互动描述，会拼进这一张的提示词


class ShotPrompt(_Strict):
    """某个镜头的最终提示词（小囍 compose 写）。"""

    slot: int = Field(ge=0)
    prompt: str = Field(min_length=1)


class Candidate(_Strict):
    image_id: str
    url: str
    seed: int


class Generation(_Strict):
    engine: str
    workflow: str
    seconds: float
    total_images: int
    # 新流程：sample 为 1 张样片，set 为用户确认后的 9 张套图。
    # 可选是为了让历史工单（没有 stage 字段）继续通过契约校验。
    stage: Literal["sample", "set"] | None = None


class Score(_Strict):
    image_id: str
    face_sim: Annotated[list[float], Field(min_length=2, max_length=2)]
    body_ok: bool
    hands_ok: bool
    issues: list[str]
    total: float
    face_compare: Literal["done", "skipped"] = "done"  # skipped：人脸比对服务未接入，只做了视觉模型检查


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
    # 套图阶段交付的 9 张高清婚纱照；旧任务仍会返回只有一项的列表。
    photos: list[str] = Field(default_factory=list)


FIELD_TYPES = {
    "brief": Brief,
    "consent": Consent,
    "groom_photo_urls": list[str],
    "bride_photo_urls": list[str],
    "photo_urls": list[str],
    "questions": list[Question],
    "message": str,
    "look": Look,
    "shot": Shot,
    "shots": list[ShotPlan],
    "prompt": str,
    "shot_prompts": list[ShotPrompt],
    "references": list[Reference],
    "identity": list[IdentityPhoto],
    "candidates": list[Candidate],
    "generation": Generation,
    "scores": list[Score],
    "best_image_id": Optional[str],
    "passed": bool,
    "retouch_plan": RetouchPlan,
    "previews": list[Preview],
    "deliverables": Deliverables,
    "step_text": str,
}

# 对外函数名 → 允许写的工单字段（step_text 任何模块都可以写）
MODULE_WRITES = {
    "intake": {"brief", "questions", "consent", "groom_photo_urls", "bride_photo_urls", "photo_urls", "identity"},
    "compose": {"prompt", "references", "shot_prompts", "identity"},
    "reveal": {"message"},
    "style": {"look", "questions"},
    "frame": {"shot", "shots", "questions"},
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


PHOTO_FIELDS = ("groom_photo_urls", "bride_photo_urls", "photo_urls")


def _check_photos(function: str, update: dict, state: dict | None) -> None:
    """照片字段：每个地址是非空字符串；分组任务每组 1～10 张，photo_urls 必须等于新郎 + 新娘。

    state 是模块运行前的工单，用来补齐本次没返回的照片字段；不传时只按本次返回的字段检查。
    """
    if not any(key in update for key in PHOTO_FIELDS):
        return
    merged = {key: (state or {}).get(key) for key in PHOTO_FIELDS}
    merged.update({key: update[key] for key in PHOTO_FIELDS if key in update})
    for key, urls in merged.items():
        if urls is not None and any(not isinstance(url, str) or not url.strip() for url in urls):
            raise ContractError(f"{function} 写的 {key} 里每一项都必须是非空的地址字符串")
    groom, bride, photos = merged["groom_photo_urls"], merged["bride_photo_urls"], merged["photo_urls"]
    if groom or bride:
        for key, urls in (("groom_photo_urls", groom), ("bride_photo_urls", bride)):
            if not urls or not PHOTO_GROUP_MIN <= len(urls) <= PHOTO_GROUP_MAX:
                raise ContractError(f"{function} 写的 {key} 必须有 {PHOTO_GROUP_MIN}～{PHOTO_GROUP_MAX} 张")
        if photos is None or list(photos) != list(groom) + list(bride):
            raise ContractError(f"{function} 写的照片字段不一致：分组任务的 photo_urls 必须等于新郎照片加新娘照片")
    elif photos is not None and not photos:
        raise ContractError(f"{function} 写的 photo_urls 不能为空")


def validate_update(function: str, update: dict, state: dict | None = None) -> None:
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
        if key == "deliverables":
            invalid = [name for name, item in value.items() if not isinstance(item, str) and not (
                name == "photos" and isinstance(item, list) and all(isinstance(url, str) for url in item)
            )]
            if invalid:
                raise ContractError(f"{function} 写的 deliverables 中 {invalid} 必须是地址字符串或 photos 地址列表")
    for key in ("shots", "shot_prompts"):
        slots = [item["slot"] for item in update.get(key) or []]
        if len(slots) != len(set(slots)):
            raise ContractError(f"{function} 写的 {key} 里 slot 不能重复")
    _check_photos(function, update, state)
