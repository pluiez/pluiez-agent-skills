"""Offline regression tests for CNBC quotes and snapshot semantics."""
import contextlib
from datetime import datetime, timezone
from decimal import Decimal
from email.message import Message
from http.client import BadStatusLine, HTTPResponse, IncompleteRead, LineTooLong, RemoteDisconnected
import importlib.util
import io
import json
import os
from pathlib import Path
import ssl
import unittest
from unittest.mock import call, patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfoNotFoundError

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "skills/cnbc-quotes/scripts/cnbc_quotes.py"
spec = importlib.util.spec_from_file_location("cnbc_quotes", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
cnbc_quotes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cnbc_quotes)

NOW = datetime(2026, 10, 24, 0, 0, tzinfo=timezone.utc)


def quote(symbol="AAPL", **fields):
    """Synthetic, deterministic fixtures; these are not captured live quotes."""
    return {"symbol": symbol, "code": 0, "name": "Apple Inc.", "last": "123.45",
            "change": "-0.50", "change_pct": "-0.40%", "currencyCode": "USD",
            "type": "STOCK", "subType": "Common Stock", "provider": "CNBC Quote Cache",
            "source": "Exchange", "exchange": "NASDAQ", "realTime": "true",
            "curmktstatus": "REG_MKT", "last_time": "2026-10-23T19:30:00.000-0400",
            **fields}


def envelope(*quotes):
    return {"FormattedQuoteResult": {"FormattedQuote": list(quotes)}}


