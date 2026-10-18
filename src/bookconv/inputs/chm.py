"""CHM 输入插件。

CHM 是微软的压缩帮助文件格式，纯 Python 解 LZX 太折腾，所以这里调用系统
工具解包（按顺序尝试 ``7z`` / ``7zz`` / ``unar`` / ``bsdtar``）：

* macOS: ``brew install p7zip``（或 ``brew install unar``）
* Debian/Ubuntu: ``apt install p7zip-full``

解包之后就是一个普通 HTML 目录，交给 :mod:`bookconv.inputs.htmlbook` 处理：
优先用 ``.hhc`` 目录，其次 EasyCHM 的 ``page.js``，最后按入口页/文件名排序。
"""

from __future__ import annotations

import atexit
import os
import shutil
import subprocess
import tempfile
from typing import Dict, List, Tuple

from ..images import ImageStore
from ..models import BookMeta, Chapter
from . import htmlbook
from .base import InputError, InputFormat, ParseOptions, SourceFile

CONTENT_EXTS = (".html", ".htm", ".xhtml", ".shtml", ".txt", ".hhc")
CONTENT_NAMES = ("page.js", "pages.js")


def _has_content(root: str) -> bool:
    for _dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            lower = name.lower()
            if lower.endswith(CONTENT_EXTS) or lower in CONTENT_NAMES:
                return True
    return False


def _unwrap_single_dir(root: str) -> str:
    """有些工具会多套一层目录。"""
    for _ in range(3):
        entries = os.listdir(root)
        # CHM 里的 #SYSTEM / #IVB 等是元数据，不算内容
        files = [name for name in entries
                 if os.path.isfile(os.path.join(root, name))
                 and not name.startswith("#")]
        dirs = [name for name in entries
                if os.path.isdir(os.path.join(root, name))]
        if files or not dirs:
            return root
        if len(dirs) == 1:
            root = os.path.join(root, dirs[0])
            continue
        # 多个目录说明可能是作品集，保留根目录让 HTML 插件递归找
        return root
    return root


def _commands(path: str, target: str) -> List[Tuple[str, List[str]]]:
    return [
        ("7z", ["7z", "x", "-y", "-bd", "-o" + target, path]),
        ("7zz", ["7zz", "x", "-y", "-bd", "-o" + target, path]),
        ("7za", ["7za", "x", "-y", "-bd", "-o" + target, path]),
        ("unar", ["unar", "-q", "-o", target, path]),
        ("bsdtar", ["bsdtar", "-xf", path, "-C", target]),
    ]


def extract_chm(path: str, workdir: str) -> str:
    """把 CHM 解包到 workdir 下的子目录，返回真正的根目录。"""
    errors: List[str] = []
    available = 0

    for index, _ in enumerate(_commands(path, "")):
        target = os.path.join(workdir, "extract-%d" % index)
        command = _commands(path, target)[index]
        tool, command = command
        if shutil.which(tool) is None:
            continue
        available += 1
        os.makedirs(target, exist_ok=True)

        try:
            result = subprocess.run(command, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, timeout=300)
        except (OSError, subprocess.SubprocessError) as error:
            errors.append("%s: %s" % (tool, error))
            shutil.rmtree(target, ignore_errors=True)
            continue

        if result.returncode == 0 and _has_content(target):
            return _unwrap_single_dir(target)

        message = result.stderr.decode("utf-8", "replace").strip()
        if not message:
            message = result.stdout.decode("utf-8", "replace").strip()
        errors.append("%s (exit %d): %s" % (tool, result.returncode,
                                            message.splitlines()[-1]
                                            if message else "没有解出文件"))
        shutil.rmtree(target, ignore_errors=True)

    hint = ""
    if not any(shutil.which(tool) for tool in ("7z", "7zz", "7za", "unar")):
        hint = ("；CHM 最好用 7z/unar 解包：macOS 可 brew install p7zip，"
                "Debian/Ubuntu 可 apt install p7zip-full")
    if available == 0:
        raise InputError("解包 CHM 需要 7z、unar 或 bsdtar，但都没找到" + hint)
    raise InputError("无法解包 CHM '%s'：%s%s"
                     % (path, "; ".join(errors), hint))


class ChmInput(InputFormat):
    name = "chm"
    extensions = ("chm",)

    def __init__(self) -> None:
        self._roots: Dict[str, str] = {}

    def _root(self, source: SourceFile) -> str:
        path = os.path.abspath(source.path)
        if path in self._roots:
            return self._roots[path]
        if not os.path.isfile(path):
            raise InputError("CHM 文件不存在: %s" % path)

        workdir = tempfile.mkdtemp(prefix="bookconv-chm-")
        atexit.register(shutil.rmtree, workdir, ignore_errors=True)
        root = extract_chm(path, workdir)
        self._roots[path] = root
        return root

    def metadata(self, source: SourceFile) -> BookMeta:
        return htmlbook.metadata_for_dir(self._root(source))

    def parse(self, source: SourceFile, *, images: ImageStore,
              options: ParseOptions) -> List[Chapter]:
        return htmlbook.parse_directory(self._root(source), images, options)


__all__ = ["ChmInput", "extract_chm"]
