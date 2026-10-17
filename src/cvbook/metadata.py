"""书名/作者兜底解析、封面查找。"""

from __future__ import annotations

import os
import re
from typing import Optional

from .frontmatter import BookMeta

FILENAME_TITLE_RE = re.compile(r"^.*《([^》]*)》")
FILENAME_AUTHOR_RE = re.compile(r"^.*作者[:：][ \t]*(.*)")
COVER_EXTS = ("jpg", "jpeg", "png", "webp")


def filename_title(path: str) -> str:
    matched = FILENAME_TITLE_RE.search(os.path.basename(path))
    return matched.group(1).strip() if matched else ""


def filename_author(path: str) -> str:
    stem = os.path.splitext(os.path.basename(path))[0]
    matched = FILENAME_AUTHOR_RE.search(stem)
    return matched.group(1).strip() if matched else ""


def resolve_meta(path: str, info: Optional[BookMeta] = None) -> BookMeta:
    """frontmatter 里缺的字段用文件名兜底，返回补齐后的 BookMeta。"""
    if info is None:
        info = BookMeta()
    if not info.title:
        info.title = filename_title(path)
    if not info.authors:
        author = filename_author(path)
        if author:
            info.authors = [author]
    return info


def find_cover(path: str) -> Optional[str]:
    """找与源文件同名的封面图（jpg/jpeg/png/webp）。"""
    stem = os.path.splitext(path)[0]
    for ext in COVER_EXTS:
        cover = "%s.%s" % (stem, ext)
        if os.path.isfile(cover):
            return cover
    return None
