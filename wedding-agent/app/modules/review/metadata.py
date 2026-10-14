"""离线运行元数据校验；不读取模型密钥、地址或照片。"""

from app.common.errors import ModuleError

SIGNATURE_FIELDS = ("mode", "face_model", "score_scale", "vision_model", "prompt_version")
PUBLIC_FIELDS = (*SIGNATURE_FIELDS, "agent_model", "dataset_version", "face_sim_threshold")


def run_signature(metadata: dict) -> tuple[str, ...]:
    if not isinstance(metadata, dict) or any(not isinstance(metadata.get(key), str) or not metadata[key].strip() for key in SIGNATURE_FIELDS):
        raise ModuleError("FILE_INVALID", "运行元数据缺少模式、人脸模型、分数尺度、视觉模型或提示词版本")
    return tuple(metadata[key].strip() for key in SIGNATURE_FIELDS)


def consistent_signature(predictions: list[dict]) -> tuple[str, ...]:
    signatures = {run_signature(prediction.get("metadata")) for prediction in predictions}
    if len(signatures) != 1:
        raise ModuleError("FILE_INVALID", "标定或验收数据使用了不同模型、分数尺度或提示词版本")
    return next(iter(signatures))
