"""书名/作者兜底解析、封面查找。"""

from __future__ import annotations

import os
import re
from typing import List, Optional
from urllib.parse import urlsplit

from .frontmatter import BookMeta
from .images import sniff_image_ext

FILENAME_TITLE_RE = re.compile(r"^.*《([^》]*)》")
FILENAME_AUTHOR_RE = re.compile(r"^.*作者[:：][ \t]*(.*)")
COVER_EXTS = ("jpg", "jpeg", "png", "webp", "gif", "svg")


def _basename(path: str) -> str:
    if path.lower().startswith(("http://", "https://")):
        path = urlsplit(path).path
    path = path.rstrip("/" + os.sep)
    return os.path.basename(path)


def filename_title(path: str) -> str:
    matched = FILENAME_TITLE_RE.search(_basename(path))
    return matched.group(1).strip() if matched else ""


def filename_author(path: str) -> str:
    stem = os.path.splitext(_basename(path))[0]
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


def bookcover_base_name(title: str, author: str) -> str:
    """生成 bookcover 下载文件用的“《书名》作者：xxx”基名。"""
    name = "《%s》作者：%s" % (title, author or "未知")
    name = name.replace("/", "／").replace("\\", "＼").replace(":", "：")
    name = re.sub(r"[\x00-\x1f\x7f]", "", name)
    return name.rstrip(" .") or "未命名"


def _usable(path: str) -> bool:
    """存在、非空且文件头像图片，才算封面。"""
    try:
        if not os.path.isfile(path) or os.path.getsize(path) == 0:
            return False
        with open(path, "rb") as f:
            return sniff_image_ext(f.read(4096)) is not None
    except OSError:
        return False


def _bookcover_names(meta: Optional[BookMeta]) -> List[str]:
    if meta is None or not meta.title:
        return []
    authors = [author for author in meta.authors if author]
    names = []
    for author in authors or [""]:
        name = bookcover_base_name(meta.title, author)
        if name not in names:
            names.append(name)
    if len(authors) > 1:
        name = bookcover_base_name(meta.title, meta.author_text)
        if name not in names:
            names.append(name)
    return names


def _find_bookcover_cover(directory: str,
                          meta: Optional[BookMeta]) -> Optional[str]:
    for name in _bookcover_names(meta):
        for ext in COVER_EXTS:
            cover = os.path.join(directory, "%s.%s" % (name, ext))
            if _usable(cover):
                return cover
    return None


def _decode_text(raw: bytes) -> str:
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return raw.decode("utf-16")
        except UnicodeDecodeError:
            pass
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _read_description(path: str) -> str:
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        return ""
    return _decode_text(raw).strip()


def _description_candidates(path: str,
                            meta: Optional[BookMeta]) -> List[str]:
    if path.lower().startswith(("http://", "https://")):
        return []
    if os.path.isdir(path):
        return ([os.path.join(path, "cover.desc")]
                + [os.path.join(path, name + ".desc")
                   for name in _bookcover_names(meta)])

    candidates = [os.path.splitext(path)[0] + ".desc"]
    directory = os.path.dirname(os.path.abspath(path))
    candidates.extend(os.path.join(directory, name + ".desc")
                      for name in _bookcover_names(meta))
    return candidates


def read_description(path: str,
                     meta: Optional[BookMeta] = None) -> str:
    """读取同名或 bookcover 命名的 ``.desc`` 作为简介。"""
    for candidate in _description_candidates(path, meta):
        text = _read_description(candidate)
        if text:
            return text
    return ""


def find_cover(path: str, meta: Optional[BookMeta] = None) -> Optional[str]:
    """找封面图：先找同名图片/目录 cover.*，再找 bookcover 下载的封面。"""
    if path.lower().startswith(("http://", "https://")):
        return None
    if os.path.isdir(path):
        for ext in COVER_EXTS:
            cover = os.path.join(path, "cover." + ext)
            if _usable(cover):
                return cover
        return _find_bookcover_cover(path, meta)

    stem = os.path.splitext(path)[0]
    for ext in COVER_EXTS:
        cover = "%s.%s" % (stem, ext)
        if _usable(cover):
            return cover
    return _find_bookcover_cover(os.path.dirname(os.path.abspath(path)), meta)
