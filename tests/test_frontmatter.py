"""frontmatter 容错解析的测试。"""

import unittest

from bookconv.frontmatter import (BookMeta, NoFrontMatter, parse_meta,
                                read_frontmatter, split_frontmatter)


def raw(text: str, newline: str = "\n") -> bytes:
    return text.replace("\n", newline).encode("utf-8")


BASIC = """\
---
title: 大明文魁
authors: 幸福来敲门
comments: 一句话简介。
---

# 第1章 开始

正文。
"""

REAL_WORLD = """\
---

title: 大明文魁

authors: 幸福来敲门

comments: |

　　紫禁城前九重门。

　　帽插宫花朝天颜。

---

# 第0001章 少年和媳妇

正文。
"""


class ReadFrontMatterTest(unittest.TestCase):
    def test_basic(self):
        info, body = read_frontmatter(raw(BASIC))
        self.assertEqual(info.title, "大明文魁")
        self.assertEqual(info.authors, ["幸福来敲门"])
        self.assertEqual(info.comments, "一句话简介。")
        self.assertEqual(info.author_text, "幸福来敲门")
        self.assertTrue(info.complete)
        self.assertTrue(body.startswith(b"\n# \xe7\xac\xac1\xe7\xab\xa0"))

    def test_blank_lines_and_unindented_block(self):
        info, body = read_frontmatter(raw(REAL_WORLD))
        self.assertEqual(info.title, "大明文魁")
        self.assertEqual(info.authors, ["幸福来敲门"])
        self.assertEqual(info.comments, "紫禁城前九重门。\n\n帽插宫花朝天颜。")
        self.assertIn("# 第0001章 少年和媳妇".encode("utf-8"), body)
        self.assertNotIn(b"title:", body[:100])

    def test_crlf(self):
        info, body = read_frontmatter(raw(REAL_WORLD, "\r\n"))
        self.assertEqual(info.title, "大明文魁")
        self.assertEqual(info.comments, "紫禁城前九重门。\n\n帽插宫花朝天颜。")
        self.assertTrue(body.startswith(b"\r\n"))

    def test_bom(self):
        info, _ = read_frontmatter(b"\xef\xbb\xbf" + raw(BASIC))
        self.assertEqual(info.title, "大明文魁")

    def test_author_list(self):
        text = """\
---
title: 列表
authors:
  - 作者一
  - 作者二
---
正文
"""
        info, _ = read_frontmatter(raw(text))
        self.assertEqual(info.authors, ["作者一", "作者二"])
        self.assertEqual(info.author_text, "作者一 & 作者二")

    def test_singular_author_and_description(self):
        text = """\
---
title: 单作者
author: 赵六
description: 用 description 当简介。
---
正文
"""
        info, _ = read_frontmatter(raw(text))
        self.assertEqual(info.authors, ["赵六"])
        self.assertEqual(info.comments, "用 description 当简介。")

    def test_closing_dots(self):
        text = """\
---
title: 点点点
authors: 辛
comments: |
  简单简介
...

正文
"""
        info, body = read_frontmatter(raw(text))
        self.assertEqual(info.title, "点点点")
        self.assertEqual(info.comments, "简单简介")
        self.assertIn(b"\xe6\xad\xa3\xe6\x96\x87", body)

    def test_no_frontmatter(self):
        with self.assertRaises(NoFrontMatter):
            read_frontmatter("# 第1章\n\n正文\n".encode("utf-8"))

    def test_horizontal_rule_is_not_frontmatter(self):
        text = "---\n\n正文前。\n\n---\n\n# 第1章\n"
        with self.assertRaises(NoFrontMatter):
            read_frontmatter(text.encode("utf-8"))

    def test_unquoted_title_with_colon(self):
        text = "---\ntitle: 书名: 副标题\nauthors: 甲\n---\n"
        info, _ = read_frontmatter(text.encode("utf-8"))
        self.assertEqual(info.title, "书名: 副标题")

    def test_body_bytes_untouched(self):
        payload = "---\ntitle: 甲\nauthors: 乙\n---\n\n正文。\n".encode("utf-8")
        _, body = split_frontmatter(payload)
        self.assertEqual(body, "\n正文。\n".encode("utf-8"))


class ParseMetaTest(unittest.TestCase):
    def test_block_scalar_folded(self):
        meta = parse_meta("comments: >\n  第一行\n  第二行\n")
        self.assertEqual(meta["comments"], "第一行 第二行")

    def test_flow_list(self):
        meta = parse_meta("authors: [甲, 乙]\n")
        self.assertEqual(meta["authors"], ["甲", "乙"])

    def test_quoted(self):
        meta = parse_meta('title: "带\\"引号\\"的书名"\n')
        self.assertEqual(meta["title"], '带"引号"的书名')


class BookMetaTest(unittest.TestCase):
    def test_empty_is_incomplete(self):
        self.assertFalse(BookMeta().complete)
        self.assertTrue(BookMeta("书", ["人"]).complete)
        # 作者可以没有，书名必须有
        self.assertTrue(BookMeta("书").complete)


if __name__ == "__main__":
    unittest.main()
