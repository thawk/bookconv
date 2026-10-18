"""EPUB 输入插件与 Markdown 输出的测试。"""

import base64
import os
import tempfile
import unittest
import zipfile

from ebooklib import epub

from cvbook.cli import main
from cvbook.images import ImageStore
from cvbook.inputs.base import ParseOptions, SourceFile
from cvbook.inputs.epub import EpubInput

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAE"
    "hQGAhKmMIQAAAABJRU5ErkJggg=="
)


def build_epub(path, *, with_toc=True, with_cover=True):
    book = epub.EpubBook()
    book.set_identifier("cvbook-test-epub")
    book.set_title("EPUB 测试书")
    book.set_language("zh")
    book.add_author("张三")
    book.add_metadata("DC", "description", "这是一本测试书。")

    if with_cover:
        book.set_cover("cover.png", PNG, create_page=False)

    image = epub.EpubItem(uid="img1", file_name="images/pic.png",
                          media_type="image/png", content=PNG)
    book.add_item(image)

    first = epub.EpubHtml(title="第一章", file_name="text/c1.xhtml", lang="zh")
    first.content = ("<html><body><h1>第一章</h1><p>正文一</p>"
                     '<img src="../images/pic.png" alt="插图"/></body></html>')
    second = epub.EpubHtml(title="第二章", file_name="text/c2.xhtml", lang="zh")
    second.content = ("<html><body><h1>第二章</h1><p>正文二</p>"
                      "</body></html>")
    book.add_item(first)
    book.add_item(second)
    if with_toc:
        book.toc = ((epub.Section("第一卷"), (first, second)),)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", first, second]
    epub.write_epub(path, book)
    return path


class EpubInputTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "source.epub")
        build_epub(self.path)
        self.fmt = EpubInput()

    def tearDown(self):
        self.tmp.cleanup()

    def test_metadata(self):
        meta = self.fmt.metadata(SourceFile(self.path, b""))
        self.assertEqual(meta.title, "EPUB 测试书")
        self.assertEqual(meta.authors, ["张三"])
        self.assertEqual(meta.comments, "这是一本测试书。")

    def test_cover(self):
        cover = self.fmt.cover(SourceFile(self.path, b""))
        self.assertIsNotNone(cover)
        self.assertEqual(cover.path, "images/cover.png")
        self.assertEqual(cover.media_type, "image/png")

    def test_chapters(self):
        images = ImageStore()
        chapters = self.fmt.parse(SourceFile(self.path, b""),
                                  images=images, options=ParseOptions())
        self.assertEqual([c.title for c in chapters],
                         ["第一卷", "第一章", "第二章"])
        self.assertEqual([c.level for c in chapters], [1, 2, 2])
        self.assertIn("正文一", chapters[1].html)
        self.assertIn('src="../images/pic.png"', chapters[1].html)
        self.assertEqual([image.path for image in images.items],
                         ["images/pic.png"])

    def test_without_toc_uses_spine(self):
        path = os.path.join(self.tmp.name, "notoc.epub")
        build_epub(path, with_toc=False, with_cover=False)
        chapters = self.fmt.parse(SourceFile(path, b""),
                                  images=ImageStore(), options=ParseOptions())
        self.assertEqual([c.title for c in chapters], ["第一章", "第二章"])


class MarkdownOutputTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp.name)
        self.source = build_epub(os.path.join(self.tmp.name, "source.epub"))

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.tmp.cleanup()

    def read(self, path):
        with open(path, encoding="utf-8") as f:
            return f.read()

    def opf(self, path):
        with zipfile.ZipFile(path) as z:
            name = next(n for n in z.namelist() if n.endswith(".opf"))
            return z.read(name).decode("utf-8")

    def test_epub_to_markdown(self):
        self.assertEqual(main(["-f", "md", self.source]), 0)
        text = self.read("source.md")
        self.assertIn('title: "EPUB 测试书"', text)
        self.assertIn('- "张三"', text)
        self.assertIn("comments: |", text)
        self.assertIn("# 第一卷", text)
        self.assertIn("## 第一章", text)
        self.assertIn("正文一", text)
        self.assertIn("![插图](source.images/pic.png)", text)
        self.assertTrue(os.path.isfile("source.images/pic.png"))
        self.assertTrue(os.path.isfile("source.png"))     # 封面

    def test_no_frontmatter(self):
        self.assertEqual(main(["-f", "md", "--no-frontmatter",
                               "-o", "plain.md", self.source]), 0)
        text = self.read("plain.md")
        self.assertFalse(text.startswith("---"))
        self.assertTrue(text.startswith("# 第一卷"))
        self.assertTrue(os.path.isfile("plain.images/pic.png"))

    def test_epub_to_epub_preserves_cover_and_images(self):
        self.assertEqual(main([self.source]), 0)
        output = "source-converted.epub"
        self.assertTrue(os.path.isfile(output))
        with zipfile.ZipFile(output) as z:
            names = z.namelist()
            self.assertIn("EPUB/images/cover.png", names)
            self.assertIn("EPUB/images/pic.png", names)
            self.assertIn("EPUB/cover.xhtml", names)
        opf = self.opf(output)
        self.assertIn("<dc:title>EPUB 测试书</dc:title>", opf)
        self.assertIn(">张三</dc:creator>", opf)

    def test_markdown_roundtrip(self):
        self.assertEqual(main(["-f", "md", self.source]), 0)
        self.assertEqual(main(["-o", "roundtrip.epub", "source.md"]), 0)
        opf = self.opf("roundtrip.epub")
        self.assertIn("<dc:title>EPUB 测试书</dc:title>", opf)
        self.assertIn(">张三</dc:creator>", opf)
        with zipfile.ZipFile("roundtrip.epub") as z:
            names = z.namelist()
            self.assertIn("EPUB/images/cover.png", names)
            self.assertIn("EPUB/images/pic.png", names)
            nav_name = next(n for n in names if n.endswith("nav.xhtml"))
            nav = z.read(nav_name).decode("utf-8")
        self.assertIn("第一卷", nav)
        self.assertIn("第一章", nav)
        self.assertIn("第二章", nav)

    def test_h2_only_markdown_splits_chapters(self):
        with open("h2.md", "w", encoding="utf-8") as f:
            f.write("---\ntitle: H2 书\n---\n\n"
                    "## 第一章\n\n正文一\n\n## 第二章\n\n正文二\n")
        self.assertEqual(main(["-o", "h2.epub", "h2.md"]), 0)
        with zipfile.ZipFile("h2.epub") as z:
            name = next(n for n in z.namelist() if n.endswith("nav.xhtml"))
            nav = z.read(name).decode("utf-8")
        self.assertIn("第一章", nav)
        self.assertIn("第二章", nav)

    def test_volume_and_chapters_are_separate_pages(self):
        with open("vol.md", "w", encoding="utf-8") as f:
            f.write("---\ntitle: 分卷书\n---\n\n"
                    "# 第一卷\n\n卷首语\n\n"
                    "## 第一章\n\n第一章正文\n\n"
                    "## 第二章\n\n第二章正文\n")
        self.assertEqual(main(["-o", "vol.epub", "vol.md"]), 0)
        with zipfile.ZipFile("vol.epub") as z:
            names = [n for n in z.namelist()
                     if n.startswith("EPUB/text/chapter-")]
            self.assertEqual(len(names), 3)
            pages = [z.read(name).decode("utf-8") for name in names]
        self.assertIn("卷首语", pages[0])
        self.assertIn("第一章正文", pages[1])
        self.assertIn("第二章正文", pages[2])

    def test_title_only_parent_is_toc_group(self):
        with open("title.md", "w", encoding="utf-8") as f:
            f.write("---\ntitle: 只有标题\n---\n\n"
                    "# title1\n\n## title2\n\ntext\n")
        self.assertEqual(main(["-o", "title.epub", "title.md"]), 0)
        with zipfile.ZipFile("title.epub") as z:
            names = [n for n in z.namelist()
                     if n.startswith("EPUB/text/chapter-")]
            self.assertEqual(len(names), 1)       # title1 不建空页
            nav_name = next(n for n in z.namelist()
                            if n.endswith("nav.xhtml"))
            nav = z.read(nav_name).decode("utf-8")
        self.assertIn("title1", nav)
        self.assertIn("title2", nav)
        self.assertIn("<span>title1</span>", nav)

    def test_markdown_output_from_markdown_input(self):
        with open("《源书》作者：甲.md", "w", encoding="utf-8") as f:
            f.write("# 第一章\n\n正文。\n")
        self.assertEqual(main(["-f", "md", "《源书》作者：甲.md"]), 0)
        text = self.read("《源书》作者：甲-converted.md")
        self.assertIn('title: "源书"', text)
        self.assertIn('- "甲"', text)

    def test_merge_markdown(self):
        with open("a.md", "w", encoding="utf-8") as f:
            f.write("---\ntitle: 合集\nauthors: 甲\n---\n\n# 第一章\n\n正文一\n")
        with open("b.md", "w", encoding="utf-8") as f:
            f.write("# 第二章\n\n正文二\n")
        self.assertEqual(main(["--merge", "-f", "md", "-o", "all.md",
                               "a.md", "b.md"]), 0)
        text = self.read("all.md")
        self.assertIn('title: "合集"', text)
        self.assertIn("# 第一章", text)
        self.assertIn("# 第二章", text)

    def test_epub_metadata_wins_over_filename(self):
        path = build_epub(os.path.join(self.tmp.name, "《错误》作者：错.epub"))
        self.assertEqual(main(["-f", "md", "-o", "meta.md", path]), 0)
        text = self.read("meta.md")
        self.assertIn('title: "EPUB 测试书"', text)
        self.assertIn('- "张三"', text)

    def test_md_with_legacy_engine_is_rejected(self):
        self.assertEqual(main(["-f", "md", "-m", "calibre", self.source]), 1)

    def test_refuses_to_overwrite_input(self):
        with open(self.source, "rb") as f:
            before = f.read()
        self.assertEqual(main(["-o", self.source, self.source]), 1)
        with open(self.source, "rb") as f:
            self.assertEqual(f.read(), before)


if __name__ == "__main__":
    unittest.main()
