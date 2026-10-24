---
name: cnbc-quotes
description: Fetch CNBC market quotes and cross-market snapshots for stocks, indices, Treasury yields, FX, commodity futures, and crypto, with regular and pre/after-hours values kept separate. Use for latest quoted prices, index levels, yields, exchange rates, or a market overview; not for news.
---

# CNBC Quotes

Use `scripts/cnbc_quotes.py` for instrument quotes and financial market snapshots, not news scraping. Use only the bundled client for retrieval; do not substitute another transport, client, proxy, or browser after a failure. Relay policy or tunnel blocks rather than bypassing them.

## Dependencies and environment

- Python 3.9+; standard library only. No API key, third-party package, cache, or installation is required.
- Network access to `https://quote.cnbc.com` is required for `quote` and `snapshot`. `presets` is offline.
- `CNBC_QUOTES_TZ` sets the display time zone; `--tz` overrides it. Default: `Asia/Shanghai`. If the time-zone database is unavailable, that default falls back to fixed UTC+08:00; `UTC` also works without a database. Other zones must be available IANA names.
- Documentation, comments, and CLI messages are English. Preserve English API instrument/contract names, symbols, and enum values. The agent chooses the conversation language independently.

## Workflow

1. Choose `snapshot` for a cross-market overview (default `global`), or `quote SYMBOL [SYMBOL ...]` for exact CNBC identifiers. CNBC formats differ from other vendors (for example `700-HK`, `600519-CN`, and `BRK.B`, not `0700.HK`, `600519.SS`, or `BRK-B`); check the reference before guessing an unfamiliar market's format. Run `presets` to inspect the fixed ordered CLI defaults; they are not CNBC categories.
2. Inspect each requested symbol's status and raw provider code. Missing symbols, nonzero codes, invalid prices, and malformed data are explicit errors; report partial successes rather than silently dropping errors or substituting aliases. Symbols are case-sensitive and never normalized.
3. Report the quote timestamp separately from fetch time. Check age, `stale`, `future`, and unknown times. `--max-age-minutes` defaults to 60 and measures timestamp age only; it does not validate market hours, holidays, or whether a market is currently open. Historical/stale quotes alone do not make the command fail. Many quotes carry only a date (observed for indices and U.S. stocks outside trading hours); report them as dated, not fresh or stale. Futures can show `future=true`; that is a provider timestamp quirk, not a CLI failure.
4. Keep the top-level `regular` quote separate from `extended`. Each has its own price, changes, timestamp, and session information. `curmktstatus` does not establish the top-level trade session; do not call its price the current after-hours price. Never splice extended fields into the regular quote.
5. Preserve currency, `type`, `subType`, provider, source, `realTime`, and `curmktstatus`. A `realTime` flag is not a freshness guarantee, and `REG_MKT` is not proof of an open market. For a percentage-valued Treasury yield, distinguish `change_bp` (raw change in percentage points times 100) from relative `change_pct`.
6. Return usable results with their limitations and any per-symbol errors. For policy/tunnel blocks (exit 3), report the diagnostic and stop. Read [references/quotes.md](references/quotes.md) only for detailed symbol mappings, output fields, source caveats, session interpretation, or troubleshooting/modifying the client.

## Common Commands

Paths below are relative to this skill directory. Quote shell-sensitive symbols.

```sh
python3 scripts/cnbc_quotes.py snapshot
python3 scripts/cnbc_quotes.py snapshot --preset asia --json
python3 scripts/cnbc_quotes.py snapshot --preset rates --tz UTC
python3 scripts/cnbc_quotes.py quote '.SPX' US10Y '.DXY' 'CNY='
python3 scripts/cnbc_quotes.py quote '@CL.1,@LCO.1,@GC.1' 'BTC.CM=' --json
python3 scripts/cnbc_quotes.py quote AAPL --timeout 20 --max-age-minutes 120
python3 scripts/cnbc_quotes.py presets
```

`quote` accepts space-separated arguments and comma-separated chunks. Exact duplicates are removed in first-seen order, preserving case. Empty chunks, whitespace, control characters, and pipes are rejected, not trimmed or repaired. A maximum of 50 unique symbols is a client safety guard, not a provider limit. `--timeout` (seconds, default 20) and `--max-age-minutes` must be positive finite numbers.

## Output, exit codes, and verification

Results use stdout; progress/retry diagnostics use stderr. Default text is compact English quote data with provenance and time/freshness caveats. `--json` returns structured results, including request and per-symbol errors; every returned quote retains raw provider fields under `raw`. Argument errors use argparse diagnostics on stderr.

| Exit | Meaning |
| --- | --- |
| 0 | Every requested quote is usable; stale, future, and unknown timestamps remain flagged. |
| 1 | Request/API/schema failure or at least one missing/invalid quote. Other successes are preserved. |
| 2 | Invalid arguments; validation runs before network access. |
| 3 | Network block: a tunnel/policy failure, or an HTTP 403/451/policy refusal that may come from runtime policy or the provider/CDN. No bypass or alternate retrieval. |

Verify that each exact requested symbol appears once, inspect errors, and keep quote time and fetch time visible in the answer. Offline regression tests run from the repository root with `python3 -B -m unittest discover -s tests -p 'test_cnbc_quotes.py'`.

## Limitations

The fixed endpoint is an observed CNBC website quote service, not a guaranteed supported public API. Availability, permissions, fields, delay, and identifier coverage can change. Transient network errors, HTTP 429/5xx, and invalid JSON get at most two retries with bounded backoff; permanent errors are not retried. The client does not infer exchange close times, holiday calendars, currency conversions, contract rolls, or whether a quote is tradable. Date-only times stay date-only; naive/ambiguous/unparseable times stay raw/unknown rather than being assigned an exchange time zone.
