"""双人特征向量配对。服务选型后，只需实现图片到向量的提取入口。"""

from collections.abc import Callable, Sequence
from math import isfinite, sqrt
from time import monotonic
from typing import Protocol

from app.common.config import settings
from app.common.errors import ModuleError

Embedding = Sequence[float]


def provider_metadata() -> dict:
    """服务选型后与 compare_faces 一起实现；不得包含密钥或访问地址。"""
    return {"connected": False, "face_model": "not_connected", "score_scale": "unconfigured"}


class FaceExtractor(Protocol):
    """供应商适配器须实际遵守 timeout_seconds，且不在内部无限重试。"""

    def extract(self, image: bytes, *, timeout_seconds: float) -> Sequence[Embedding]: ...


def compare_batch_with_extractor(source: bytes, candidates: list[tuple[str, bytes]], extractor: FaceExtractor) -> dict[str, list[float]]:
    """单轮提取原图一次；每次调用传入剩余预算，无跨任务缓存。

    本模块不自行启动后台线程，适配器负责网络／推理的实际超时。
    超时后不能产生可用评分；单张失败暂保持整轮失败。
    """
    ids = [image_id for image_id, _ in candidates]
    if isinstance(settings.candidates_per_round, bool) or not isinstance(settings.candidates_per_round, int) or settings.candidates_per_round < 1:
        raise ModuleError("GENERATION_FAILED", "候选张数配置必须为正整数")
    if not ids or len(ids) != len(set(ids)) or len(ids) > settings.candidates_per_round:
        raise ModuleError("GENERATION_FAILED", "本轮人脸比对的候选数量或编号不正确")
    if isinstance(settings.max_agent_steps, bool) or not isinstance(settings.max_agent_steps, int) or settings.max_agent_steps < len(ids) + 1 or isinstance(settings.image_timeout_seconds, bool) or not isinstance(settings.image_timeout_seconds, (int, float)) or not isfinite(settings.image_timeout_seconds) or settings.image_timeout_seconds <= 0:
        raise ModuleError("GENERATION_FAILED", "人脸提取调用次数或超时预算不足")
    deadline = monotonic() + settings.image_timeout_seconds

    def extract(data: bytes) -> Sequence[Embedding]:
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise ModuleError("GENERATION_FAILED", "人脸比对已超时，请稍后重试")
        try:
            vectors = extractor.extract(data, timeout_seconds=remaining)
        except Exception:
            raise ModuleError("GENERATION_FAILED", "人脸特征提取失败，请稍后重试")
        if monotonic() >= deadline:
            raise ModuleError("GENERATION_FAILED", "人脸比对已超时，请稍后重试")
        return vectors

    source_vectors = extract(source)
    return {image_id: match_embeddings(source_vectors, extract(data)) for image_id, data in candidates}


def match_embeddings(source: Sequence[Embedding], candidate: Sequence[Embedding]) -> list[float]:
    """按原图人物顺序返回分数；自动处理候选两人换位，不按性别排序。

    分数为单位向量的余弦相似度，负值记为 0；阈值需按实际模型标定。
    输入须恰有两张人脸的特征。多脸／缺脸不能猜测主体。
    """
    try:
        if len(source) != 2 or len(candidate) != 2:
            raise ValueError("two faces required")
        vectors = [list(vector) for vector in [*source, *candidate]]
        dimension = len(vectors[0])
        if not dimension or any(len(vector) != dimension for vector in vectors):
            raise ValueError("dimensions mismatch")
        normalized = []
        for vector in vectors:
            if any(isinstance(value, bool) or not isinstance(value, (float, int)) or not isfinite(value) for value in vector):
                raise ValueError("invalid embedding")
            norm = sqrt(sum(value * value for value in vector))
            if not isfinite(norm) or norm == 0:
                raise ValueError("zero norm")
            normalized.append([value / norm for value in vector])
        matrix = [[sum(a * b for a, b in zip(normalized[i], normalized[j + 2])) for j in range(2)] for i in range(2)]
        pairs = [matrix[0][0], matrix[1][1]] if matrix[0][0] + matrix[1][1] >= matrix[0][1] + matrix[1][0] else [matrix[0][1], matrix[1][0]]
        return [max(0.0, min(1.0, value)) for value in pairs]
    except (TypeError, ValueError, OverflowError):
        raise ModuleError("GENERATION_FAILED", "无法完成双人人脸对应，请检查人脸数量和特征数据")


def compare_with_extractor(source: bytes, candidate: bytes, extractor: Callable[[bytes], Sequence[Embedding]]) -> list[float]:
    """测试或本地服务可传入提取器；不在模块全局缓存任务、人脸或模型结果。"""
    try:
        return match_embeddings(extractor(source), extractor(candidate))
    except ModuleError:
        raise
    except Exception:
        raise ModuleError("GENERATION_FAILED", "人脸特征提取失败，请稍后重试")


def compare_faces(source: bytes, candidate: bytes) -> list[float]:
    """真实图片入口；没有已选定服务时明确阻止通过，不用视觉模型猜分。"""
    raise ModuleError("GENERATION_FAILED", "人脸比对服务尚未接入，请先完成选型；演示可使用 fake 模式")
