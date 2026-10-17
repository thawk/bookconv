"""生成 XHTML 时用到的通用小工具（各输入插件共用）。"""

from __future__ import annotations

import html as html_lib
import os
import re
import sys
from typing import Optional
from urllib.parse import unquote

from .images import ImageStore

TAG_RE = re.compile(r"<[^>]+>")
#: 段落开头的全角空格/空白（源文件自己缩进过，交给 CSS text-indent 更灵活）
P_INDENT_RE = re.compile(r"(<p\b[^>]*>)[\u3000 \t]+")
IMG_RE = re.compile(r'(<img\b[^>]*?\bsrc=")([^"]+)(")', re.IGNORECASE)
ABSOLUTE_URL_RE = re.compile(r"^(?:[a-zA-Z][a-zA-Z0-9+.-]*:|//|#)")


def escape(text: str) -> str:
    return html_lib.escape(text, quote=True)


def plain_text(fragment: str) -> str:
    """去掉标签、还原实体，得到纯文本（用于目录标题）。"""
    return html_lib.unescape(TAG_RE.sub("", fragment)).strip()


def strip_paragraph_indent(html: str) -> str:
    return P_INDENT_RE.sub(r"\1", html)


def paragraphs(text: str, keep_indent: bool = False) -> str:
    """纯文本 -> <p> 段落（空行分段，用于简介等短文本）。"""
    if not text or not text.strip():
        return ""
    parts = []
    for block in re.split(r"\n\s*\n", text.strip()):
        block = block.strip()
        if not block:
            continue
        if not keep_indent:
            block = " ".join(block.split())
        parts.append("<p>%s</p>" % escape(block))
    return "\n".join(parts)


def rewrite_images(html: str, base_dir: str, images: Optional[ImageStore],
                   href_prefix: str = "") -> str:
    """把 ![](相对路径) 指向的图片收进 EPUB，并改写 src。"""
    if images is None:
        return html

    def replace(matched: "re.Match[str]") -> str:
        src = html_lib.unescape(matched.group(2)).strip()
        if ABSOLUTE_URL_RE.match(src):
            return matched.group(0)
        source = os.path.normpath(os.path.join(base_dir, unquote(src)))
        stored = images.add(source)
        if stored is None:
            print("!!! 找不到插图: %s" % source, file=sys.stderr)
            return matched.group(0)
        return (matched.group(1)
                + html_lib.escape(href_prefix + stored, quote=True)
                + matched.group(3))

    return IMG_RE.sub(replace, html)
