"""样式解析的测试。"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bookconv import styles


def write(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


class ResolveStyleTest(unittest.TestCase):
    def test_builtin_default(self):
        with tempfile.TemporaryDirectory() as empty, \
                mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": empty}):
            sheet = styles.resolve()
        self.assertIn("Songti SC", sheet.css)
        self.assertEqual(sheet.sources, ["内置默认样式"])

    def test_config_style_replaces_default(self):
        with tempfile.TemporaryDirectory() as config:
            write(Path(config) / "bookconv" / "style.css", ".x { color: red; }")
            with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": config}):
                sheet = styles.resolve()
        self.assertEqual(sheet.css.strip(), ".x { color: red; }")
        self.assertNotIn("Songti SC", sheet.css)

    def test_config_extra_appends(self):
        with tempfile.TemporaryDirectory() as config:
            write(Path(config) / "bookconv" / "extra.css", ".x { color: blue; }")
            with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": config}):
                sheet = styles.resolve()
        self.assertIn("Songti SC", sheet.css)
        self.assertIn("color: blue", sheet.css)

    def test_explicit_style_wins(self):
        with tempfile.TemporaryDirectory() as config, \
                tempfile.TemporaryDirectory() as work:
            write(Path(config) / "bookconv" / "style.css", ".config { }")
            explicit = write(Path(work) / "mine.css", ".mine { }")
            with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": config}):
                sheet = styles.resolve(explicit)
        self.assertIn(".mine", sheet.css)
        self.assertNotIn(".config", sheet.css)

    def test_extra_order(self):
        with tempfile.TemporaryDirectory() as work:
            first = write(Path(work) / "a.css", ".marker-alpha { }")
            second = write(Path(work) / "b.css", ".marker-beta { }")
            with tempfile.TemporaryDirectory() as empty, \
                    mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": empty}):
                sheet = styles.resolve(None, [first, second])
        self.assertLess(sheet.css.index(".marker-alpha"),
                        sheet.css.index(".marker-beta"))

    def test_missing_file(self):
        with self.assertRaises(styles.StyleError):
            styles.resolve("/no/such/style.css")


if __name__ == "__main__":
    unittest.main()
