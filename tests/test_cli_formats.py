"""新输入格式的端到端测试（HTML 目录 / AsciiDoc / CHM）。"""

import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile

from cvbook.cli import main


class CliFormatTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp.name)

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.tmp.cleanup()

    def write(self, name, text):
        directory = os.path.dirname(name)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(name, "w", encoding="utf-8") as f:
            f.write(text)

    def read_html(self, epub, suffix):
        with zipfile.ZipFile(epub) as z:
            name = next(n for n in z.namelist() if n.endswith(suffix))
            return z.read(name).decode("utf-8")

    def opf(self, epub):
        return self.read_html(epub, ".opf")

    def test_html_directory(self):
        self.write("book/index.html", """\
<html><head><title>目录书</title><meta name="author" content="甲"></head>
<body><a href="001.html">第一章</a><a href="002.html">第二章</a></body></html>
""")
        self.write("book/001.html",
                   "<html><body><h1>第一章</h1><p>正文一</p></body></html>")
        self.write("book/002.html",
                   "<html><body><h1>第二章</h1><p>正文二</p></body></html>")

        self.assertEqual(main(["book/"]), 0)
        self.assertTrue(os.path.isfile("book.epub"))
        opf = self.opf("book.epub")
        self.assertIn("<dc:title>目录书</dc:title>", opf)
        self.assertIn(">甲</dc:creator>", opf)
        nav = self.read_html("book.epub", "nav.xhtml")
        self.assertIn("第一章", nav)
        self.assertIn("第二章", nav)

    def test_asciidoc_file(self):
        self.write("book.adoc", """\
= AsciiDoc 书
:author: 乙

== 第一章

正文。
""")
        self.assertEqual(main(["book.adoc"]), 0)
        self.assertTrue(os.path.isfile("book.epub"))
        opf = self.opf("book.epub")
        self.assertIn("<dc:title>AsciiDoc 书</dc:title>", opf)
        self.assertIn(">乙</dc:creator>", opf)

    @unittest.skipUnless(shutil.which("7z"), "需要 7z")
    def test_chm_file(self):
        os.makedirs("src")
        self.write("src/index.html", """\
<html><head><title>CHM 书</title></head><body>
<a href="001.html">第一章</a></body></html>
""")
        self.write("src/001.html",
                   "<html><body><h1>第一章</h1><p>正文</p></body></html>")
        result = subprocess.run(
            ["7z", "a", "-t7z", "-y", os.path.abspath("book.chm"), "."],
            cwd="src", stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        if result.returncode != 0:
            self.skipTest("7z 无法创建测试包")

        self.assertEqual(main(["book.chm"]), 0)
        self.assertTrue(os.path.isfile("book.epub"))
        self.assertIn("<dc:title>CHM 书</dc:title>", self.opf("book.epub"))


if __name__ == "__main__":
    unittest.main()
