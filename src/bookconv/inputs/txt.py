"""纯文本（txt）输入插件。

网文 txt 一般是"一行一段 + 章标题独占一行"，所以这里按行切分：
标题行用正则识别，其余非空行各自成段。以后要支持更多标题层级，只要在
``_event_level`` 里加规则即可。

默认能识别::

    第一卷 风起 / 第一部 / 第一篇
    第1章 少年和媳妇 / 第十二回 / 第 3 节
    Chapter 12

有"卷/部/篇"时章标题会作为二级目录挂在卷下面，否则章标题就是一级目录。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence

from ..htmlutil import escape
from ..images import ImageStore
from ..models import Chapter
from .base import InputFormat, ParseOptions, SourceFile

_NUM = r"[0-9０-９一二三四五六七八九十百千万零〇两]+"

#: 默认的章节标题正则（也用于识别卷/部/篇）
DEFAULT_PATTERN = (
    r"^\s*(?:第\s*" + _NUM + r"\s*[章节回卷部篇]|Chapter\s+\d+)"
    r"(?:[\s:：、，,.．·—\-]+.*)?$"
)
VOLUME_RE = re.compile(
    r"^\s*第\s*" + _NUM + r"\s*[卷部篇](?:[\s:：、，,.．·—\-]+.*)?$",
    re.IGNORECASE,
)


@dataclass
class _Event:
    kind: str          #: "volume" / "chapter"
    title: str
    lines: List[str]


def _is_volume(title: str) -> bool:
    return bool(VOLUME_RE.match(title))


def split_events(text: str, pattern: str) -> List[_Event]:
    """按标题行切分，返回事件列表（标题行 + 其后的正文行）。"""
    matcher = re.compile(pattern)
    events: List[_Event] = []
    current: Optional[_Event] = None
    preface: List[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        if stripped and matcher.match(stripped):
            if current is not None:
                events.append(current)
            kind = "volume" if _is_volume(stripped) else "chapter"
            current = _Event(kind, stripped, [])
            continue
        if current is None:
            preface.append(line)
        else:
            current.lines.append(line)

    if current is not None:
        events.append(current)
    if any(line.strip() for line in preface):
        events.insert(0, _Event("chapter", "", preface))
    return events


class TextInput(InputFormat):
    name = "txt"
    extensions = ("txt", "text")

    def parse(self, source: SourceFile, *, images: ImageStore,
              options: ParseOptions) -> List[Chapter]:
        pattern = options.chapter_pattern or DEFAULT_PATTERN
        events = split_events(source.text, pattern)
        has_volume = any(event.kind == "volume" for event in events)

        chapters: List[Chapter] = []
        for event in events:
            if not event.title:
                title = "前言"
            else:
                title = event.title
            level = 1
            if event.kind == "chapter" and has_volume:
                level = 2

            parts = []
            if event.title:
                parts.append('<h1 class="chapter-title">%s</h1>'
                             % escape(event.title))
            for paragraph in event.lines:
                paragraph = paragraph.rstrip()
                if not paragraph.strip():
                    continue
                if not options.keep_indent:
                    paragraph = paragraph.strip()
                parts.append("<p>%s</p>" % escape(paragraph))

            if not parts:
                continue
            chapters.append(Chapter(title=title, html="\n".join(parts),
                                   level=level))

        return chapters


__all__ = ["TextInput", "DEFAULT_PATTERN", "split_events"]
