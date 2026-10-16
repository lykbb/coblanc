"""统一的错误类型（框架维护）。"""


class ModuleError(Exception):
    """模块出错时抛这个。

    code 用《小囍接口约定》里的错误码，例如 PHOTO_INVALID、GENERATION_FAILED；
    message 是给用户看的中文，前端会直接显示。
    """

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


# ---- 失败分类（前后端统一） ----
# user_input：上传内容不符合要求（用户改了就能继续，不可「重试」）
# system：模型/网络/服务异常（不是用户的问题，可点「重试」从出错那一步继续）
# 质检没完全达标不算失败：图会照样交出来，附 quality_note 说明（见 graph.accept_best）
USER_INPUT_CODES = {"PHOTO_INVALID", "FILE_INVALID"}
STEP_NAMES = {
    "intake": "小囍看照片/整理需求", "styling": "妆造师设计造型", "framing": "摄影师设计镜头",
    "composing": "合成生图指令", "generating": "生图", "checking": "审片质检",
    "retouching": "修图", "packaging": "制作婚礼物料",
}


def error_info(code: str, message: str, step: str | None) -> dict:
    if code in USER_INPUT_CODES:
        return {"code": code, "category": "user_input", "step": step, "retryable": False,
                "title": "上传的照片不符合要求", "message": message}
    where = STEP_NAMES.get(step or "", "处理")
    return {"code": code, "category": "system", "step": step, "retryable": True,
            "title": f"系统异常：{where}这一步没完成",
            "message": f"{message}（模型/网络/服务异常，不是你们的问题），可以点「重试」从这一步继续。"}