class CliTests(unittest.TestCase):
    def invoke(self, argv, response=None, error=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, {"CNBC_QUOTES_TZ": "Asia/Shanghai"}):
            with patch.object(cnbc_quotes, "utc_now", return_value=NOW):
                with patch.object(cnbc_quotes, "http_json", return_value=response,
                                  side_effect=error) as request:
                    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                        try:
                            code = cnbc_quotes.main(argv)
                        except SystemExit as exc:
                            code = exc.code
        return code, stdout.getvalue(), stderr.getvalue(), request

    def result(self, *items, symbols=None, options=()):
        symbols = symbols or [item["symbol"] for item in items]
        code, output, stderr, request = self.invoke(
            ["quote", *symbols, "--json", *options], envelope(*items))
        return code, json.loads(output), stderr, request

    def test_exact_symbols_encoding_dedupe_and_order(self):
        symbols = [".SPX", "@GC.1", "CNY=", "BTC.CM=", "aapl", "AAPL"]
        code, result, stderr, request = self.result(
            *(quote(s) for s in reversed(symbols)),
            symbols=[".SPX,@GC.1", "CNY=,BTC.CM=", "aapl", "AAPL", ".SPX"])
        self.assertEqual(code, 0)
        self.assertEqual(result["requested_symbols"], symbols)
        self.assertEqual([q["requested_symbol"] for q in result["quotes"]], symbols)
        url = request.call_args.args[0]
        self.assertTrue(url.startswith(cnbc_quotes.QUOTE_URL + "?"))
        self.assertIn("%7C", url)
        self.assertIn("%40GC.1", url)
        self.assertIn("CNY%3D", url)
        self.assertEqual(parse_qs(urlparse(url).query), {
            "symbols": ["|".join(symbols)], "requestMethod": ["itv"], "noform": ["1"],
            "partnerId": ["2"], "fund": ["1"], "exthrs": ["1"],
            "output": ["json"], "events": ["1"]})
        self.assertIn("Fetching", stderr)

    def test_bad_symbols_rejected_before_request(self):
        for symbol in ("", " ", "A A", "A\tA", "A\n", "A|B", ",A", "A,", "A,,B",
                       "A\x00", "A\x7f", "A\x85", " A", "A "):
            with self.subTest(symbol=repr(symbol)):
                code, _, stderr, request = self.invoke(["quote", symbol])
                self.assertEqual(code, 2)
                self.assertIn("symbol", stderr.lower())
                request.assert_not_called()

    def test_maximum_is_unique_client_guard(self):
        symbols = ["S" + str(i) for i in range(50)]
        code, _, _, request = self.result(*(quote(s) for s in symbols), symbols=symbols * 2)
        self.assertEqual(code, 0)
        request.assert_called_once()
        code, _, stderr, request = self.invoke(["quote", *symbols, "S50"])
        self.assertEqual(code, 2)
        self.assertIn("client", stderr)
        request.assert_not_called()

    def test_invalid_options_rejected_before_request(self):
        for option in ("--timeout", "--max-age-minutes"):
            for value in ("0", "-1", "nan", "inf", "-inf", "nonsense"):
                with self.subTest(option=option, value=value):
                    code, _, _, request = self.invoke(["quote", "AAPL", option, value])
                    self.assertEqual(code, 2)
                    request.assert_not_called()
        code, _, _, request = self.invoke(["quote", "AAPL", "--tz", "Not/AZone"])
        self.assertEqual(code, 2)
        request.assert_not_called()

    def test_timeout_passed_to_network(self):
        code, _, _, request = self.result(quote(), options=["--timeout", "3.25"])
        self.assertEqual(code, 0)
        self.assertEqual(request.call_args.kwargs["timeout"], 3.25)

    def test_all_snapshot_presets_and_global_union(self):
        expected = {
            "us": [".SPX", ".IXIC", ".DJI"],
            "rates": ["US10Y", ".DXY", "CNY="],
            "commodities": ["@CL.1", "@LCO.1", "@GC.1"],
            "asia": [".HSI", ".SSEC", ".N225", ".KS11"],
            "crypto": ["BTC.CM="],
        }
        expected["global"] = list(dict.fromkeys(s for v in expected.values() for s in v))
        self.assertEqual(cnbc_quotes.PRESETS, expected)
        for name, symbols in expected.items():
            with self.subTest(preset=name):
                code, output, _, request = self.invoke(
                    ["snapshot", "--preset", name, "--json"],
                    envelope(*(quote(s) for s in reversed(symbols))))
                self.assertEqual(code, 0)
                self.assertEqual(json.loads(output)["requested_symbols"], symbols)
                request.assert_called_once()
        code, output, _, _ = self.invoke(["snapshot", "--json"],
                                        envelope(*(quote(s) for s in expected["global"])))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["requested_symbols"], expected["global"])

    def test_presets_is_offline(self):
        code, output, _, request = self.invoke(["presets"])
        self.assertEqual(code, 0)
        request.assert_not_called()
        for name, symbols in cnbc_quotes.PRESETS.items():
            self.assertIn(name + ": " + ",".join(symbols), output)
        self.assertIn("CLI-defined", output)
        self.assertEqual([line.split(":")[0] for line in output.splitlines()[1:]],
                         ["global", "us", "rates", "commodities", "asia", "crypto"])

    def test_partial_missing_and_api_error_preserve_good_quote(self):
        code, result, _, _ = self.result(quote("AAPL"), {"symbol": "BAD", "code": 3},
                                       symbols=["MISSING", "BAD", "AAPL"])
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "partial")
        missing, bad, good = result["quotes"]
        self.assertEqual(missing["error"]["type"], "missing_quote")
        self.assertIsNone(missing["raw"])
        self.assertEqual(bad["error"]["type"], "api_error")
        self.assertEqual(bad["code"], 3)
        self.assertEqual(bad["raw"], {"symbol": "BAD", "code": 3})
        self.assertEqual(good["status"], "ok")

    def test_alias_and_case_are_not_matches(self):
        for returned in ("aapl", "AAPL.O"):
            with self.subTest(returned=returned):
                code, result, _, _ = self.result(quote(returned, altSymbol="AAPL"), symbols=["AAPL"])
                self.assertEqual(code, 1)
                self.assertEqual(result["quotes"][0]["error"]["type"], "missing_quote")

    def test_duplicate_returned_symbol_is_explicit_error(self):
        code, result, _, _ = self.result(quote(), quote(last="120"), symbols=["AAPL"])
        self.assertEqual(code, 1)
        self.assertEqual(result["quotes"][0]["error"]["type"], "duplicate_quote")

    def test_missing_code_or_invalid_price_is_error(self):
        missing = quote()
        del missing["code"]
        for item in (missing, quote(code=None), quote(code=True), quote(code="1"),
                     quote(last=None), quote(last="N/A"), quote(last="NaN"),
                     quote(last="Infinity"), quote(last="-inf"), quote(last=True),
                     quote(last={}), quote(last="12,34.56")):
            with self.subTest(item=item):
                code, result, _, _ = self.result(item)
                self.assertEqual(code, 1)
                self.assertEqual(result["quotes"][0]["status"], "error")
                self.assertEqual(result["quotes"][0]["raw"], item)

    def test_nonfinite_optional_numbers_are_unknown_not_guessed(self):
        code, result, _, _ = self.result(quote(change="NaN", change_pct="Infinity%"))
        self.assertEqual(code, 0)
        regular = result["quotes"][0]["regular"]
        self.assertIsNone(regular["change"])
        self.assertIsNone(regular["change_pct"])
        self.assertTrue(regular["warnings"])
        for value in (float("nan"), float("inf"), Decimal("NaN"), True, [], {}):
            self.assertIsNone(cnbc_quotes.parse_number(value))

    def test_bond_basis_points_distinct_from_relative_percentage(self):
        item = quote("US10Y", name="U.S. 10 Year Treasury", last="4.999%", change="+0.046",
                     change_pct="+0.9287%", type="BOND", subType="Government Bond")
        del item["currencyCode"]
        code, result, _, _ = self.result(item)
        self.assertEqual(code, 0)
        q = result["quotes"][0]
        self.assertEqual(q["regular"]["unit"], "yield_percent")
        self.assertEqual(Decimal(q["regular"]["change_bp"]), Decimal("4.6"))
        self.assertEqual(q["regular"]["change_pct"], "0.9287")
        self.assertIsNone(q["currencyCode"])
        self.assertEqual(q["raw"], item)
        code, text, _, _ = self.invoke(["quote", "US10Y"], envelope(item))
        self.assertEqual(code, 0)
        self.assertIn("change_bp=4.6", text)
        self.assertIn("change_pct=0.9287%", text)

    def test_futures_names_types_and_currencies_are_preserved(self):
        items = [quote("@GC.1", name="Gold COMEX (Dec'26)", type="DERIVATIVE", subType="Future",
                       last="4,123.45", realTime="false"),
                 quote("CNY=", name="US Dollar/Chinese Renminbi FX Spot Rate", type="CURRENCY",
                       subType="Currency", currencyCode="CNY", last="7.1234")]
        code, result, _, _ = self.result(*items)
        self.assertEqual(code, 0)
        for raw, normalized in zip(items, result["quotes"]):
            self.assertEqual(normalized["raw"], raw)
            self.assertEqual(normalized["name"], raw["name"])
            self.assertEqual(normalized["subType"], raw["subType"])
        self.assertIsNone(result["quotes"][0]["regular"]["change_bp"])

    def test_text_is_compact_and_exposes_provenance_and_time_caveats(self):
        code, text, stderr, _ = self.invoke(["quote", "AAPL"], envelope(quote()))
        self.assertEqual(code, 0)
        for field in ("AAPL", "Apple Inc.", "currency=USD", "type=STOCK", "subType=Common Stock",
                      "provider=CNBC Quote Cache", "quote_time=2026-10-24T07:30:00+08:00",
                      "quote_time_raw=2026-10-23T19:30:00.000-0400", "age_minutes=30",
                      "stale=false", "future=false", "realTime=true", "curmktstatus=REG_MKT",
                      "fetched_at=2026-10-24T08:00:00+08:00", "regular"):
            self.assertIn(field, text)
        self.assertIn("not a freshness guarantee", text)
        self.assertIn("not verified open", text)
        self.assertNotIn("Fetching", text)
        self.assertIn("Fetching", stderr)

    def test_json_preserves_raw_fields_without_progress(self):
        item = quote(extra_field={"unknown": [1, "x"]}, realTime=False)
        code, result, stderr, _ = self.result(item)
        self.assertEqual(code, 0)
        self.assertEqual(result["quotes"][0]["raw"], item)
        self.assertIs(result["quotes"][0]["realTime"], False)
        self.assertEqual(result["fetched_at"], "2026-10-24T08:00:00+08:00")
        self.assertIn("Fetching", stderr)

    def test_explicit_offset_timestamp_variants(self):
        cases = [
            ("2026-10-23T19:30:00.000-0400", "2026-10-24T07:30:00+08:00"),
            ("2026-10-24T08:30:00+0900", "2026-10-24T07:30:00+08:00"),
            ("2026-10-23T23:30:00Z", "2026-10-24T07:30:00+08:00"),
            ("2026-10-23T19:30:00-04:00", "2026-10-24T07:30:00+08:00"),
        ]
        for raw, converted in cases:
            with self.subTest(raw=raw):
                code, result, _, _ = self.result(quote(last_time=raw))
                self.assertEqual(code, 0)
                t = result["quotes"][0]["regular"]["time"]
                self.assertEqual(t["raw"], raw)
                self.assertEqual(t["kind"], "timestamp")
                self.assertEqual(t["converted"], converted)
                self.assertEqual(t["age_minutes"], 30)
                self.assertIs(t["stale"], False)

    def test_timestamps_are_rewritten_for_pre_311_fromisoformat(self):
        # Python 3.9/3.10 accept only +HH:MM offsets and 3- or 6-digit fractions.
        for raw, expected in (("2026-10-23T19:30:00.000-0400", "2026-10-23T19:30:00.000000-04:00"),
                              ("2026-10-23T23:30:00Z", "2026-10-23T23:30:00+00:00"),
                              ("2026-10-24T08:30:00.5+0900", "2026-10-24T08:30:00.500000+09:00"),
                              ("2026-10-23T19:30:00.1234567-04:00", "2026-10-23T19:30:00.123456-04:00"),
                              ("2026-10-23T19:30-0400", "2026-10-23T19:30-04:00"),
                              ("2026-10-23T19:30:00", "2026-10-23T19:30:00")):
            with self.subTest(raw=raw):
                self.assertEqual(cnbc_quotes.iso_text(raw), expected)
        t = cnbc_quotes.quote_time("2026-10-24T08:30:00.5+0900", NOW, timezone.utc, 60)
        self.assertEqual(t["kind"], "timestamp")
        self.assertEqual(t["converted"], "2026-10-23T23:30:00.500000+00:00")

    def test_date_only_naive_unknown_never_infer_zone_or_age(self):
        for raw, kind in (("2026-10-23", "date_only"), ("2026-10-23T19:30:00", "naive"),
                          ("4:00 PM EDT", "unknown"), ("2026-02-30", "unknown"),
                          (None, "unknown"), ({"bad": "time"}, "unknown")):
            with self.subTest(raw=raw):
                code, result, _, _ = self.result(quote(last_time=raw, timeZone="EDT",
                                                      last_timedate="4:00 PM EDT"))
                self.assertEqual(code, 0)
                t = result["quotes"][0]["regular"]["time"]
                self.assertEqual(t["raw"], raw)
                self.assertEqual(t["kind"], kind)
                self.assertIsNone(t["converted"])
                self.assertIsNone(t["age_minutes"])
                self.assertIsNone(t["stale"])
                self.assertIsNone(t["future"])

    def test_future_time_flag_is_not_fresh(self):
        code, result, _, _ = self.result(quote(last_time="2026-10-24T01:00:00Z"))
        self.assertEqual(code, 0)
        t = result["quotes"][0]["regular"]["time"]
        self.assertIs(t["future"], True)
        self.assertIsNone(t["stale"])
        self.assertLess(t["age_minutes"], 0)
        self.assertEqual(t["raw"], "2026-10-24T01:00:00Z")

    def test_age_is_independent_of_real_time_and_market_status(self):
        for real_time, status in (("true", "REG_MKT"), ("false", "POST_MKT")):
            code, result, _, _ = self.result(quote(last_time="2026-10-20T00:00:00Z",
                                                  realTime=real_time, curmktstatus=status))
            self.assertEqual(code, 0)
            self.assertIs(result["quotes"][0]["regular"]["time"]["stale"], True)
        code, result, _, _ = self.result(quote(realTime="false", curmktstatus="CLOSED"))
        self.assertEqual(code, 0)
        self.assertIs(result["quotes"][0]["regular"]["time"]["stale"], False)
        code, result, _, _ = self.result(quote(), options=["--max-age-minutes", "10"])
        self.assertEqual(code, 0)
        self.assertIs(result["quotes"][0]["regular"]["time"]["stale"], True)

    def test_extended_quote_does_not_replace_or_splice_regular(self):
        ext = {"type": "POST_MKT", "last": "124.50", "change": "+1.05", "change_pct": "+0.85%",
               "last_time": "2026-10-23T19:59:00-0400", "source": "Extended feed"}
        item = quote(last="123.45", last_time="2026-10-23T16:00:00-0400",
                     curmktstatus="POST_MKT", ExtendedMktQuote=ext)
        code, result, _, _ = self.result(item)
        self.assertEqual(code, 0)
        q = result["quotes"][0]
        self.assertEqual(q["regular"]["last"], "123.45")
        self.assertEqual(q["regular"]["change"], "-0.5")
        self.assertIsNone(q["regular"]["session"])
        self.assertIs(q["regular"]["time"]["stale"], True)
        self.assertEqual(q["extended"]["last"], "124.5")
        self.assertEqual(q["extended"]["session"], "POST_MKT")
        self.assertEqual(q["extended"]["change"], "1.05")
        self.assertIs(q["extended"]["time"]["stale"], False)
        self.assertEqual(q["extended"]["raw"], ext)
        code, text, _, _ = self.invoke(["quote", "AAPL"], envelope(item))
        self.assertEqual(code, 0)
        self.assertIn("regular last=123.45", text)
        self.assertIn("extended last=124.5", text)
        self.assertIn("session=POST_MKT", text)

    def test_extended_missing_fields_are_not_filled_from_regular(self):
        code, result, _, _ = self.result(quote(ExtendedMktQuote={"last": "124", "type": "PRE_MKT"}))
        self.assertEqual(code, 0)
        ext = result["quotes"][0]["extended"]
        self.assertIsNone(ext["change"])
        self.assertIsNone(ext["change_pct"])
        self.assertIsNone(ext["time"]["raw"])
        self.assertIsNone(ext["time"]["age_minutes"])
        for value in ([], "bad", {"last": "NaN", "type": "POST_MKT"}):
            code, result, _, _ = self.result(quote(ExtendedMktQuote=value))
            self.assertEqual(code, 1)
            self.assertEqual(result["quotes"][0]["regular"]["last"], "123.45")
            self.assertEqual(result["quotes"][0]["extended"]["status"], "error")

    def test_malformed_schema_never_crashes(self):
        for response in (None, [], "bad", {}, {"FormattedQuoteResult": None},
                         {"FormattedQuoteResult": []}, {"FormattedQuoteResult": {"FormattedQuote": {}}},
                         {"FormattedQuoteResult": {"FormattedQuote": None}}):
            with self.subTest(response=response):
                code, output, _, _ = self.invoke(["quote", "AAPL", "--json"], response)
                self.assertEqual(code, 1)
                result = json.loads(output)
                self.assertEqual(result["error"]["type"], "schema_error")
                self.assertEqual(result["quotes"][0]["status"], "error")

    def test_malformed_entries_preserve_valid_requested_quotes(self):
        code, output, _, _ = self.invoke(["quote", "AAPL", "--json"],
                                        envelope(None, [], {"symbol": []}, quote()))
        self.assertEqual(code, 1)
        result = json.loads(output)
        self.assertEqual(result["quotes"][0]["status"], "ok")
        self.assertTrue(result["schema_errors"])

    def test_request_failures_in_json_and_text(self):
        for error, expected, kind in ((cnbc_quotes.ApiError("HTTP 500"), 1, "request_error"),
                                      (cnbc_quotes.NetworkBlocked("Tunnel blocked"), 3, "network_blocked")):
            for json_mode in (True, False):
                with self.subTest(kind=kind, json=json_mode):
                    code, output, _, _ = self.invoke(
                        ["quote", "AAPL", "BAD", *(["--json"] if json_mode else [])], error=error)
                    self.assertEqual(code, expected)
                    if json_mode:
                        result = json.loads(output)
                        self.assertEqual(result["error"]["type"], kind)
                        self.assertEqual(len(result["quotes"]), 2)
                        self.assertTrue(all(q["status"] == "error" for q in result["quotes"]))
                    else:
                        self.assertIn("error=" + kind, output)
                        self.assertIn("AAPL", output)
                        self.assertIn("BAD", output)


