"""EPUB 组装的测试（解压生成的 epub 检查结构）。"""

import base64
import os
import re
import tempfile
import unittest
import zipfile

from cvbook.epub import build_epub
from cvbook.images import EpubImage
from cvbook.models import BookMeta, Chapter

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAE"
    "hQGAhKmMIQAAAABJRU5ErkJggg=="
)


class BuildEpubTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = os.path.join(self.tmp.name, "book.epub")
        meta = BookMeta(title="测试书名", authors=["张三", "李四"],
                        comments="简介文字。")
        chapters = [
            Chapter("第1章", '<h1 id="c1">第1章</h1><p>正文一。</p>'),
            Chapter("第2章", '<h1 id="c2">第2章</h1><p>正文二。</p>'),
        ]
        cover = EpubImage("images/cover.png", "image/png", PNG)
        build_epub(self.out, meta, chapters, css="body{color:red}",
                   cover=cover, intro_html="<p>简介文字。</p>")
        self.zip = zipfile.ZipFile(self.out)
        self.names = self.zip.namelist()

    def tearDown(self):
        self.zip.close()
        self.tmp.cleanup()

    def read(self, name):
        return self.zip.read(name).decode("utf-8")

    def opf(self):
        name = next(n for n in self.names if n.endswith(".opf"))
        return self.read(name)

    def html(self, suffix):
        return self.read(next(n for n in self.names if n.endswith(suffix)))

    def test_mimetype_first_and_stored(self):
        first = self.zip.infolist()[0]
        self.assertEqual(first.filename, "mimetype")
        self.assertEqual(first.compress_type, zipfile.ZIP_STORED)
        self.assertEqual(self.zip.read("mimetype"), b"application/epub+zip")

    def test_container(self):
        self.assertIn("META-INF/container.xml", self.names)

    def test_metadata(self):
        opf = self.opf()
        self.assertIn("<dc:title>测试书名</dc:title>", opf)
        self.assertIn("<dc:creator", opf)
        self.assertIn("张三", opf)
        self.assertIn("李四", opf)
        self.assertIn("<dc:description>简介文字。</dc:description>", opf)
        self.assertIn("<dc:language>zh</dc:language>", opf)
        self.assertIn('properties="cover-image"', opf)
        self.assertIn('properties="nav"', opf)

    def test_cover_page(self):
        page = self.html("cover.xhtml")
        self.assertIn('class="page cover first"', page)
        self.assertIn('<img class="cover-image" src="images/cover.png"', page)

    def test_titlepage_and_intro(self):
        self.assertIn('class="page titlepage"', self.html("titlepage.xhtml"))
        self.assertIn("<h1 class=\"book-title\">测试书名</h1>",
                      self.html("titlepage.xhtml"))
        intro = self.html("intro.xhtml")
        self.assertIn('class="page intro"', intro)
        self.assertIn("<p>简介文字。</p>", intro)

    def test_chapters(self):
        page = self.html("chapter-0001.xhtml")
        self.assertIn('class="page chapter"', page)
        self.assertIn('href="../css/style.css"', page)
        self.assertIn("<h1 id=\"c1\">第1章</h1>", page)

    def test_stylesheet_embedded(self):
        self.assertIn("body{color:red}", self.read("EPUB/css/style.css"))

    def test_toc(self):
        nav = self.html("nav.xhtml")
        self.assertIn("第1章", nav)
        self.assertIn("第2章", nav)
        ncx = self.html("toc.ncx")
        self.assertEqual(len(re.findall(r"<navPoint ", ncx)), 2)

    def test_spine_order(self):
        opf = self.opf()
        self.assertLess(opf.index('idref="cover"'), opf.index('idref="chap-0001"'))

    def test_nav_not_in_spine(self):
        opf = self.opf()
        self.assertIn('id="nav"', opf)               # nav 文档还在 manifest 里
        self.assertNotIn('idref="nav"', opf)         # 但不排进正文
        self.assertLess(opf.index('idref="titlepage"'),
                        opf.index('idref="chap-0001"'))


class NestedTocTest(unittest.TestCase):
    def test_volumes_nest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, "nested.epub")
            meta = BookMeta(title="分卷书", authors=["作者"])
            chapters = [
                Chapter("第一卷", "<h1>第一卷</h1>", level=1),
                Chapter("第1章", "<h1>第1章</h1>", level=2),
                Chapter("第2章", "<h1>第2章</h1>", level=2),
                Chapter("第二卷", "<h1>第二卷</h1>", level=1),
            ]
            build_epub(out, meta, chapters, css="")
            with zipfile.ZipFile(out) as z:
                nav = z.read("EPUB/nav.xhtml").decode("utf-8")
            # 第一卷下面应该有一个嵌套的 <ol>
            self.assertRegex(nav, r"(?s)第一卷.*?<ol>.*?第1章.*?</ol>")


if __name__ == "__main__":
    unittest.main()
