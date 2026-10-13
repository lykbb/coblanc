"""生图 agent：拼最终提示词，调用生图服务出 4 张候选。见《小囍模块接入规范》模块卡片 5。"""

from .node import build_prompt, generate

__all__ = ["generate", "build_prompt"]
