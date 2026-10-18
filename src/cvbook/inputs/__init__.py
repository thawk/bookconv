"""输入插件注册表。"""

from __future__ import annotations

from typing import List, Optional, Sequence

from .asciidoc import AsciiDocInput
from .base import (InputError, InputFormat, ParseOptions, SourceFile,
                   decode_text)
from .chm import ChmInput
from .html import HtmlInput
from .markdown import MarkdownInput
from .txt import TextInput

#: 注册的输入格式，顺序决定自动识别的优先级
FORMATS: Sequence[InputFormat] = (
    MarkdownInput(),
    TextInput(),
    AsciiDocInput(),
    HtmlInput(),
    ChmInput(),
)

#: 识别不出扩展名时默认用哪种格式
DEFAULT_FORMAT = "markdown"


def names() -> List[str]:
    return [fmt.name for fmt in FORMATS]


def get(name: str) -> Optional[InputFormat]:
    for fmt in FORMATS:
        if fmt.name == name:
            return fmt
    return None


def detect(source: SourceFile) -> Optional[InputFormat]:
    for fmt in FORMATS:
        if fmt.matches(source):
            return fmt
    return None


__all__ = ["FORMATS", "DEFAULT_FORMAT", "InputError", "InputFormat",
           "ParseOptions", "SourceFile", "decode_text", "detect", "get",
           "names"]
