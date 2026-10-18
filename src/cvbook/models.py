"""公共数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class BookMeta:
    """书籍元信息。"""

    title: str = ""
    authors: List[str] = field(default_factory=list)
    comments: str = ""

    @property
    def author_text(self) -> str:
        """calibre 用 " & " 分隔多作者。"""
        return " & ".join(self.authors)

    @property
    def complete(self) -> bool:
        # 作者可以没有（HTML/CHM 里经常提取不到），书名必须有
        return bool(self.title)


@dataclass
class Chapter:
    """一个页面（输入插件解析出来的最小单位）。

    - ``html`` 是页面内部的 XHTML 片段，章节标题用 ``<h1>``。
    - ``level`` 是目录层级：1 是顶层，2 挂在上一个 1 级条目下，依此类推。
    """

    title: str
    html: str
    level: int = 1
