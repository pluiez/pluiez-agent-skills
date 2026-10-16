"""Regression tests for content-first story reading (no network required)."""
import contextlib
import io
import unittest
from argparse import Namespace
from unittest.mock import patch

import tv_news


class ReadStoryTests(unittest.TestCase):
    def read_story(self, permission, ast=None, max_chars=8000):
        story = {
            "permission": permission,
            "title": "Test story",
            "shortDescription": "Summary only",
            "astDescription": ast,
        }
        args = Namespace(tz="Asia/Shanghai", refs=["test:0"], max_stories=5,
                         lang="en", max_chars=max_chars)
        output = io.StringIO()
        with patch.object(tv_news, "http_json", return_value=story):
            with contextlib.redirect_stdout(output):
                code = tv_news.cmd_read(args)
        self.assertEqual(code, 0)
        return output.getvalue()

    def test_returned_body_takes_precedence_over_permission(self):
        ast = {"type": "root", "children": [
            {"type": "p", "children": ["By Author"]},
            {"type": "p", "children": ["Complete article body"]},
        ]}
        for permission in (None, "headline", "provider", "preview", "unknown"):
            with self.subTest(permission=permission):
                output = self.read_story(permission, ast)
                self.assertIn("status=full\nBy Author\n\nComplete article body", output)
                self.assertIn("访问级别: 全文", output)
                self.assertNotIn("Summary only", output)

    def test_empty_body_falls_back_to_permission(self):
        for ast in (None, {"type": "root", "children": []},
                    {"type": "root", "children": [{"type": "p", "children": ["  "]}]}):
            for permission, status in ((None, "no_body"), ("headline", "restricted"),
                                       ("provider", "restricted"), ("preview", "preview"),
                                       ("unknown", "restricted")):
                with self.subTest(ast=ast, permission=permission):
                    output = self.read_story(permission, ast)
                    self.assertIn(f"status={status}", output)
                    self.assertNotIn("status=full", output)

    def test_headline_body_obeys_character_limit(self):
        ast = {"type": "root", "children": [
            {"type": "p", "children": ["First paragraph."]},
            {"type": "p", "children": ["Second paragraph."]},
        ]}
        output = self.read_story("headline", ast, max_chars=20)
        self.assertIn("status=full\nFirst paragraph.", output)
        self.assertNotIn("Second paragraph.", output)
        self.assertIn("[已截断：正文超过 20 字符", output)


if __name__ == "__main__":
    unittest.main()
