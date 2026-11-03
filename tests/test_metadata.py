"""书名/作者兜底解析、封面查找的测试。"""

import base64
import os
import tempfile
import unittest

from bookconv.metadata import (bookcover_base_name, find_cover, resolve_meta)
from bookconv.models import BookMeta

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAE"
    "hQGAhKmMIQAAAABJRU5ErkJggg=="
)


class FindCoverTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def touch(self, name, data=PNG):
        path = os.path.join(self.dir, name)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def test_bookcover_base_name(self):
        self.assertEqual(bookcover_base_name("书", "甲"), "《书》作者：甲")
        self.assertEqual(bookcover_base_name("A/B", ""), "《A／B》作者：未知")

    def test_same_stem_cover_wins(self):
        source = self.touch("书.txt")
        same = self.touch("书.jpg")
        self.touch("《书》作者：甲.jpg")
        meta = BookMeta(title="书", authors=["甲"])
        self.assertEqual(find_cover(source, meta), same)

    def test_bookcover_fallback(self):
        source = self.touch("《书》（校对版全本）作者：甲.txt")
        cover = self.touch("《书》作者：甲.jpg")
        meta = resolve_meta(source)
        self.assertEqual(find_cover(source, meta), cover)

    def test_bookcover_fallback_without_meta(self):
        source = self.touch("《书》（校对版全本）作者：甲.txt")
        self.touch("《书》作者：甲.jpg")
        self.assertIsNone(find_cover(source))

    def test_bookcover_unknown_author(self):
        source = self.touch("书.txt")
        cover = self.touch("《书》作者：未知.png")
        self.assertEqual(find_cover(source, BookMeta(title="书")), cover)

    def test_bookcover_tries_each_author(self):
        source = self.touch("书.txt")
        cover = self.touch("《书》作者：乙.jpg")
        meta = BookMeta(title="书", authors=["甲", "乙"])
        self.assertEqual(find_cover(source, meta), cover)

    def test_empty_same_stem_cover_is_skipped(self):
        source = self.touch("书.txt")
        self.touch("书.jpg", b"")
        cover = self.touch("《书》作者：甲.jpg")
        meta = BookMeta(title="书", authors=["甲"])
        self.assertEqual(find_cover(source, meta), cover)

    def test_invalid_same_stem_cover_is_skipped(self):
        source = self.touch("书.txt")
        self.touch("书.jpg", b"not an image")
        cover = self.touch("《书》作者：甲.jpg")
        meta = BookMeta(title="书", authors=["甲"])
        self.assertEqual(find_cover(source, meta), cover)

    def test_missing_cover(self):
        source = self.touch("书.txt")
        meta = BookMeta(title="书", authors=["甲"])
        self.assertIsNone(find_cover(source, meta))

    def test_directory_cover_wins(self):
        directory = os.path.join(self.dir, "book")
        os.mkdir(directory)
        same = os.path.join(directory, "cover.jpg")
        with open(same, "wb") as f:
            f.write(PNG)
        with open(os.path.join(directory, "《书》作者：甲.jpg"), "wb") as f:
            f.write(PNG)
        meta = BookMeta(title="书", authors=["甲"])
        self.assertEqual(find_cover(directory, meta), same)

    def test_directory_bookcover_fallback(self):
        directory = os.path.join(self.dir, "book")
        os.mkdir(directory)
        cover = os.path.join(directory, "《书》作者：甲.jpg")
        with open(cover, "wb") as f:
            f.write(PNG)
        self.assertEqual(find_cover(directory, BookMeta(title="书", authors=["甲"])),
                         cover)

    def test_url_has_no_cover(self):
        self.assertIsNone(find_cover("https://example.com/book",
                                     BookMeta(title="书")))


if __name__ == "__main__":
    unittest.main()
