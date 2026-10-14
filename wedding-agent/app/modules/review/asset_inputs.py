"""真实质检与独立诊断共用的资产库读图和输入验证。"""

from app.common.config import settings
from app.common.errors import ModuleError
from app.modules.assets import load_image

from .vision import image_mime


def read_images(state: dict, candidates: list[dict], *, loader=None) -> tuple[bytes, list[tuple[str, bytes]]]:
    photos = state.get("photo_urls")
    if not isinstance(photos, list) or not photos or not isinstance(photos[0], str):
        raise ModuleError("PHOTO_INVALID", "当前质检需要一张清晰的双人合照")
    if isinstance(settings.candidates_per_round, bool) or not isinstance(settings.candidates_per_round, int) or settings.candidates_per_round < 1 or not candidates or len(candidates) > settings.candidates_per_round:
        raise ModuleError("GENERATION_FAILED", "候选数量或本轮张数配置不正确")
    loader = loader or load_image
    try:
        source = loader(photos[0])
        images = [(candidate["image_id"], loader(candidate["url"])) for candidate in candidates]
    except Exception:
        raise ModuleError("FILE_INVALID", "质检图片无法从资产库读取，请重新上传或生成") from None
    image_mime(source)
    for _, data in images:
        image_mime(data)
    return source, images
