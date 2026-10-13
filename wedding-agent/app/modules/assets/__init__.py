"""资产库：存图、取图、取模板、出预览、套版。见《小囍模块接入规范》模块卡片 7。"""

from .node import get_template, load_image, make_previews, package, purge_expired, save_image

__all__ = ["save_image", "load_image", "get_template", "make_previews", "package", "purge_expired"]
