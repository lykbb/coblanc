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
