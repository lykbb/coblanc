"""工单定义（框架维护，其他人只读）。

工单是所有模块共用的一张表：每个模块只读自己需要的字段，只写《小囍模块接入规范》
「工单字段」里「谁写」一栏是自己的字段。要改字段，先改文档，再由框架同学改这里。
"""

from typing import TypedDict

from pydantic import BaseModel, ConfigDict, Field


class Brief(BaseModel):
    """需求单，由小囍生成。

    工单里以 dict 保存：用 Brief(**state["brief"]) 得到对象，用 brief.model_dump() 存回去。
    不允许出现下面没有的字段；要加字段先改《小囍模块接入规范》，再由框架同学改这里。
    """

    model_config = ConfigDict(extra="forbid")

    intent: str = "photo_and_materials"
    style: str = "keep_original"  # 风格编号，对应妆造师 prompts/ 里的模板文件名
    background: str = "keep_original"  # keep_original 保留原图场景；studio 室内影棚
    makeup: str = "自然淡妆"
    outfit_bride: str = "白色缎面婚纱"
    outfit_groom: str = "黑色西装，白衬衫"
    expression: str = "自然微笑"
    pose: str = "keep_original"  # keep_original 或姿势模板编号
    heights_cm: list[int] = Field(default_factory=list)  # 两人身高，例如 [175, 162]
    body_types: list[str] = Field(default_factory=list)
    keep_features: list[str] = Field(default_factory=list)  # 必须保留的特征，例如 "女生的眼镜"
    beautify: str = "none"  # none 不美化；light 轻度美化，只有用户主动选择才能是 light
    materials: list[str] = Field(default_factory=lambda: ["invitation", "welcome_poster", "led_screen"])
    invitation: dict = Field(default_factory=dict)  # {"names": ..., "date": ..., "place": ...}
    missing: list[str] = Field(default_factory=list)  # 还缺的字段；空列表表示资料齐了


class WeddingState(TypedDict, total=False):
    # 框架写
    task_id: str
    photo_urls: list[str]
    description: str
    answers: list[dict]  # 每条含 question_id、value 或 skipped，以及第几轮 round
    retry_count: int
    user_feedback: dict | None  # 用户要求重做时的 image_id、reason、note
    step_text: str  # 任何模块都可以写，给用户看的进度文案

    # 主 agent（小囍）写
    questions: list[dict]
    brief: dict
    message: str

    # 妆造师写
    look: dict  # {"text": 造型描述, "style": 风格编号}

    # 摄影师写
    shot: dict  # {"text": 构图光线姿势描述, "pose": 姿势编号, "pose_ref_url": 地址或 None}

    # 生图 agent 写
    prompt: str
    candidates: list[dict]  # 每张含 image_id、url、seed
    generation: dict  # engine、workflow、seconds、total_images

    # 评测修图师写
    scores: list[dict]
    best_image_id: str | None
    passed: bool
    retouch_plan: dict | None  # {"target": look/shot/generate/none, "patch": 修改说明, "image_id": 换用的候选}

    # 资产库写
    previews: list[dict]
    deliverables: dict
