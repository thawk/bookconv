"""输入格式插件接口。

每种源文件格式实现一个 :class:`InputFormat` 子类，负责把源文件解析成"页"
（:class:`cvbook.models.Chapter`）。核心流程只认这个接口，所以以后要加新的
格式（比如带章节识别的 txt、HTML 等）不用改 EPUB 生成部分。

约定：解析结果里

* 章节标题用 ``<h1>``，小节用 ``<h2>`` / ``<h3>``，正文段落用 ``<p>``；
* 段落开头的缩进用 :func:`cvbook.htmlutil.strip_paragraph_indent` 去掉，
  交给 CSS 控制（``keep_indent`` 可关闭）；
* 插图用 :func:`cvbook.htmlutil.rewrite_images` 收进 EPUB；
* ``Chapter.level`` 是目录层级（1 = 顶层，2 = 上一个顶层条目下的子条目），
  方便以后做"自动识别各级标题"的格式。
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Sequence
from urllib.parse import urljoin, urlsplit

from ..images import EpubImage, ImageStore
from ..models import BookMeta, Chapter


class InputError(Exception):
    """输入无法读取/解析时抛出的可预期错误（CLI 只打印消息，不打印堆栈）。"""


def decode_text(raw: bytes) -> str:
    """按 UTF-8 / UTF-16 / GB18030 依次尝试解码。"""
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


def is_url(path: str) -> bool:
    return path.lower().startswith(("http://", "https://"))


@dataclass
class SourceFile:
    """交给插件的源文件（正文部分已去掉 frontmatter）。

    ``path`` 可以是普通文件、目录，或者 http(s) URL。目录和 URL 没有
    ``raw``（空 bytes），插件自己通过 :mod:`cvbook.inputs.htmlbook` 里的
    loader 读取。
    """

    path: str
    raw: bytes = b""

    @property
    def is_url(self) -> bool:
        return is_url(self.path)

    @property
    def is_dir(self) -> bool:
        return not self.is_url and os.path.isdir(self.path)

    @property
    def suffix(self) -> str:
        path = urlsplit(self.path).path if self.is_url else self.path
        return os.path.splitext(path)[1].lstrip(".").lower()

    @property
    def name(self) -> str:
        """文件名（URL 去掉 query/fragment，目录取目录名）。"""
        path = urlsplit(self.path).path if self.is_url else self.path
        path = path.rstrip("/")
        return os.path.basename(path) or "book"

    @property
    def base_dir(self) -> str:
        if self.is_url:
            return urljoin(self.path, ".")
        if self.is_dir:
            return os.path.abspath(self.path)
        return os.path.dirname(os.path.abspath(self.path))

    @property
    def text(self) -> str:
        return decode_text(self.raw)

    @property
    def binary(self) -> bool:
        """文件内容看起来是二进制（例如 CHM）。"""
        if self.raw.startswith((b"\xff\xfe", b"\xfe\xff")):
            return False                 # UTF-16 文本
        return b"\x00" in self.raw[:4096]


@dataclass
class ParseOptions:
    """插件通用的解析选项。"""

    #: 保留段落开头的全角空格（默认去掉，交给 CSS text-indent）
    keep_indent: bool = False
    #: txt 等纯文本格式的章节标题正则
    chapter_pattern: str = ""


class InputFormat(ABC):
    """输入格式插件。"""

    #: 插件名，命令行 --input 用
    name: str = ""
    #: 能处理的扩展名
    extensions: Sequence[str] = ()

    def matches(self, source: SourceFile) -> bool:
        if source.is_url:
            return self.matches_url(source)
        if source.is_dir:
            return self.matches_dir(source)
        return source.suffix in self.extensions

    def matches_url(self, source: SourceFile) -> bool:
        """URL 输入（默认不处理，由 HTML 插件接）。"""
        return False

    def matches_dir(self, source: SourceFile) -> bool:
        """目录输入（默认不处理，由 HTML 插件接）。"""
        return False

    def metadata(self, source: SourceFile) -> BookMeta:
        """尽可能从内容里读出书名/作者，供文件名猜不出时兜底。"""
        return BookMeta()

    def cover(self, source: SourceFile) -> Optional[EpubImage]:
        """源文件内部自带封面时返回它（目前只有 EPUB 用）。"""
        return None

    @abstractmethod
    def parse(self, source: SourceFile, *, images: ImageStore,
              options: ParseOptions) -> List[Chapter]:
        """把源文件解析成页面列表。"""
        raise NotImplementedError


__all__ = ["InputError", "InputFormat", "ParseOptions", "SourceFile",
           "decode_text", "is_url"]
