#!/usr/bin/env python3
"""CNBC website quotes: compact results, separate sessions, and explicit errors.

Python 3.9+ standard library only. Results use stdout; progress uses stderr.
The observed website endpoint is not a guaranteed supported public API.
"""
import argparse
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, localcontext
import http.client
import json
import math
import os
import re
import ssl
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

QUOTE_URL = "https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol"
DEFAULT_TZ = "Asia/Shanghai"
MAX_SYMBOLS = 50  # A client guard, not a measured provider limit.
RETRIES = 2
# "global" comes first as the default and is the ordered union of the other groups.
PRESETS = {
    "global": [],
    "us": [".SPX", ".IXIC", ".DJI"],
    "rates": ["US10Y", ".DXY", "CNY="],
    "commodities": ["@CL.1", "@LCO.1", "@GC.1"],
    "asia": [".HSI", ".SSEC", ".N225", ".KS11"],
    "crypto": ["BTC.CM="],
}
PRESETS["global"] = list(dict.fromkeys(s for group in PRESETS.values() for s in group))
NUMBER = re.compile(r"[+-]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?\Z")
OFFSET = re.compile(r"(?:Z|[+-]\d{2}:?\d{2})\Z")
COMPACT_OFFSET = re.compile(r"([+-]\d{2})(\d{2})\Z")
FRACTION = re.compile(r"(:\d{2})\.(\d+)")


class ApiError(Exception):
    """A permanent failure or exhausted transient request."""


class NetworkBlocked(Exception):
    """A tunnel or policy error; never attempt to bypass it."""


class _Transient(Exception):
    pass


def log(message):
    print(message, file=sys.stderr)


def utc_now():
    return datetime.now(timezone.utc)


def positive_finite(value):
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        raise argparse.ArgumentTypeError("Must be a positive finite number") from None
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("Must be a positive finite number")
    return number


def get_tz(name):
    if name == "UTC":
        return timezone.utc
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        if name == DEFAULT_TZ:
            return timezone(timedelta(hours=8), "+08:00")
        raise ValueError("Unknown time zone: " + name + " (use an available IANA name)") from None


def validate_symbols(chunks):
    symbols = []
    seen = set()
    for chunk in chunks:
        for symbol in chunk.split(","):
            if (not symbol or "|" in symbol or
                    any(c.isspace() or unicodedata.category(c).startswith("C") for c in symbol)):
                raise ValueError("Invalid symbol: " + repr(symbol) +
                                 "; blanks, whitespace, controls and pipes are not allowed")
            if symbol not in seen:
                symbols.append(symbol)
                seen.add(symbol)
    if not symbols:
        raise ValueError("At least one symbol is required")
    if len(symbols) > MAX_SYMBOLS:
        raise ValueError("At most 50 unique symbols are allowed (client guard, not provider limit)")
    return symbols


def quote_url(symbols):
    return QUOTE_URL + "?" + urllib.parse.urlencode({
        "symbols": "|".join(symbols), "requestMethod": "itv", "noform": "1",
        "partnerId": "2", "fund": "1", "exthrs": "1", "output": "json", "events": "1",
    })


def is_blocked(message):
    message = message.lower()
    return any(word in message for word in (
        "tunnel", "forbidden", "blocked by", "access denied", "policy block", "network policy"))


def reject_constant(value):
    raise ValueError("Nonfinite JSON number: " + value)


def finite_json_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Nonfinite JSON number: " + value)
    return number


def http_json_once(url, timeout):
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0", "Accept": "application/json",
        "Origin": "https://www.cnbc.com", "Referer": "https://www.cnbc.com/",
    })
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"),
                              parse_constant=reject_constant, parse_float=finite_json_float)
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read(512).decode("utf-8", "replace")
        except (OSError, http.client.HTTPException):
            body = "Response body unavailable"
        finally:
            exc.close()
        diagnostic = "HTTP " + str(exc.code) + ": " + body
        if exc.code in (403, 451) or is_blocked(diagnostic):
            # An HTTP refusal may come from a policy proxy or from the provider's own CDN.
            raise NetworkBlocked(diagnostic + "; this HTTP refusal may come from runtime policy "
                                 "or from the provider/CDN") from None
        if exc.code == 429 or 500 <= exc.code <= 599:
            raise _Transient(diagnostic) from None
        raise ApiError(diagnostic) from None
    except urllib.error.URLError as exc:
        # Treat SSL failures as permanent before checking policy-message heuristics.
        if isinstance(exc.reason, ssl.SSLError):
            raise ApiError("SSL error: " + str(exc.reason)) from None
        if is_blocked(str(exc.reason)):
            raise NetworkBlocked(str(exc.reason)) from None
        raise _Transient("Network error: " + str(exc.reason)) from None
    except ssl.SSLError as exc:
        raise ApiError("SSL error: " + str(exc)) from None
    except http.client.IncompleteRead as exc:
        # A truncated HTTP body is a transient stream failure, like a reset.
        raise _Transient("Network error: " + str(exc)) from None
    except http.client.HTTPException as exc:
        # urllib does not wrap malformed status/header lines because they are not OSErrors.
        raise _Transient("Network error: " + type(exc).__name__ + ": " + str(exc)) from None
    except OSError as exc:
        if is_blocked(str(exc)):
            raise NetworkBlocked(str(exc)) from None
        raise _Transient("Network error: " + str(exc)) from None
    except (ValueError, UnicodeError) as exc:
        raise _Transient("Invalid JSON response: " + str(exc)) from None


