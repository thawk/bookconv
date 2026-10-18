"""插图收集：去重、命名、格式处理。

Markdown 里的 ![](pic.png) 是相对源文件目录的，生成的章节文件在 EPUB 的
text/ 目录下，所以要把图片复制进 EPUB 并改写成 ../images/xxx 这样的路径。
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import Dict, List, Optional

MEDIA_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "svg": "image/svg+xml",
    "webp": "image/webp",
}

#: 允许的图片扩展名（cover 查找也用这套）
IMAGE_EXTS = tuple(MEDIA_TYPES)

_SAFE_NAME_RE = re.compile(r"[^\w.\-]+", re.UNICODE)


@dataclass
class EpubImage:
    path: str          #: EPUB 内路径，如 images/pic.png
    media_type: str
    data: bytes


def image_size(data: bytes) -> Optional[tuple]:
    """读 PNG/JPEG 的像素尺寸（不依赖第三方库）。"""
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        width = int.from_bytes(data[16:20], "big")
        height = int.from_bytes(data[20:24], "big")
        return (width, height) if width and height else None

    if data[:2] != b"\xff\xd8":               # 不是 JPEG
        return None

    offset = 2
    while offset + 9 < len(data):
        if data[offset] != 0xFF:
            offset += 1
            continue
        marker = data[offset + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            offset += 2
            continue
        length = int.from_bytes(data[offset + 2:offset + 4], "big")
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            height = int.from_bytes(data[offset + 5:offset + 7], "big")
            width = int.from_bytes(data[offset + 7:offset + 9], "big")
            return (width, height) if width and height else None
        offset += 2 + length
    return None


def media_type_for(name: str) -> Optional[str]:
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return MEDIA_TYPES.get(ext)


def convert_image(data: bytes, source_name: str, target_ext: str = "png") -> Optional[bytes]:
    """用系统工具（sips / ImageMagick）转换图片格式，失败返回 None。"""
    tools = []
    if shutil.which("sips"):
        tools.append("sips")
    if shutil.which("convert"):
        tools.append("convert")
    if not tools:
        return None

    workdir = tempfile.mkdtemp(prefix="cvbook-img.")
    try:
        source = os.path.join(workdir, "in." + (source_name.rsplit(".", 1)[-1].lower() or "webp"))
        target = os.path.join(workdir, "out." + target_ext)
        with open(source, "wb") as f:
            f.write(data)

        for tool in tools:
            if tool == "sips":
                cmd = ["sips", "-s", "format", target_ext, source, "--out", target]
            else:
                cmd = ["convert", source, target]
            try:
                if subprocess.call(cmd, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL) == 0:
                    with open(target, "rb") as f:
                        return f.read()
            except OSError:
                continue
        return None
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def safe_name(name: str) -> str:
    """把文件名收拾成适合进 EPUB 的样子（保留中文）。"""
    name = _SAFE_NAME_RE.sub("_", name).strip("._") or "image"
    return name


def sniff_image_ext(data: bytes) -> Optional[str]:
    """从文件头猜图片格式（给没有扩展名或扩展名不对的插图用）。"""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    head = data[:512].lstrip()
    if head.startswith(b"\xef\xbb\xbf"):
        head = head[3:].lstrip()
    head = head.lower()
    if head.startswith(b"<svg") or (head.startswith(b"<?xml") and b"<svg" in data[:2048].lower()):
        return "svg"
    return None


class ImageStore:
    """收集正文里的插图，按源文件去重，分配 EPUB 内路径。"""

    def __init__(self) -> None:
        self._by_source: Dict[str, str] = {}
        self._used_names: Dict[str, str] = {}
        self.items: List[EpubImage] = []

    def add(self, source: str) -> Optional[str]:
        """登记一张本地图片，返回 EPUB 内路径；读不到文件时返回 None。"""
        source = os.path.abspath(source)
        if source in self._by_source:
            return self._by_source[source]

        try:
            with open(source, "rb") as f:
                data = f.read()
        except OSError:
            return None

        return self.add_bytes(os.path.basename(source), data, source=source)

    def add_bytes(self, name: str, data: bytes,
                  source: Optional[str] = None) -> Optional[str]:
        """登记内存里的图片（HTML/CHM/远程插图用）。

        ``source`` 是去重键（本地路径、URL 或任意唯一标识）；不传时按内容
        哈希去重。返回 EPUB 内路径，格式不支持时返回 None。
        """
        key = source or "sha1:" + hashlib.sha1(data).hexdigest()
        if key in self._by_source:
            return self._by_source[key]

        name = safe_name(os.path.basename(name))
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        sniffed = sniff_image_ext(data)
        if sniffed is not None and sniffed != ext:
            # 扩展名和实际内容不一致时以内容为准（网页上 .jpg 里装 png 很常见）
            name = os.path.splitext(name)[0] + "." + sniffed
            ext = sniffed
        elif ext not in MEDIA_TYPES:
            print("!!! 忽略不支持的图片格式: %s" % (source or name),
                  file=sys.stderr)
            return None

        if ext == "webp":
            converted = convert_image(data, name, "png")
            if converted is not None:
                name = os.path.splitext(name)[0] + ".png"
                data = converted
                ext = "png"
            else:
                print("!!! 无法转换 webp 图片，按原格式嵌入: %s"
                      % (source or name), file=sys.stderr)

        # 同名不同图时加后缀
        path = "images/" + name
        if path in self._used_names and self._used_names[path] != key:
            stem, dot, suffix = name.rpartition(".")
            index = 2
            while path in self._used_names:
                candidate = ("%s-%d.%s" % (stem, index, suffix) if dot
                             else "%s-%d" % (name, index))
                path = "images/" + candidate
                index += 1

        self._by_source[key] = path
        self._used_names[path] = key
        self.items.append(EpubImage(path, MEDIA_TYPES[ext], data))
        return path
