"""照片规则（代码里唯一的一份）。

规则原文在 prompts/dialogue.md 的「照片规则」；photo_sort / image_prompt SKILL、接口和前端文案都引用这里，
不再各写一套。这里只做纯判断：输入每张照片的检查结果（photo_sort 的 check 输出），输出能不能继续、
缺什么、身份照怎么排、是否需要用单人照合成。

规则：
1. 一共 2～10 张（重复的照片只算一张）。
2. 合照、单人照都行，不要求合照，也不追问合照。可用照片里新郎、新娘各至少出现一次（合照里出现也算）就通过。
3. 可用照片里没有合照 → compose_from_solo=True（自动，不问用户）。
4. 宠物：只有动物是画面主体（pet_prominent）且用户没说要它入镜时，才请用户说明；背景里的动物、拿不准的，一律不管。
5. 只在三种情况暂停：缺新郎或缺新娘；主体宠物未经同意；数量不在 2～10。其他不可用的照片，要求满足时直接跳过。
"""

from __future__ import annotations

from dataclasses import dataclass, field

MIN_PHOTOS = 2
MAX_PHOTOS = 10
PET_WORDS = ("宠物", "狗", "猫", "兔", "毛孩子", "仓鼠", "鹦鹉")

COUNT_MESSAGE = "请上传 2～10 张照片，新郎新娘都要有，合照单人照都行"
TOO_MANY_MESSAGE = "照片最多 10 张，请删掉几张再上传"
UPLOAD_HINT = "新郎新娘都要有，合照单人照都行"


def dedupe(urls) -> list[str]:
    """同一张照片传了两次只算一张，保持原顺序。"""
    seen, out = set(), []
    for url in urls or []:
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def count_problem(n: int) -> str:
    if n < MIN_PHOTOS:
        return COUNT_MESSAGE
    if n > MAX_PHOTOS:
        return TOO_MANY_MESSAGE
    return ""


def pet_consent(text: str) -> bool:
    """用户在描述或回答里主动提到宠物，视为同意宠物一起入镜。"""
    return any(word in (text or "") for word in PET_WORDS)


def role_of(result: dict) -> str | None:
    """这张照片里能用的人：couple / groom / bride；不能用返回 None。侧脸、轻微遮挡不卡。"""
    people = result.get("people_count", 0)
    if not result.get("clear") or people not in (1, 2):
        return None
    if people == 2:
        return "couple"
    tag = result.get("tag")
    return tag if tag in ("groom", "bride") else None


def pet_blocks(result: dict, consent: bool) -> bool:
    return bool(result.get("pet_prominent")) and not consent


def _pet_name(result: dict) -> str:
    return result.get("pet_kind") or "小动物"


def _unusable_reason(result: dict) -> str:
    people = result.get("people_count", 0)
    if people == 0:
        return "这张没看到人脸，请换一张你们的照片"
    if people > 2:
        return "这张人有点多，请换成单人照或你们俩的合照"
    if not result.get("clear"):
        return "这张有点模糊，请换一张清晰的"
    return "这张分不清是新郎还是新娘，请换一张"


@dataclass
class Verdict:
    failures: list[dict] = field(default_factory=list)  # {"index": int|None, "reason": str}
    identity: list[dict] = field(default_factory=list)  # [{"url", "role"}]，合照优先，再新郎、新娘
    compose_from_solo: bool = False
    pets: list[str] = field(default_factory=list)  # 同意入镜的宠物种类

    @property
    def ok(self) -> bool:
        return not self.failures


def evaluate(urls: list[str], results: list[dict], consent: bool) -> Verdict:
    """按上面的规则判断一组混合上传的照片。results 与 urls 一一对应。"""
    verdict = Verdict()
    problem = count_problem(len(urls))
    if problem:
        verdict.failures.append({"index": None, "reason": problem})
        return verdict
    usable: list[tuple[str, str, dict]] = []
    for url, result in zip(urls, results):
        role = role_of(result)
        if pet_blocks(result, consent):
            where = "是" if not result.get("people_count") else "里有"
            verdict.failures.append({"index": result["index"], "reason": f"这张{where}{_pet_name(result)}，如需一起入镜请告诉我"})
        if role:
            usable.append((url, role, result))
        if consent and result.get("pet_prominent"):
            verdict.pets.append(_pet_name(result))
    present = {"groom", "bride"} if any(role == "couple" for _, role, _ in usable) else {role for _, role, _ in usable}
    missing = [who for who in ("groom", "bride") if who not in present]
    if missing:
        # 缺人时才点名其他不能用的照片，帮用户知道换哪张
        verdict.failures += [{"index": r["index"], "reason": _unusable_reason(r)}
                             for r in results if not role_of(r) and not pet_blocks(r, consent)]
        verdict.failures += [{"index": None, "reason": f"还缺{'新郎' if who == 'groom' else '新娘'}的清晰照片，单人照或合照都行"}
                             for who in missing]
    usable.sort(key=lambda item: (("couple", "groom", "bride").index(item[1]),
                                  not (item[2].get("front_facing") and item[2].get("unobstructed"))))
    verdict.identity = [{"url": url, "role": role} for url, role, _ in usable][:MAX_PHOTOS]
    verdict.compose_from_solo = bool(usable) and not any(role == "couple" for _, role, _ in usable)
    return verdict


def describe(failures: list[dict]) -> str:
    overall = [item["reason"] for item in failures if not item.get("index")]
    per_photo = [f"第{item['index']}张{item['reason'].removeprefix('这张')}" for item in failures if item.get("index")]
    return "；".join(overall + per_photo)
