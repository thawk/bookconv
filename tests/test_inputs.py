"""输入插件（markdown / txt）的测试。"""

import base64
import os
import tempfile
import unittest

from cvbook.htmlutil import paragraphs, plain_text, strip_paragraph_indent
from cvbook.images import ImageStore
from cvbook.inputs.base import ParseOptions, SourceFile
from cvbook.inputs.markdown import (MarkdownInput, detect_heading_level,
                                    split_sections)
from cvbook.inputs.txt import TextInput, split_events

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAE"
    "hQGAhKmMIQAAAABJRU5ErkJggg=="
)


class MarkdownSectionTest(unittest.TestCase):
    def test_basic(self):
        text = "# 第1章\n\n正文一\n\n# 第2章\n\n正文二\n"
        sections = split_sections(text)
        self.assertEqual([s.title for s in sections], ["第1章", "第2章"])
        self.assertEqual([s.level for s in sections], [1, 1])
        self.assertIn("正文一", sections[0].chunk)

    def test_preface(self):
        text = "卷首语\n\n# 第1章\n\n正文\n"
        sections = split_sections(text)
        self.assertEqual(sections[0].title, "")
        self.assertEqual(sections[0].level, 0)
        self.assertEqual(sections[1].title, "第1章")

    def test_code_fence_is_not_heading(self):
        text = "# 第1章\n\n```\n# 这不是标题\n```\n\n# 第2章\n"
        sections = split_sections(text)
        self.assertEqual([s.title for s in sections], ["第1章", "第2章"])

    def test_no_heading(self):
        sections = split_sections("只有正文，没有标题。\n")
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0].title, "")
        self.assertEqual(sections[0].level, 0)

    def test_every_heading_is_a_section(self):
        text = "## 第1章\n\n正文\n\n### 小节\n\n内容\n\n## 第2章\n"
        self.assertEqual(detect_heading_level(text), 2)
        sections = split_sections(text)
        self.assertEqual([s.title for s in sections],
                         ["第1章", "小节", "第2章"])
        self.assertEqual([s.level for s in sections], [2, 3, 2])

    def test_mixed_levels(self):
        text = "# 卷一\n\n## 第1章\n\n正文\n\n# 卷二\n"
        sections = split_sections(text)
        self.assertEqual([s.title for s in sections],
                         ["卷一", "第1章", "卷二"])
        self.assertEqual([s.level for s in sections], [1, 2, 1])

    def test_indented_heading(self):
        self.assertEqual(detect_heading_level("  ## 第1章\n\n正文\n"), 2)


