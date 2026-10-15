"""工单定义（框架维护，其他人只读）。

工单是所有模块共用的一张表：每个模块只读自己需要的字段，只写《小囍模块接入规范》
「工单字段」里「谁写」一栏是自己的字段。要改字段，先改文档，再由框架同学改这里。
"""

from __future__ import annotations

from typing import Optional, TypedDict

from pydantic import BaseModel, ConfigDict, Field


UNDECIDED = "undecided"  # 需求单里造型／镜头字段的"还没定"
DEPRECATED_BRIEF_FIELDS = ("style", "background", "makeup", "outfit_bride", "outfit_groom", "expression", "pose")
PHOTO_GROUP_MIN, PHOTO_GROUP_MAX = 1, 10


class Brief(BaseModel):
    """需求单，由小囍生成。

    工单里以 dict 保存：用 Brief(**state["brief"]) 得到对象，用 brief.model_dump() 存回去。
    不允许出现下面没有的字段；要加字段先改《小囍模块接入规范》，再由框架同学改这里。
    """

    model_config = ConfigDict(extra="forbid")

    intent: str = "photo_and_materials"
    # 下面 7 个造型／镜头字段暂时保留（修图师还在读），小囍不再填写，妆造师、摄影师也不要读。
    # 默认值是 UNDECIDED（"还没定"）；修图师改完后由框架删除。
    style: str = UNDECIDED
    background: str = UNDECIDED
    makeup: str = UNDECIDED
    outfit_bride: str = UNDECIDED
    outfit_groom: str = UNDECIDED
    expression: str = UNDECIDED
    pose: str = UNDECIDED
    heights_cm: list[int] = Field(default_factory=list)  # 两人身高，例如 [175, 162]
    body_types: list[str] = Field(default_factory=list)
    keep_features: list[str] = Field(default_factory=list)  # 必须保留的特征，例如 "女生的眼镜"
    beautify: str = "none"  # none 不美化；light 轻度美化，只有用户主动选择才能是 light
    materials: list[str] = Field(default_factory=lambda: ["invitation", "welcome_poster", "led_screen"])
    invitation: dict = Field(default_factory=dict)  # {"names": ..., "date": ..., "place": ...}
    missing: list[str] = Field(default_factory=list)  # 还缺的字段；空列表表示资料齐了


class Consent(BaseModel):
    """任务级照片授权记录，不会被拼进生图提示词。"""

    model_config = ConfigDict(extra="forbid")

    authorization_scope: str = "generation_only"
    retention_days: int = Field(default=7, ge=0)
    allow_training: bool = False
    watermark: bool = True
    delete_original: bool = True
    confirmed: bool = False


class WeddingState(TypedDict, total=False):
    # 框架写
    task_id: str
    photo_urls: list[str]
    groom_photo_urls: list[str]
    bride_photo_urls: list[str]
    description: str
    consent: Optional[dict]
    answers: list[dict]  # 每条含 question_id、value 或 skipped，以及是谁问的 asker、第几轮 round
    question_rounds: dict  # 每位 agent 已经问了几轮，例如 {"intake": 1, "styling": 1}
    retry_count: int
    user_feedback: Optional[dict]  # 用户要求重做时的 image_id、reason、note
    sample_only: bool  # 用户在样片页选了"只要这一张"：跳过套图，直接用样片交付
    # 另外，任何模块都可以在返回值里带 step_text（给用户看的进度文案），框架转给前端，不写进工单

    # 小囍、妆造师、摄影师都可以写：要问用户的问题，框架负责暂停、收集回答
    questions: list[dict]

    # 主 agent（小囍）写
    brief: dict
    prompt: str  # 汇总妆造师和摄影师的方案后写的最终提示词（所有镜头共用的部分；没有 shot_prompts 时每张都用它）
    shot_prompts: list[dict]  # 可选：每个镜头的最终提示词，每项 {"slot": 0~8, "prompt": ...}；生图按 slot 取
    references: list[dict]  # 生图时带上的参考图，每张含 url、role
    identity: list[dict]  # 身份照清单（发图顺序），每项 {"url", "role": groom|bride|couple}；生图按它的顺序先发，再发 references
    message: str  # 揭幕寄语

    # 妆造师写（先和用户确认妆容、发型、服饰、配饰）
    look: dict  # {"text": 造型描述, "style": 风格编号, "references": [从资产库挑的参考图]}

    # 摄影师写（在妆造师之后，和用户确认互动、场景、季节、灯光）
    shot: dict  # {"text": 构图光线姿势描述, "pose": 姿势编号, "references": [从资产库挑的参考图]}
    # 可选：分镜表，每张套图一个镜头 {"slot", "pose", "framing"(景别), "scene", "text"}。
    # slot 0 同时用于样片；套图阶段 slot 0~8 各画一张。
    shots: list[dict]

    # 生图 agent 写
    candidates: list[dict]  # 每张含 image_id、url、seed
    generation: dict  # engine、workflow、seconds、total_images；stage 为 sample / set

    # 评测修图师写
    scores: list[dict]
    best_image_id: Optional[str]
    passed: bool
    retouch_plan: Optional[dict]  # {"target": look/shot/prompt/generate/none, "patch": 修改说明, "image_id": 换用的候选}

    # 资产库写
    previews: list[dict]
    deliverables: dict