class TimezoneTests(unittest.TestCase):
    def test_default_fallback_without_timezone_database(self):
        with patch.object(cnbc_quotes, "ZoneInfo", side_effect=ZoneInfoNotFoundError("no database")):
            zone = cnbc_quotes.get_tz("Asia/Shanghai")
            self.assertEqual(NOW.astimezone(zone).isoformat(), "2026-10-24T08:00:00+08:00")
            self.assertEqual(cnbc_quotes.get_tz("UTC"), timezone.utc)
            with self.assertRaises(ValueError):
                cnbc_quotes.get_tz("America/New_York")

    def test_environment_and_cli_override(self):
        for options, expected in (([], "2026-10-24T00:00:00+00:00"),
                                  (["--tz", "Asia/Shanghai"], "2026-10-24T08:00:00+08:00")):
            stdout = io.StringIO()
            with patch.dict(os.environ, {"CNBC_QUOTES_TZ": "UTC"}):
                with patch.object(cnbc_quotes, "utc_now", return_value=NOW):
                    with patch.object(cnbc_quotes, "http_json", return_value=envelope(quote())):
                        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
                            code = cnbc_quotes.main(["quote", "AAPL", "--json", *options])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(stdout.getvalue())["fetched_at"], expected)


class HttpTests(unittest.TestCase):
    def response(self, body=b'{"ok":true}'):
        return io.BytesIO(body)

    def run_http(self, effects):
        with patch.object(cnbc_quotes.urllib.request, "urlopen", side_effect=effects) as opened:
            with patch.object(cnbc_quotes.time, "sleep") as slept:
                with contextlib.redirect_stderr(io.StringIO()):
                    result = cnbc_quotes.http_json(cnbc_quotes.QUOTE_URL, timeout=2.5)
        return result, opened, slept

    def truncated_response(self):
        with patch("socket.socket") as socket:
            socket.return_value.makefile.return_value = io.BytesIO(
                b'HTTP/1.1 200 OK\r\nContent-Length: 11\r\n\r\n{"ok":')
            response = HTTPResponse(socket())
        response.begin()
        self.addCleanup(response.close)
        return response

    def truncated_http_error(self, status):
        stream = io.BytesIO(
            b"HTTP/1.1 " + str(status).encode("ascii") +
            b" Error\r\nTransfer-Encoding: chunked\r\n\r\n5\r\nretry\r\n8\r\ncut")
        with patch("socket.socket") as socket:
            socket.return_value.makefile.return_value = stream
            response = HTTPResponse(socket())
        response.begin()
        error = HTTPError(cnbc_quotes.QUOTE_URL, status, "Error", response.headers, response)
        self.addCleanup(error.close)
        return error, response, stream

    def invoke_network_cli(self, effects):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(cnbc_quotes.urllib.request, "urlopen", side_effect=effects) as opened:
            with patch.object(cnbc_quotes.time, "sleep") as slept:
                with patch.object(cnbc_quotes, "utc_now", return_value=NOW):
                    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                        code = cnbc_quotes.main(["quote", "AAPL", "--json", "--tz", "UTC"])
        return code, stdout.getvalue(), stderr.getvalue(), opened, slept

    def test_truncated_response_recovers_after_one_retry(self):
        code, output, stderr, opened, slept = self.invoke_network_cli([
            self.truncated_response(), self.response(json.dumps(envelope(quote())).encode("utf-8"))])
        self.assertEqual(code, 0)
        result = json.loads(output)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["quotes"][0]["raw"], quote())
        self.assertEqual(opened.call_count, 2)
        self.assertEqual(slept.call_args_list, [call(1)])
        diagnostic = "Network error: " + str(IncompleteRead(b'{"ok":', 5))
        self.assertEqual(stderr.splitlines(), ["Fetching 1 CNBC quote(s)",
                                              diagnostic + "; retrying in 1s (1/2)"])
        self.assertNotIn("Traceback", output + stderr)

    def test_truncated_response_exhaustion_returns_json_failure(self):
        code, output, stderr, opened, slept = self.invoke_network_cli(
            [self.truncated_response() for _ in range(3)])
        self.assertEqual(code, 1)
        result = json.loads(output)
        diagnostic = "Network error: " + str(IncompleteRead(b'{"ok":', 5))
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], {"type": "request_error", "message": diagnostic})
        self.assertEqual(result["quotes"][0]["error"], result["error"])
        self.assertEqual(result["quotes"][0]["status"], "error")
        self.assertEqual(opened.call_count, 3)
        self.assertEqual(slept.call_args_list, [call(1), call(2)])
        self.assertEqual(stderr.splitlines(), ["Fetching 1 CNBC quote(s)",
                                              diagnostic + "; retrying in 1s (1/2)",
                                              diagnostic + "; retrying in 2s (2/2)"])
        self.assertNotIn("Traceback", output + stderr)

    def test_truncated_http_503_body_exhaustion_returns_json_failure(self):
        errors = [self.truncated_http_error(503) for _ in range(3)]
        code, output, stderr, opened, slept = self.invoke_network_cli(
            [error for error, _, _ in errors])
        self.assertEqual(code, 1)
        result = json.loads(output)
        diagnostic = "HTTP 503: Response body unavailable"
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], {"type": "request_error", "message": diagnostic})
        self.assertEqual(result["quotes"][0]["error"], result["error"])
        self.assertEqual(result["quotes"][0]["status"], "error")
        self.assertEqual(opened.call_count, 3)
        self.assertEqual(slept.call_args_list, [call(1), call(2)])
        self.assertEqual(stderr.splitlines(), ["Fetching 1 CNBC quote(s)",
                                              diagnostic + "; retrying in 1s (1/2)",
                                              diagnostic + "; retrying in 2s (2/2)"])
        self.assertNotIn("Traceback", output + stderr)
        for error, response, stream in errors:
            self.assertTrue(error.closed)
            self.assertTrue(response.isclosed())
            self.assertTrue(stream.closed)

    def test_truncated_http_403_and_451_bodies_remain_blocked_without_retry(self):
        for status in (403, 451):
            with self.subTest(status=status):
                error, response, stream = self.truncated_http_error(status)
                code, output, stderr, opened, slept = self.invoke_network_cli([error])
                self.assertEqual(code, 3)
                result = json.loads(output)
                diagnostic = ("HTTP " + str(status) + ": Response body unavailable; "
                              "this HTTP refusal may come from runtime policy or from the provider/CDN; "
                              "ask the runtime administrator whether quote.cnbc.com is allowed; "
                              "do not bypass the restriction")
                self.assertEqual(result["status"], "error")
                self.assertEqual(result["error"], {"type": "network_blocked", "message": diagnostic})
                self.assertEqual(result["quotes"][0]["error"], result["error"])
                self.assertEqual(result["quotes"][0]["status"], "error")
                opened.assert_called_once()
                slept.assert_not_called()
                self.assertEqual(stderr, "Fetching 1 CNBC quote(s)\n")
                self.assertNotIn("Traceback", output + stderr)
                self.assertTrue(error.closed)
                self.assertTrue(response.isclosed())
                self.assertTrue(stream.closed)

    def test_malformed_http_exhaustion_returns_json_failure(self):
        code, output, stderr, opened, slept = self.invoke_network_cli(
            [BadStatusLine("garbage") for _ in range(3)])
        self.assertEqual(code, 1)
        result = json.loads(output)
        self.assertEqual(result["error"], {"type": "request_error",
                                           "message": "Network error: BadStatusLine: garbage"})
        self.assertEqual(result["quotes"][0]["error"], result["error"])
        self.assertEqual(opened.call_count, 3)
        self.assertEqual(slept.call_args_list, [call(1), call(2)])
        self.assertNotIn("Traceback", output + stderr)

    def test_ssl_errors_direct_or_wrapped_never_retry(self):
        for wrapped in (False, True):
            for ssl_error in (ssl.SSLCertVerificationError(1, "certificate verify failed"),
                              ssl.CertificateError("hostname mismatch: access denied"),
                              ssl.SSLError(1, "certificate verify failed")):
                with self.subTest(wrapped=wrapped, error=ssl_error):
                    error = URLError(ssl_error) if wrapped else ssl_error
                    stderr = io.StringIO()
                    with patch.object(cnbc_quotes.urllib.request, "urlopen", side_effect=error) as opened:
                        with patch.object(cnbc_quotes.time, "sleep") as slept:
                            with contextlib.redirect_stderr(stderr):
                                with self.assertRaises(cnbc_quotes.ApiError) as failed:
                                    cnbc_quotes.http_json(cnbc_quotes.QUOTE_URL)
                    opened.assert_called_once()
                    slept.assert_not_called()
                    self.assertEqual(str(failed.exception), "SSL error: " + str(ssl_error))
                    self.assertEqual(stderr.getvalue(), "")

    def test_ssl_errors_direct_or_wrapped_return_json_failure(self):
        for wrapped in (False, True):
            for ssl_error in (ssl.SSLCertVerificationError(1, "certificate verify failed"),
                              ssl.CertificateError("hostname mismatch: access denied"),
                              ssl.SSLError(1, "certificate verify failed")):
                with self.subTest(wrapped=wrapped, error=ssl_error):
                    error = URLError(ssl_error) if wrapped else ssl_error
                    code, output, stderr, opened, slept = self.invoke_network_cli(error)
                    self.assertEqual(code, 1)
                    result = json.loads(output)
                    self.assertEqual(result["status"], "error")
                    self.assertEqual(result["error"], {"type": "request_error",
                                                     "message": "SSL error: " + str(ssl_error)})
                    self.assertEqual(result["quotes"][0]["error"], result["error"])
                    self.assertEqual(result["quotes"][0]["status"], "error")
                    opened.assert_called_once()
                    slept.assert_not_called()
                    self.assertEqual(stderr, "Fetching 1 CNBC quote(s)\n")
                    self.assertNotIn("Traceback", output + stderr)

    def test_one_request_and_headers(self):
        result, opened, slept = self.run_http([self.response()])
        self.assertEqual(result, {"ok": True})
        opened.assert_called_once()
        req = opened.call_args.args[0]
        self.assertEqual(req.full_url, cnbc_quotes.QUOTE_URL)
        self.assertEqual(req.get_header("Accept"), "application/json")
        self.assertEqual(opened.call_args.kwargs["timeout"], 2.5)
        slept.assert_not_called()

    def test_transient_errors_retry_at_most_twice(self):
        for make_error in (lambda: OSError("reset"), lambda: TimeoutError("timeout"),
                           lambda: URLError("temporary DNS failure"),
                           lambda: BadStatusLine("garbage"), lambda: LineTooLong("header line"),
                           lambda: RemoteDisconnected("closed"),
                           lambda: HTTPError(cnbc_quotes.QUOTE_URL, 429, "limited", Message(), io.BytesIO(b"retry")),
                           lambda: HTTPError(cnbc_quotes.QUOTE_URL, 503, "unavailable", Message(), io.BytesIO(b"retry"))):
            with self.subTest(factory=make_error):
                result, opened, slept = self.run_http([make_error(), make_error(), self.response()])
                self.assertEqual(result, {"ok": True})
                self.assertEqual(opened.call_count, 3)
                self.assertEqual(slept.call_count, 2)
                self.assertTrue(all(0 < item.args[0] <= 3 for item in slept.call_args_list))
                with patch.object(cnbc_quotes.urllib.request, "urlopen",
                                  side_effect=[make_error(), make_error(), make_error()]) as opened:
                    with patch.object(cnbc_quotes.time, "sleep") as slept:
                        with contextlib.redirect_stderr(io.StringIO()):
                            with self.assertRaises(cnbc_quotes.ApiError):
                                cnbc_quotes.http_json(cnbc_quotes.QUOTE_URL)
                    self.assertEqual(opened.call_count, 3)
                    self.assertEqual(slept.call_count, 2)

    def test_malformed_json_unicode_and_nonfinite_json_retry(self):
        for body in (b"not json", b"\xff", b'{"last":NaN}', b'{"last":Infinity}', b'{"last":1e999}'):
            with self.subTest(body=body):
                result, opened, slept = self.run_http([self.response(body), self.response()])
                self.assertEqual(result, {"ok": True})
                self.assertEqual(opened.call_count, 2)
                slept.assert_called_once()

    def test_permanent_http_errors_never_retry(self):
        for status in (400, 401, 404, 422):
            error = HTTPError(cnbc_quotes.QUOTE_URL, status, "bad", Message(), io.BytesIO(b"bad request"))
            with self.subTest(status=status):
                with patch.object(cnbc_quotes.urllib.request, "urlopen", side_effect=error) as opened:
                    with patch.object(cnbc_quotes.time, "sleep") as slept:
                        with self.assertRaises(cnbc_quotes.ApiError):
                            cnbc_quotes.http_json(cnbc_quotes.QUOTE_URL)
                opened.assert_called_once()
                slept.assert_not_called()

    def test_tunnel_and_policy_blocks_never_retry(self):
        errors = [(URLError("Tunnel connection failed: 403 Forbidden"), False),
                  (OSError("blocked by network policy"), False),
                  (HTTPError(cnbc_quotes.QUOTE_URL, 403, "Forbidden", Message(), io.BytesIO(b"denied")), True),
                  (HTTPError(cnbc_quotes.QUOTE_URL, 451, "Policy", Message(), io.BytesIO(b"denied")), True),
                  (HTTPError(cnbc_quotes.QUOTE_URL, 502, "Gateway", Message(),
                             io.BytesIO(b"blocked by policy")), True)]
        for error, http_refusal in errors:
            with self.subTest(error=error):
                with patch.object(cnbc_quotes.urllib.request, "urlopen", side_effect=error) as opened:
                    with patch.object(cnbc_quotes.time, "sleep") as slept:
                        with self.assertRaises(cnbc_quotes.NetworkBlocked) as blocked:
                            cnbc_quotes.http_json(cnbc_quotes.QUOTE_URL)
                opened.assert_called_once()
                slept.assert_not_called()
                # Only an HTTP response can be a provider refusal rather than a runtime block.
                self.assertEqual("provider/CDN" in str(blocked.exception), http_refusal)


if __name__ == "__main__":
    unittest.main()