def http_json(url, timeout=20):
    for attempt in range(RETRIES + 1):
        try:
            return http_json_once(url, timeout)
        except _Transient as exc:
            if attempt == RETRIES:
                raise ApiError(str(exc)) from None
            delay = attempt + 1
            log(str(exc) + "; retrying in " + str(delay) + "s (" +
                str(attempt + 1) + "/" + str(RETRIES) + ")")
            time.sleep(delay)


def parse_number(value):
    """Parse formatted provider numbers to finite Decimal, never binary math."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        return None
    text = str(value).strip()
    if text.endswith("%"):
        text = text[:-1]
    if not NUMBER.fullmatch(text):
        return None
    try:
        number = Decimal(text.replace(",", ""))
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def decimal_text(value):
    if value is None:
        return None
    # Avoid expanding arbitrarily large exponents into enormous strings.
    if value.adjusted() > 30 or value.adjusted() < -20:
        return str(value)
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def iso_text(raw):
    """Rewrite Z, +HHMM and fraction lengths that fromisoformat rejects before Python 3.11."""
    text = raw[:-1] + "+00:00" if raw.endswith("Z") else COMPACT_OFFSET.sub(r"\1:\2", raw)
    # Pad or truncate to microseconds, matching how Python 3.11+ parses longer fractions.
    return FRACTION.sub(lambda m: m.group(1) + "." + (m.group(2) + "00000")[:6], text, count=1)


def quote_time(raw, fetched, zone, max_age_minutes):
    result = {"raw": raw, "kind": "unknown", "converted": None,
              "age_minutes": None, "stale": None, "future": None}
    if not isinstance(raw, str):
        return result
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        try:
            date.fromisoformat(raw)
            result["kind"] = "date_only"
        except ValueError:
            pass
        return result
    # A time without an explicit numeric offset or Z is not localizable safely.
    if not re.match(r"\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}", raw):
        return result
    try:
        parsed = datetime.fromisoformat(iso_text(raw))
        if not OFFSET.search(raw) or parsed.tzinfo is None:
            result["kind"] = "naive"
            return result
        age = (fetched - parsed).total_seconds() / 60
        result.update(kind="timestamp", converted=parsed.astimezone(zone).isoformat(),
                      age_minutes=round(age, 6), future=age < 0,
                      stale=None if age < 0 else age > max_age_minutes)
    except (ValueError, OverflowError):
        pass
    return result


def session_quote(raw, fetched, zone, max_age_minutes, yield_quote=False, extended=False):
    if not isinstance(raw, dict):
        return {"status": "error", "error": {"type": "schema_error",
                "message": "ExtendedMktQuote must be an object"}, "raw": raw}
    last = parse_number(raw.get("last"))
    change = parse_number(raw.get("change"))
    change_pct = parse_number(raw.get("change_pct"))
    bp = None
    if yield_quote and change is not None:
        with localcontext() as ctx:
            ctx.prec = max(28, len(change.as_tuple().digits) + 3)
            bp = change * Decimal(100)
    result = {
        "status": "ok" if last is not None else "error",
        "last": decimal_text(last), "change": decimal_text(change),
        "change_pct": decimal_text(change_pct), "change_bp": decimal_text(bp),
        "unit": "yield_percent" if yield_quote else "price",
        # curmktstatus describes provider market status, not the top-level trade session.
        "session": raw.get("type") if extended else None,
        "time": quote_time(raw.get("last_time"), fetched, zone, max_age_minutes),
        "warnings": [],
    }
    if extended:
        result["raw"] = raw
    if last is None:
        result["error"] = {"type": "invalid_price", "message": "Missing or invalid finite last price"}
    for key, number in (("change", change), ("change_pct", change_pct)):
        if key in raw and raw[key] is not None and number is None:
            result["warnings"].append("Invalid finite " + key + "; retained only in raw")
    return result


def error_quote(symbol, kind, message, raw=None):
    return {"requested_symbol": symbol, "symbol": raw.get("symbol") if isinstance(raw, dict) else None,
            "code": raw.get("code") if isinstance(raw, dict) else None,
            "status": "error", "error": {"type": kind, "message": message}, "raw": raw}


def normalize_quote(symbol, raw, fetched, zone, max_age_minutes):
    code = raw.get("code")
    if not ((type(code) is int and code == 0) or (isinstance(code, str) and code == "0")):
        return error_quote(symbol, "api_error", "Missing or nonzero provider code", raw)
    result = {"requested_symbol": symbol, "symbol": raw["symbol"], "code": code,
              "status": "ok", "raw": raw}
    for key in ("name", "type", "subType", "currencyCode", "provider", "source", "exchange",
                "realTime", "curmktstatus"):
        result[key] = raw.get(key)
    # Only a BOND whose last is explicitly a percentage is treated as a yield.
    yield_quote = (raw.get("type") == "BOND" and isinstance(raw.get("last"), str) and
                   raw["last"].strip().endswith("%"))
    result["regular"] = session_quote(raw, fetched, zone, max_age_minutes, yield_quote)
    result["extended"] = None
    if "ExtendedMktQuote" in raw and raw["ExtendedMktQuote"] is not None:
        result["extended"] = session_quote(raw["ExtendedMktQuote"], fetched, zone,
                                           max_age_minutes, yield_quote, extended=True)
    for block in (result["regular"], result["extended"]):
        if block and block["status"] == "error":
            result["status"] = "error"
            result["error"] = block["error"]
            break
    return result


def normalize_response(payload, symbols, fetched, zone, max_age_minutes):
    if not isinstance(payload, dict) or not isinstance(payload.get("FormattedQuoteResult"), dict):
        raise ApiError("schema_error: Expected FormattedQuoteResult object")
    items = payload["FormattedQuoteResult"].get("FormattedQuote")
    if not isinstance(items, list):
        raise ApiError("schema_error: Expected FormattedQuoteResult.FormattedQuote list")
    by_symbol = {}
    schema_errors = []
    for index, item in enumerate(items):
        if not isinstance(item, dict) or not isinstance(item.get("symbol"), str):
            schema_errors.append("Invalid quote entry at index " + str(index))
            continue
        by_symbol.setdefault(item["symbol"], []).append(item)
    quotes = []
    for symbol in symbols:
        matches = by_symbol.get(symbol, [])
        if not matches:
            quotes.append(error_quote(symbol, "missing_quote", "No exact requested-symbol match returned"))
        elif len(matches) > 1:
            q = error_quote(symbol, "duplicate_quote", "Multiple exact-symbol quotes returned")
            q["raw"] = matches
            quotes.append(q)
        else:
            quotes.append(normalize_quote(symbol, matches[0], fetched, zone, max_age_minutes))
    return quotes, schema_errors


def display(value):
    if value is None:
        return "unknown"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return format(value, ".10g")
    # Keep compact text to one line per session without changing raw JSON fields.
    return str(value).replace("\r", "\\r").replace("\n", "\\n").replace("\t", "\\t")


def print_session(label, block):
    if "last" not in block:
        print("  " + label + " error=" + block["error"]["type"] + " " + block["error"]["message"])
        return
    pct = display(block["change_pct"]) + ("%" if block["change_pct"] is not None else "")
    fields = [label + " last=" + display(block["last"]), "unit=" + block["unit"],
              "change=" + display(block["change"]), "change_pct=" + pct]
    if block["change_bp"] is not None:
        fields.append("change_bp=" + display(block["change_bp"]))
    fields.append("session=" + display(block["session"]))
    t = block["time"]
    fields.extend(["quote_time=" + display(t["converted"]), "quote_time_raw=" + display(t["raw"]),
                   "time_kind=" + t["kind"], "age_minutes=" + display(t["age_minutes"]),
                   "stale=" + display(t["stale"]), "future=" + display(t["future"])])
    if block["status"] == "error":
        fields.append("error=" + block["error"]["type"])
    if block["warnings"]:
        fields.append("warnings=" + "; ".join(block["warnings"]))
    print("  " + " | ".join(fields))


def print_text(result):
    print("# CNBC quotes | fetched_at=" + result["fetched_at"] + " | timezone=" + result["timezone"] +
          " | max_age_minutes=" + display(result["max_age_minutes"]))
    print("# realTime is a provider flag, not a freshness guarantee; curmktstatus is provider status, "
          "not verified open. Age is not market-open validation; top-level trade session is unknown.")
    if "error" in result:
        print("error=" + result["error"]["type"] + " " + display(result["error"]["message"]))
    for message in result.get("schema_errors", []):
        print("error=schema_error " + message)
    for q in result["quotes"]:
        fields = [q["requested_symbol"], "code=" + display(q["code"]), "status=" + q["status"]]
        if "name" in q:
            fields.extend([display(q["name"]), "currency=" + display(q["currencyCode"]),
                           "type=" + display(q["type"]), "subType=" + display(q["subType"]),
                           "provider=" + display(q["provider"]), "source=" + display(q["source"]),
                           "realTime=" + display(q["realTime"]),
                           "curmktstatus=" + display(q["curmktstatus"])])
        if "error" in q:
            fields.append("error=" + q["error"]["type"] + " " + q["error"]["message"])
        print(" | ".join(fields))
        if "regular" in q:
            print_session("regular", q["regular"])
        if q.get("extended") is not None:
            print_session("extended", q["extended"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    quote = commands.add_parser("quote", help="Fetch exact CNBC symbols")
    quote.add_argument("symbols", nargs="+", metavar="SYMBOL")
    snapshot = commands.add_parser("snapshot", help="Fetch a fixed CLI-defined symbol group")
    snapshot.add_argument("--preset", choices=list(PRESETS), default="global")
    commands.add_parser("presets", help="Print fixed CLI-defined presets without network access")
    for command in (quote, snapshot):
        command.add_argument("--json", action="store_true", help="Print structured JSON, including errors")
        command.add_argument("--tz", default=os.environ.get("CNBC_QUOTES_TZ", DEFAULT_TZ),
                             help="Display time zone (default: CNBC_QUOTES_TZ or Asia/Shanghai)")
        command.add_argument("--timeout", type=positive_finite, default=20,
                             help="Per-attempt network timeout in seconds (default: 20)")
        command.add_argument("--max-age-minutes", type=positive_finite, default=60,
                             help="Age threshold, not a market-open check (default: 60)")
    args = parser.parse_args(argv)
    if args.command == "presets":
        print("# CLI-defined presets, not CNBC categories (offline)")
        for name, symbols in PRESETS.items():
            print(name + ": " + ",".join(symbols))
        return 0
    try:
        zone = get_tz(args.tz)
        symbols = validate_symbols(args.symbols if args.command == "quote" else PRESETS[args.preset])
    except ValueError as exc:
        parser.error(str(exc))
    result = {"status": "error", "source_url": QUOTE_URL, "requested_symbols": symbols,
              "timezone": args.tz, "max_age_minutes": args.max_age_minutes, "quotes": []}
    exit_code = 1
    log("Fetching " + str(len(symbols)) + " CNBC quote(s)")
    try:
        payload = http_json(quote_url(symbols), timeout=args.timeout)
        fetched = utc_now()
        result["fetched_at"] = fetched.astimezone(zone).isoformat()
        quotes, schema_errors = normalize_response(payload, symbols, fetched, zone, args.max_age_minutes)
        result["quotes"] = quotes
        if schema_errors:
            result["schema_errors"] = schema_errors
        usable = sum(q["status"] == "ok" for q in quotes)
        if usable == len(symbols) and not schema_errors:
            result["status"] = "ok"
            exit_code = 0
        elif usable:
            result["status"] = "partial"
    except (NetworkBlocked, ApiError) as exc:
        blocked = isinstance(exc, NetworkBlocked)
        kind = "network_blocked" if blocked else "request_error"
        if str(exc).startswith("schema_error:"):
            kind = "schema_error"
        message = str(exc)
        if blocked:
            message += ("; ask the runtime administrator whether quote.cnbc.com is allowed; "
                        "do not bypass the restriction")
        result["fetched_at"] = utc_now().astimezone(zone).isoformat()
        result["error"] = {"type": kind, "message": message}
        result["quotes"] = [error_quote(s, kind, message) for s in symbols]
        exit_code = 3 if blocked else 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":")))
    else:
        print_text(result)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
