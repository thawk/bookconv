"""Markdown 子集渲染器的测试。"""

import unittest

from cvbook import markdown_lite


def render(text):
    return markdown_lite.render(text)


class BlockTest(unittest.TestCase):
    def test_heading(self):
        html = render("# 第1章 开始\n")
        self.assertIn('<h1 id="第1章-开始">第1章 开始</h1>', html)

    def test_heading_levels(self):
        html = render("## 小节\n### 更小\n")
        self.assertIn("<h2", html)
        self.assertIn("<h3", html)

    def test_heading_ids_unique(self):
        html = render("## 小节\n## 小节\n")
        self.assertIn('id="小节"', html)
        self.assertIn('id="小节-1"', html)

    def test_paragraphs(self):
        html = render("第一段。\n\n第二段。\n")
        self.assertEqual(html, "<p>第一段。</p>\n<p>第二段。</p>")

    def test_paragraph_keeps_fullwidth_indent(self):
        html = render("　　缩进段落。\n")
        self.assertEqual(html, "<p>　　缩进段落。</p>")

    def test_soft_line_break_joins(self):
        html = render("第一行\n第二行\n")
        self.assertEqual(html, "<p>第一行\n第二行</p>")

    def test_hard_break(self):
        html = render("第一行  \n第二行\n")
        self.assertIn("<br />", html)

    def test_horizontal_rule(self):
        self.assertIn("<hr />", render("---\n"))
        self.assertIn("<hr />", render("* * *\n"))

    def test_blockquote(self):
        html = render("> 引用一\n> 引用二\n")
        self.assertIn("<blockquote>", html)
        self.assertIn("引用一", html)

    def test_fenced_code(self):
        html = render("```python\nprint('#')\n```\n")
        self.assertIn('<pre><code class="language-python">', html)
        self.assertIn("print('#')", html)

    def test_fenced_code_keeps_hash(self):
        html = render("```\n# 不是标题\n```\n")
        self.assertIn("# 不是标题", html)
        self.assertNotIn("<h1", html)

    def test_unordered_list(self):
        html = render("- 一\n- 二\n")
        self.assertEqual(html, "<ul><li>一</li><li>二</li></ul>")

    def test_ordered_list(self):
        html = render("1. 一\n2. 二\n")
        self.assertEqual(html, "<ol><li>一</li><li>二</li></ol>")

    def test_paragraph_ending_at_block(self):
        html = render("段落\n# 标题\n")
        self.assertIn("<p>段落</p>", html)
        self.assertIn("<h1", html)


class InlineTest(unittest.TestCase):
    def test_bold_italic(self):
        self.assertIn("<strong>粗</strong>", render("**粗**"))
        self.assertIn("<em>斜</em>", render("*斜*"))
        self.assertIn("<strong><em>都</em></strong>", render("***都***"))

    def test_code_span(self):
        self.assertIn("<code>a &lt; b</code>", render("`a < b`"))

    def test_image(self):
        self.assertIn('<img src="pic.png" alt="插图"/>', render("![插图](pic.png)"))

    def test_link(self):
        self.assertIn('<a href="https://x.y">点我</a>', render("[点我](https://x.y)"))

    def test_escape_html(self):
        self.assertIn("a &lt; b", render("a < b"))

    def test_entity_kept(self):
        self.assertIn("&amp;", render("A &amp; B") or "")
        self.assertIn("&amp;", render("A & B"))

    def test_backslash_escape(self):
        self.assertIn("*不是斜体*", render(r"\*不是斜体\*"))

    def test_raw_html_passthrough(self):
        self.assertIn("<br>", render("换行<br>了"))

    def test_empty(self):
        self.assertEqual(render(""), "")
        self.assertEqual(render("\n\n"), "")


if __name__ == "__main__":
    unittest.main()
