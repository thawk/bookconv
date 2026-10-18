"""HTML 输入插件：单个 HTML 文件、整本 HTML 目录，或者网页 URL。"""

from __future__ import annotations

import os
from typing import List

from ..images import ImageStore
from ..models import BookMeta, Chapter
from . import htmlbook
from .base import InputFormat, ParseOptions, SourceFile


class HtmlInput(InputFormat):
    name = "html"
    extensions = ("html", "htm", "xhtml", "shtml")

    def matches_url(self, source: SourceFile) -> bool:
        return True

    def matches_dir(self, source: SourceFile) -> bool:
        if not os.path.isdir(source.path):
            return False
        root = os.path.abspath(source.path)
        for dirpath, dirnames, filenames in os.walk(root):
            depth = os.path.relpath(dirpath, root).count(os.sep)
            if depth >= 3:
                dirnames[:] = []
                continue
            for name in filenames:
                lower = name.lower()
                if lower.endswith((".html", ".htm", ".xhtml", ".shtml",
                                   ".hhc")):
                    return True
                if lower in ("page.js", "pages.js"):
                    return True
        return False

    def metadata(self, source: SourceFile) -> BookMeta:
        return htmlbook.metadata_for_source(source)

    def parse(self, source: SourceFile, *, images: ImageStore,
              options: ParseOptions) -> List[Chapter]:
        return htmlbook.parse_source(source, images, options)


__all__ = ["HtmlInput"]
