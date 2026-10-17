"""端到端测试：cli.main() 生成 epub。"""

import base64
import os
import tempfile
import unittest
import zipfile

from cvbook.cli import main

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAE"
    "hQGAhKmMIQAAAABJRU5ErkJggg=="
)

BOOK_MD = """\
---

title: 测试书名

authors: 幸福来敲门

comments: |

　　第一段简介。

　　第二段简介。

---

# 第0001章 少年和媳妇

　　正文一。

# 第0002章 家有悍妇

　　正文二。
"""


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmp.name)

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.tmp.cleanup()

    def write(self, name, text, binary=False):
        with open(name, "wb" if binary else "w",
                  **({} if binary else {"encoding": "utf-8"})) as f:
            f.write(text)
        return name

    def opf(self, epub):
        with zipfile.ZipFile(epub) as z:
            name = next(n for n in z.namelist() if n.endswith(".opf"))
            return z.read(name).decode("utf-8")

    def html(self, epub, suffix):
        with zipfile.ZipFile(epub) as z:
            name = next(n for n in z.namelist() if n.endswith(suffix))
            return z.read(name).decode("utf-8")

    def test_markdown_with_frontmatter_and_cover(self):
        self.write("book.md", BOOK_MD)
        self.write("book.png", PNG, binary=True)
        self.assertEqual(main(["book.md"]), 0)

        self.assertTrue(os.path.isfile("book.epub"))
        opf = self.opf("book.epub")
        self.assertIn("<dc:title>测试书名</dc:title>", opf)
        self.assertIn("幸福来敲门", opf)
        self.assertIn("第一段简介。", opf)
        self.assertIn("cover.png", opf)
        # frontmatter 不该出现在正文页里
        chapter = self.html("book.epub", "chapter-0001.xhtml")
        self.assertNotIn("title:", chapter)

    def test_filename_fallback(self):
        self.write("《无头》作者：某人.md", "# 第1章\n\n正文\n")
        self.assertEqual(main(["《无头》作者：某人.md"]), 0)
        opf = self.opf("《无头》作者：某人.epub")
        self.assertIn("<dc:title>无头</dc:title>", opf)
        self.assertIn("某人", opf)

    def test_custom_style(self):
        self.write("book.md", BOOK_MD)
        self.write("my.css", "/* 自定义样式 */\n.chapter p{color:blue}\n")
        self.assertEqual(main(["-s", "my.css", "book.md"]), 0)
        with zipfile.ZipFile("book.epub") as z:
            css = z.read("EPUB/css/style.css").decode("utf-8")
        self.assertIn("自定义样式", css)
        self.assertNotIn("Songti SC", css)      # 默认样式被整体替换

    def test_extra_style_appends(self):
        self.write("book.md", BOOK_MD)
        self.write("fix.css", ".chapter p{color:red}\n")
        self.assertEqual(main(["--extra-style", "fix.css", "book.md"]), 0)
        with zipfile.ZipFile("book.epub") as z:
            css = z.read("EPUB/css/style.css").decode("utf-8")
        self.assertIn("Songti SC", css)         # 默认样式还在
        self.assertIn("color:red", css)

    def test_no_intro_and_no_titlepage(self):
        self.write("book.md", BOOK_MD)
        self.assertEqual(main(["--no-intro", "--no-titlepage", "book.md"]), 0)
        with zipfile.ZipFile("book.epub") as z:
            names = z.namelist()
        self.assertFalse(any(n.endswith("intro.xhtml") for n in names))
        self.assertFalse(any(n.endswith("titlepage.xhtml") for n in names))

    def test_missing_metadata(self):
        self.write("plain.md", "# 第1章\n\n正文\n")
        self.assertEqual(main(["plain.md"]), 1)
        self.assertFalse(os.path.exists("plain.epub"))

    def test_txt_input(self):
        self.write("《txt 书》作者：甲.txt",
                   "第一卷 风起\n\n第1章 开始\n第一段。\n第二段。\n\n第2章 继续\n内容。\n")
        self.assertEqual(main(["《txt 书》作者：甲.txt"]), 0)
        opf = self.opf("《txt 书》作者：甲.epub")
        self.assertIn("<dc:title>txt 书</dc:title>", opf)
        chapter = self.html("《txt 书》作者：甲.epub", "chapter-0002.xhtml")
        self.assertIn("第1章 开始", chapter)
        self.assertIn("<p>第一段。</p>", chapter)
        # 卷下面是二级目录
        nav = self.html("《txt 书》作者：甲.epub", "nav.xhtml")
        self.assertRegex(nav, r"(?s)第一卷 风起.*?<ol>.*?第1章 开始")

    def test_unknown_input_format(self):
        self.write("book.md", BOOK_MD)
        with self.assertRaises(SystemExit) as raised:   # argparse 拒绝
            main(["-i", "nope", "book.md"])
        self.assertEqual(raised.exception.code, 2)

    def write_parts(self):
        self.write("a.md", BOOK_MD)
        second = "《第二部》作者：幸福来敲门.md"
        self.write(second, "# 第0003章 尾声\n\n　　正文三。\n")
        return "a.md", second

    def test_batch_multiple_files(self):
        a, b = self.write_parts()
        self.assertEqual(main([a, b]), 0)
        self.assertTrue(os.path.isfile("a.epub"))
        second_epub = os.path.splitext(b)[0] + ".epub"
        self.assertTrue(os.path.isfile(second_epub))
        self.assertIn("第0003章 尾声",
                      self.html(second_epub, "chapter-0001.xhtml"))

    def test_merge(self):
        a, b = self.write_parts()
        self.assertEqual(main(["--merge", a, b]), 0)
        self.assertTrue(os.path.isfile("a.epub"))
        self.assertFalse(os.path.exists(os.path.splitext(b)[0] + ".epub"))
        with zipfile.ZipFile("a.epub") as z:
            chapters = [n for n in z.namelist()
                        if "chapter-" in n and n.endswith(".xhtml")]
        self.assertEqual(len(chapters), 3)
        opf = self.opf("a.epub")
        self.assertIn("<dc:title>测试书名</dc:title>", opf)
        self.assertIn("第0003章 尾声", self.html("a.epub", "chapter-0003.xhtml"))

    def test_merge_with_output(self):
        a, b = self.write_parts()
        self.assertEqual(main(["--merge", "-o", "全本.epub", a, b]), 0)
        self.assertTrue(os.path.isfile("全本.epub"))

    def test_output_single_file(self):
        self.write("book.md", BOOK_MD)
        self.assertEqual(main(["-o", "custom.epub", "book.md"]), 0)
        self.assertTrue(os.path.isfile("custom.epub"))

    def test_output_with_multiple_files_needs_merge(self):
        a, b = self.write_parts()
        self.assertEqual(main(["-o", "x.epub", a, b]), 2)
        self.assertFalse(os.path.exists("x.epub"))

    def test_cover_option(self):
        self.write("book.md", BOOK_MD)
        self.write("my-cover.png", PNG, binary=True)
        self.assertEqual(main(["--cover", "my-cover.png", "book.md"]), 0)
        opf = self.opf("book.epub")
        self.assertIn('properties="cover-image"', opf)
        with zipfile.ZipFile("book.epub") as z:
            self.assertIn("EPUB/images/cover.png", z.namelist())

    def test_verbose_runs(self):
        self.write("book.md", BOOK_MD)
        self.assertEqual(main(["-v", "book.md"]), 0)


if __name__ == "__main__":
    unittest.main()
