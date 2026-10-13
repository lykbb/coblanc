"""生图服务的唯一出口。换服务、加备用服务，只改这个文件。"""


def generate_image(photo_urls: list[str], prompt: str, seed: int, pose_ref_url: str | None = None) -> bytes:
    """调用生图服务，返回一张图片的二进制内容（jpg 或 png）。

    主力：RunningHub 上的 ComfyUI 工作流（.env 里的 RUNNINGHUB_API_KEY、RUNNINGHUB_WORKFLOW_ID），
          用 nodeInfoList 按节点 ID 传入照片、提示词和种子。
    备用：火山方舟 Seedream（LLM_API_KEY、SEEDREAM_MODEL）。
    以模型选型的实测结果为准。照片要先用 app.modules.assets.load_image 读出来再上传给服务。
    """
    raise NotImplementedError("生图服务还没接，见《小囍模块接入规范》模块卡片 5")