class MarkdownInputTest(unittest.TestCase):
    def parse(self, text, base_dir=None, keep_indent=False):
        source = SourceFile(os.path.join(base_dir or "/tmp", "book.md"),
                            text.encode("utf-8"))
        return MarkdownInput().parse(
            source, images=ImageStore(),
            options=ParseOptions(keep_indent=keep_indent))

    def test_title_plain_text(self):
        chapters = self.parse("# 第1章 **重要**\n\n正文\n")
        self.assertEqual(chapters[0].title, "第1章 重要")
        self.assertEqual(chapters[0].level, 1)
        self.assertIn("<h1", chapters[0].html)

    def test_indent_stripped(self):
        chapters = self.parse("# 第1章\n\n　　缩进段落。\n")
        self.assertIn("<p>缩进段落。</p>", chapters[0].html)

    def test_indent_kept(self):
        chapters = self.parse("# 第1章\n\n　　缩进段落。\n", keep_indent=True)
        self.assertIn("缩进段落。", chapters[0].html)
        self.assertEqual(chapters[0].html.count("&#x3000;"), 2)

    def test_no_heading_still_one_chapter(self):
        chapters = self.parse("只有正文。\n")
        self.assertEqual(len(chapters), 1)
        self.assertEqual(chapters[0].title, "正文")

    def test_preface_page(self):
        chapters = self.parse("卷首语\n\n# 第1章\n\n正文\n")
        self.assertEqual(chapters[0].title, "前言")
        self.assertIn("卷首语", chapters[0].html)

    def test_h2_becomes_level_one(self):
        chapters = self.parse("## 第1章\n\n正文\n\n### 小节\n\n内容\n")
        self.assertEqual([c.title for c in chapters], ["第1章", "小节"])
        self.assertEqual([c.level for c in chapters], [1, 2])
        self.assertIn("正文", chapters[0].html)
        self.assertIn("内容", chapters[1].html)
        self.assertIn("<h1", chapters[0].html)
        self.assertIn("<h1", chapters[1].html)

    def test_h3_becomes_level_one(self):
        chapters = self.parse("### 第1章\n\n正文\n\n#### 小节\n\n内容\n")
        self.assertEqual([c.title for c in chapters], ["第1章", "小节"])
        self.assertEqual([c.level for c in chapters], [1, 2])

    def test_every_heading_is_page_or_group(self):
        chapters = self.parse(
            "# 卷一\n\n## 第1章\n\n正文一\n\n"
            "### 小节\n\n小节内容\n\n## 第2章\n\n正文二\n")
        self.assertEqual([c.title for c in chapters],
                         ["卷一", "第1章", "小节", "第2章"])
        self.assertEqual([c.level for c in chapters], [1, 2, 3, 2])
        self.assertTrue(chapters[0].virtual)      # 卷标题下没有正文，只做目录分组
        self.assertFalse(chapters[1].virtual)
        self.assertIn("正文一", chapters[1].html)
        self.assertIn("小节内容", chapters[2].html)
        self.assertIn("正文二", chapters[3].html)

    def test_title_only_parent_is_virtual_group(self):
        chapters = self.parse("# title1\n## title2\ntext\n")
        self.assertEqual([c.title for c in chapters], ["title1", "title2"])
        self.assertTrue(chapters[0].virtual)
        self.assertEqual(chapters[0].html, "")
        self.assertFalse(chapters[1].virtual)
        self.assertIn("text", chapters[1].html)

    def test_terminal_title_only_still_has_page(self):
        chapters = self.parse("# 只有标题\n")
        self.assertEqual(len(chapters), 1)
        self.assertFalse(chapters[0].virtual)
        self.assertIn("只有标题", chapters[0].html)

    def test_heading_page_contains_text_below_it(self):
        chapters = self.parse(
            "# 卷一\n\n卷首语\n\n## 第一章\n\n正文\n")
        self.assertEqual([c.title for c in chapters], ["卷一", "第一章"])
        self.assertIn("卷首语", chapters[0].html)
        self.assertNotIn("正文", chapters[0].html)
        self.assertIn("正文", chapters[1].html)

    def test_image_rewritten(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "pic.png"), "wb") as f:
                f.write(PNG)
            store = ImageStore()
            source = SourceFile(os.path.join(tmpdir, "book.md"),
                                "# 第1章\n\n![插图](pic.png)\n".encode("utf-8"))
            chapters = MarkdownInput().parse(
                source, images=store, options=ParseOptions())
            self.assertIn('src="../images/pic.png"', chapters[0].html)
            self.assertEqual([image.path for image in store.items],
                             ["images/pic.png"])


class TxtInputTest(unittest.TestCase):
    def parse(self, text, pattern=""):
        source = SourceFile("/tmp/book.txt", text.encode("utf-8"))
        return TextInput().parse(source, images=ImageStore(),
                                 options=ParseOptions(chapter_pattern=pattern))

    def test_chapters_and_paragraphs(self):
        text = "第1章 开始\n\n第一段。\n第二段。\n\n第2章 继续\n内容。\n"
        chapters = self.parse(text)
        self.assertEqual([c.title for c in chapters], ["第1章 开始", "第2章 继续"])
        self.assertIn("<h1", chapters[0].html)
        self.assertIn("<p>第一段。</p>", chapters[0].html)
        self.assertIn("<p>第二段。</p>", chapters[0].html)
        self.assertEqual(chapters[0].level, 1)

    def test_volumes_nest_chapters(self):
        text = "第一卷 风起\n\n第1章 开始\n正文\n"
        chapters = self.parse(text)
        self.assertEqual([c.title for c in chapters], ["第一卷 风起", "第1章 开始"])
        self.assertEqual([c.level for c in chapters], [1, 2])

    def test_prose_starting_with_number_is_not_heading(self):
        events = split_events("第三回合，他赢了。\n", r"^第[0-9]+章")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].title, "")

    def test_custom_pattern(self):
        text = "== 第一节 ==\n内容\n"
        chapters = self.parse(text, pattern=r"^== .* ==$")
        self.assertEqual([c.title for c in chapters], ["== 第一节 =="])


class HtmlUtilTest(unittest.TestCase):
    def test_strip_indent(self):
        self.assertEqual(strip_paragraph_indent("<p>　　文字</p>"), "<p>文字</p>")
        self.assertEqual(strip_paragraph_indent("<p> 文字</p>"), "<p>文字</p>")

    def test_plain_text(self):
        self.assertEqual(plain_text("<b>标题</b>&amp;"), "标题&")

    def test_paragraphs(self):
        html = paragraphs("第一段。\n\n第二段。")
        self.assertEqual(html, "<p>第一段。</p>\n<p>第二段。</p>")
        self.assertEqual(paragraphs("   "), "")
        self.assertIn("&lt;", paragraphs("<b>"))


if __name__ == "__main__":
    unittest.main()
