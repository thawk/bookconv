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
from typing import List, Sequence

from ..images import ImageStore
from ..models import Chapter


def decode_text(raw: bytes) -> str:
    """按 UTF-8 / GB18030 依次尝试解码。"""
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


@dataclass
class SourceFile:
    """交给插件的源文件（正文部分已去掉 frontmatter）。"""

    path: str
    raw: bytes

    @property
    def base_dir(self) -> str:
        return os.path.dirname(os.path.abspath(self.path))

    @property
    def text(self) -> str:
        return decode_text(self.raw)


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
        ext = os.path.splitext(source.path)[1].lstrip(".").lower()
        return ext in self.extensions

    @abstractmethod
    def parse(self, source: SourceFile, *, images: ImageStore,
              options: ParseOptions) -> List[Chapter]:
        """把源文件解析成页面列表。"""
        raise NotImplementedError


__all__ = ["InputFormat", "ParseOptions", "SourceFile", "decode_text"]
