"""解析 Markdown 文件头部的 YAML frontmatter。

不依赖 PyYAML：不少工具生成的 frontmatter 并不严格合法（块标量内容没有缩进、
字段之间有空行等），而 calibre / pandoc 自带的解析器碰到这些写法会放弃解析，
把整段 frontmatter 当正文。这里做的是容错解析，只关心书名/作者/简介等字段。
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple, Union

from .models import BookMeta

KEY_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_.-]*)[ \t]*:[ \t]*(.*)$")
LIST_ITEM_RE = re.compile(r"^\s*-\s+(.*)$")

CLOSING_DELIMS = (b"---", b"...")
#: frontmatter 不会很大，超过这个大小多半是正文里的 --- 水平分割线
MAX_FM_BYTES = 256 * 1024

#: 常见的书籍信息字段名
TITLE_KEYS = ("title",)
AUTHOR_KEYS = ("authors", "author", "creator")
COMMENT_KEYS = ("comments", "description", "abstract", "summary")
RECOGNIZED_KEYS = {
    "title", "author", "authors", "creator",
    "comments", "description", "abstract", "summary",
}

MetaValue = Union[str, List[str]]


class NoFrontMatter(Exception):
    """文件里没有 frontmatter（或者看起来不是 frontmatter）。"""


def split_frontmatter(raw: bytes) -> Tuple[str, bytes]:
    """返回 (frontmatter 文本, 正文 bytes)，没有 frontmatter 时抛 NoFrontMatter。"""
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]

    nl = raw.find(b"\n")
    if nl == -1 or raw[:nl].rstrip(b"\r \t") != b"---":
        raise NoFrontMatter()

    fm_start = nl + 1
    pos = fm_start
    close_start = close_end = None
    while pos < len(raw):
        nl = raw.find(b"\n", pos)
        if nl == -1:
            line, nxt = raw[pos:], len(raw)
        else:
            line, nxt = raw[pos:nl], nl + 1
        if line.rstrip(b"\r \t") in CLOSING_DELIMS:
            close_start, close_end = pos, nxt
            break
        if pos - fm_start > MAX_FM_BYTES:
            raise NoFrontMatter()
        pos = nxt

    if close_start is None:
        raise NoFrontMatter()

    fm_bytes = raw[fm_start:close_start]
    for encoding in ("utf-8", "gb18030"):
        try:
            return fm_bytes.decode(encoding), raw[close_end:]
        except UnicodeDecodeError:
            continue
    raise NoFrontMatter()


def unquote(value: str) -> str:
    """去掉标量两侧的引号并还原常见转义。"""
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        inner = value[1:-1]
        if value[0] == '"':
            inner = (inner.replace("\\n", "\n")
                          .replace("\\t", "\t")
                          .replace('\\"', '"')
                          .replace("\\\\", "\\"))
        else:
            inner = inner.replace("''", "'")
        return inner
    return value


def parse_meta(text: str) -> Dict[str, MetaValue]:
    """把 frontmatter 文本解析成 {key: str 或 [str]}。"""
    meta: Dict[str, MetaValue] = {}
    lines = text.splitlines()
    i, total = 0, len(lines)

    while i < total:
        line = lines[i]
        if not line.strip():
            i += 1
            continue

        matched = KEY_RE.match(line)
        if not matched:                # 不认识的写法，跳过
            i += 1
            continue

        key, value = matched.group(1).lower(), matched.group(2)
        i += 1
        marker = value.strip()

        # 块标量: | |+ |- > >+ >-
        if marker in ("|", "|+", "|-", ">", ">+", ">-"):
            folded = marker[0] == ">"
            block: List[str] = []
            while i < total:
                nxt = lines[i]
                # 顶格出现的 "key: value" 视为下一个字段
                if nxt[:1] not in (" ", "\t") and KEY_RE.match(nxt):
                    break
                block.append(nxt)
                i += 1
            while block and not block[0].strip():
                block.pop(0)
            while block and not block[-1].strip():
                block.pop()
            # 允许内容未缩进（很多生成器就是这样写的）
            content = [b.strip() for b in block]
            meta[key] = (" " if folded else "\n").join(content)
            continue

        # 列表: key:\n  - a\n  - b   或   key: [a, b]
        if not marker:
            items: List[str] = []
            while i < total:
                nxt = lines[i]
                item = LIST_ITEM_RE.match(nxt)
                if item:
                    items.append(unquote(item.group(1)))
                    i += 1
                elif not nxt.strip():
                    i += 1
                else:
                    break
            meta[key] = items if items else ""
            continue

        if marker.startswith("[") and marker.endswith("]"):
            meta[key] = [unquote(x) for x in marker[1:-1].split(",") if x.strip()]
            continue

        meta[key] = unquote(marker)

    return meta


def one_line(value: MetaValue) -> str:
    return " ".join(str(value).split())


def as_text(value: Optional[MetaValue]) -> str:
    if not value:
        return ""
    if isinstance(value, list):
        return "\n\n".join(str(v).strip() for v in value if str(v).strip())
    return str(value).strip()


def as_lines(value: Optional[MetaValue]) -> List[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [one_line(v) for v in value if one_line(v)]
    line = one_line(value)
    return [line] if line else []


def _first(meta: Dict[str, MetaValue], *keys: str) -> Optional[MetaValue]:
    for key in keys:
        if meta.get(key):
            return meta[key]
    return None


def read_frontmatter(raw: bytes) -> Tuple[BookMeta, bytes]:
    """解析文件头部的 frontmatter，返回 (BookMeta, 正文 bytes)。"""
    text, body = split_frontmatter(raw)

    # 安全性检查：第一处非空行必须是 key: value，避免把正文里的 --- 误判成
    # frontmatter；同时至少要有一个已知字段
    first_line = next((line for line in text.splitlines() if line.strip()), "")
    if not KEY_RE.match(first_line):
        raise NoFrontMatter()

    meta = parse_meta(text)
    if not (set(meta) & RECOGNIZED_KEYS):
        raise NoFrontMatter()

    info = BookMeta(
        title=one_line(as_text(_first(meta, *TITLE_KEYS))),
        authors=as_lines(_first(meta, *AUTHOR_KEYS)),
        comments=as_text(_first(meta, *COMMENT_KEYS)),
    )
    return info, body
