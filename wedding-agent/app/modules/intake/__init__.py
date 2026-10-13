"""主 agent（小囍）：接单、写最终提示词、揭幕。见《小囍模块接入规范》模块卡片 2。"""

from .node import compose, intake, reveal

__all__ = ["intake", "compose", "reveal"]
