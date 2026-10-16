"""Offline regression tests for news content, metadata, and CLI semantics."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "skills/tradingview-news/scripts/tv_news.py"
spec = importlib.util.spec_from_file_location("tv_news", SCRIPT_PATH)
tv_news = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tv_news)


MISSING = object()


def body_ast(*paragraphs):
    return {"type": "root", "children": [
        {"type": "p", "children": [text]} for text in paragraphs
    ]}


class CliTests(unittest.TestCase):
    def invoke(self, argv, response=None, error=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(tv_news, "http_json", return_value=response, side_effect=error) as request:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                try:
                    code = tv_news.main(argv)
                except SystemExit as exc:
                    code = exc.code
        return code, stdout.getvalue(), stderr.getvalue(), request

    def read_story(self, permission=MISSING, ast=None, max_chars=8000, **fields):
        story = {"title": "Test story", "shortDescription": "Summary only",
                 "astDescription": ast, **fields}
        if permission is not MISSING:
            story["permission"] = permission
        code, output, _, _ = self.invoke(
            ["read", "test:0", "--max-chars", str(max_chars)], response=story)
        self.assertEqual(code, 0)
        return output

    def test_returned_body_takes_precedence_over_permission(self):
        ast = body_ast("By Author", "Complete article body")
        for permission, label in ((MISSING, "<missing>"), (None, "null"),
                                  ("headline", "headline"), ("provider", "provider"),
                                  ("preview", "preview"), ("unknown", "unknown")):
            with self.subTest(permission=label):
                output = self.read_story(permission, ast)
                self.assertIn(f"permission={label}\n", output)
                self.assertIn("status=full\nBy Author\n\nComplete article body", output)
                self.assertNotIn("Summary only", output)

    def test_empty_body_falls_back_to_permission(self):
        for ast in (None, body_ast(), body_ast("  ")):
            for permission, status in ((MISSING, "no_body"), (None, "no_body"),
                                       ("headline", "restricted"), ("provider", "restricted"),
                                       ("preview", "preview"), ("unknown", "restricted")):
                with self.subTest(ast=ast, permission=permission):
                    output = self.read_story(permission, ast)
                    self.assertIn(f"status={status}\n", output)
                    self.assertIn("No body text could be extracted", output)
                    self.assertNotIn("status=full", output)
                    self.assertNotIn("subscription", output.lower())
                    self.assertNotIn("flash", output.lower())

    def test_headline_body_obeys_character_limit(self):
        output = self.read_story("headline", body_ast("First paragraph.", "Second paragraph."),
                                 max_chars=20)
        text, notice = output.split("status=full\n", 1)[1].split("[Truncated:", 1)
        self.assertEqual(text.rstrip(), "First paragraph.")
        self.assertLessEqual(len(text.rstrip()), 20)
        self.assertIn("body exceeds 20 characters", notice)
        self.assertNotIn("Second paragraph.", output)

    def test_character_limit_without_newlines_and_at_boundary(self):
        for cap, expected, truncated in ((5, "abcde", True), (10, "abcdefghij", False)):
            with self.subTest(cap=cap):
                output = self.read_story("headline", body_ast("abcdefghij"), max_chars=cap)
                self.assertEqual(output.split("status=full\n", 1)[1].splitlines()[0], expected)
                self.assertEqual("[Truncated:" in output, truncated)

    def test_preview_preserves_summary_without_inferred_ellipsis(self):
        summary = "Original summary. " * 20
        output = self.read_story("preview", shortDescription=summary)
        self.assertTrue(output.endswith(summary.strip() + "\n"))
        self.assertNotIn("\u2026", output)

    def test_news_language_does_not_translate_content_or_change_time_zone(self):
        title, body = "\u539f\u6587\u6807\u9898", "\u65b0\u95fb\u6b63\u6587"
        story = {"title": title, "provider": {"name": "\u6765\u6e90"},
                 "published": 1, "permission": "headline", "astDescription": body_ast(body)}
        with patch.dict(os.environ, {"TV_NEWS_TZ": "Asia/Shanghai"}):
            code, output, _, request = self.invoke(["read", "test:0", "--lang", "zh-Hans"], story)
        self.assertEqual(code, 0)
        self.assertIn(title, output)
        self.assertIn("Provider: \u6765\u6e90", output)
        self.assertIn("08:00 GMT+8", output)
        self.assertIn("status=full\n" + body, output)
        self.assertEqual(parse_qs(urlparse(request.call_args.args[0]).query)["lang"], ["zh-Hans"])

    def test_twitter_node_preserves_source_text_with_english_annotation(self):
        ast = {"type": "twitter", "params": {"username": "author"},
               "children": ["\u539f\u6587"]}
        output = self.read_story("headline", ast)
        self.assertIn("[Twitter @author] \u539f\u6587", output)

    def test_list_preserves_permissions_flags_content_and_cache(self):
        items = []
        for index, permission in enumerate((MISSING, None, "headline", "provider", "future_value")):
            item = {"id": f"story:{index}", "title": f"\u539f\u6587 {index}", "published": index + 1,
                    "provider": {"id": "dow-jones", "name": "Dow Jones Newswires"},
                    "relatedSymbols": [{"symbol": "NYSE:ANET"}], "is_flash": True,
                    "isExclusive": True}
            if permission is not MISSING:
                item["permission"] = permission
            items.append(item)
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "list.json"
            with patch.dict(os.environ, {"TV_NEWS_CACHE": str(cache), "TV_NEWS_TZ": "Asia/Shanghai"}):
                code, output, _, request = self.invoke(["list", "--lang", "ja"], {"items": items})
                cached = json.loads(cache.read_text())["items"]
        self.assertEqual(code, 0)
        self.assertIn("time zone=GMT+8", output)
        self.assertIn("is_flash=true/isExclusive=true", output)
        for label in ("<missing>", "null", "headline", "provider", "future_value"):
            self.assertIn("permission=" + label, output)
        self.assertIn("\u539f\u6587 0", output)
        self.assertNotIn("status=full", output)
        self.assertNotIn("permission", cached[-1])
        self.assertIsNone(cached[-2]["permission"])
        self.assertIn("lang:ja", parse_qs(urlparse(request.call_args.args[0]).query)["filter"])

    def test_full_only_still_filters_permission_without_claiming_body_availability(self):
        items = [{"id": "missing:0", "title": "Missing permission", "published": 1},
                 {"id": "null:0", "title": "Null permission", "published": 2, "permission": None},
                 {"id": "headline:0", "title": "Body may exist", "published": 3,
                  "permission": "headline"}]
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"TV_NEWS_CACHE": str(Path(directory) / "list.json")}):
                code, output, _, _ = self.invoke(["list", "--full-only"], {"items": items})
        self.assertEqual(code, 0)
        self.assertIn("Missing permission", output)
        self.assertIn("Null permission", output)
        self.assertNotIn("Body may exist", output)
        self.assertNotIn("status=full", output)

    def test_filters_use_english_metadata_and_preserve_display_title_case(self):
        meta = {"filters": [{"id": "corp_activity", "constraints": {"values": [
            {"id": "recommendation", "title": "Analysts"},
            {"id": "management", "title": "Management"},
        ]}}]}
        code, output, _, request = self.invoke(["filters"], meta)
        self.assertEqual(code, 0)
        self.assertIn("recommendation (Analysts)", output)
        self.assertIn("management (Management)", output)
        self.assertEqual(parse_qs(urlparse(request.call_args.args[0]).query)["lang"], ["en"])

    def test_filters_reject_news_language_and_time_zone_options(self):
        for option, value in (("--lang", "zh-Hans"), ("--tz", "UTC")):
            with self.subTest(option=option):
                code, _, error, request = self.invoke(["filters", option, value])
                self.assertEqual(code, 2)
                self.assertIn("unrecognized arguments", error)
                request.assert_not_called()

    def test_network_and_api_failures_keep_exit_codes_and_diagnostics(self):
        for error, code, diagnostic in ((tv_news.NetworkBlocked("news.tradingview.com"), 3,
                                        "error=network_blocked"),
                                       (tv_news.ApiError("HTTP 500"), 1, "status=error")):
            with self.subTest(error=error):
                actual, output, _, _ = self.invoke(["read", "test:0"], error=error)
                self.assertEqual(actual, code)
                self.assertIn(diagnostic, output)
                self.assertNotIn("Claude", output)

    def test_invalid_numeric_argument_reports_english_error_before_request(self):
        code, _, error, request = self.invoke(["read", "test:0", "--max-chars", "0"])
        self.assertEqual(code, 2)
        self.assertIn("Must be greater than zero", error)
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
