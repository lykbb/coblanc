"""妆造师：按风格模板和需求单填空，写出造型描述 look。

不是 agent，不做多步循环。每种风格一个模板 prompts/<风格编号>.md，
模板里的 {字段名} 用需求单同名字段填充。
"""

from pathlib import Path

from app.state import Brief, WeddingState

PROMPTS = Path(__file__).parent / "prompts"
DEFAULT_STYLE = "keep_original"


def available_styles() -> list[str]:
    return sorted(path.stem for path in PROMPTS.glob("*.md"))


def style(state: WeddingState) -> dict:
    brief = Brief(**state.get("brief", {}))
    style_id = brief.style if (PROMPTS / f"{brief.style}.md").is_file() else DEFAULT_STYLE
    template = (PROMPTS / f"{style_id}.md").read_text(encoding="utf-8").strip()
    fields = {key: value for key, value in brief.model_dump().items() if isinstance(value, str)}
    text = template.format_map(fields)

    if brief.keep_features:
        text += f"保留：{'、'.join(brief.keep_features)}。"
    plan = state.get("retouch_plan") or {}
    if plan.get("target") == "look" and plan.get("patch"):
        text += f"调整：{plan['patch']}。"
    # TODO(妆造师)：需要时用一次 get_llm("cheap") 把用户的模糊描述转成模板里的词；
    # beautify 不是 "light" 时，不要写瘦身、改五官、年轻化等内容
    return {"look": {"text": text, "style": style_id}}
