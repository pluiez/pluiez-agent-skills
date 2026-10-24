# CNBC Quote Service Reference

Read on demand for symbol choices, provider fields, source limitations, or client maintenance. This is a quote/snapshot client, not a CNBC news scraper. Examples are relative to the skill directory.

## Source and request

The client uses this fixed, observed CNBC website quote service:

```text
https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol
```

It sends URL-encoded query parameters `symbols` (exact identifiers joined with `|`), `requestMethod=itv`, `noform=1`, `partnerId=2`, `fund=1`, `exthrs=1`, `output=json`, and `events=1`. One batch is sent per invocation, apart from at most two transient retries. Fifty unique symbols is a client guard, not a measured CNBC limit. There is no authentication/key configuration, alternate endpoint, alternate transport, browser fallback, or proxy-bypass feature. Normal runtime network configuration still applies.

The response is expected to contain `FormattedQuoteResult.FormattedQuote` as a list. This is not a guaranteed supported public API or a promise of service, licensed redistribution, real-time accuracy, completeness, or tradability. Access and schema may change. An HTTP/tunnel/policy failure must be reported, not evaded. HTTP 403/451 and explicit tunnel/policy diagnostics are conservatively reported as `network_blocked`. An HTTP refusal can come from a runtime policy proxy or from CNBC's own CDN (for example an "Access Denied" page), and the client cannot tell them apart, so HTTP-derived blocks say that either source is possible. Tunnel and OS-level policy diagnostics come from the runtime network path. Neither case permits a bypass. Other permanent HTTP failures and TLS errors (including wrapped certificate-validation failures) are not retried. Truncated HTTP error bodies retain the original status classification: a 503 remains retryable, while 403/451 remain blocked. HTTP 429/5xx, transient OS/URL/timeouts, and invalid JSON retry after one and two seconds, then fail.

## Fixed CLI presets and identifiers

These ordered groups are CLI defaults, not CNBC-defined market categories. `presets` prints them without accessing the network.

| Preset | Ordered exact identifiers |
| --- | --- |
| `us` | `.SPX`, `.IXIC`, `.DJI` |
| `rates` | `US10Y`, `.DXY`, `CNY=` |
| `commodities` | `@CL.1`, `@LCO.1`, `@GC.1` |
| `asia` | `.HSI`, `.SSEC`, `.N225`, `.KS11` |
| `crypto` | `BTC.CM=` |
| `global` | Ordered union: `us`, `rates`, `commodities`, `asia`, `crypto` |

Common meanings: `.SPX` S&P 500, `.IXIC` NASDAQ Composite, `.DJI` Dow Jones Industrial Average; `US10Y` U.S. 10 Year Treasury yield; `.DXY` U.S. Dollar Index; `CNY=` US Dollar/Chinese Renminbi FX spot; `@CL.1` WTI crude futures, `@LCO.1` Brent crude futures, `@GC.1` Gold COMEX futures; `.HSI` Hang Seng, `.SSEC` Shanghai Composite, `.N225` Nikkei 225, `.KS11` KOSPI; `BTC.CM=` Bitcoin/USD. These descriptions do not replace returned English API names.

Do not convert identifiers to another data vendor's conventions or silently use `altSymbol`/`feedSymbol`. Match returned `symbol` to the exact requested string, not the response position or an alias. Preserve case and punctuation. `.KS11` was observed as a usable KOSPI quote; `005930-KR` and `000660-KR` returned provider code 3 without a price and must not be advertised as working identifiers. A symbol's current usability must be checked from its result.

Single-stock formats observed on 2026-10-24. Coverage can change, so confirm each result's `code`:

| Market | Returned code 0 | Returned a nonzero code |
| --- | --- | --- |
| U.S. stocks, ADRs, and ETFs | Plain tickers: `AAPL`, `NVDA`, `BABA`, `TCEHY`, `SPY`; share classes as described below | |
| Hong Kong | `700-HK`, `1810-HK`, `9988-HK` (no leading zeros) | `0700-HK`, `00700-HK` (code 1) |
| China A-shares, Shanghai and Shenzhen | `600519-CN`, `601318-CN`, `300750-CN`, `000858-CN` | `600519-SS` (code 1) |
| Taiwan | `2330-TW` | |
| London | `VOD-GB`, `VOD-LN` | |
| Germany | `SAP-DE` | |
| Japan, Korea | No working single-stock format found | `7203-JP`, `7203-T`, `7203-TK`, `6758-JP`, `005930-KS` (code 1); `005930-KR`, `000660-KR` (code 3) |

Other vendors' formats such as `0700.HK` or `600519.SS` do not carry over. Do not keep guessing suffixes after a nonzero code. Report the error, and say if no format is known for that market.

### U.S. tickers and share classes

Checked on 2026-10-24 against the Nasdaq Trader symbol directories (dated 2026-10-23) and a market-cap ranking from the Nasdaq stock screener. "Top 100" means the 100 largest U.S.-listed companies by market cap, counting each company once and including ADRs but excluding preferred shares and notes. The cutoff was about $162B. Confirm each result's `code` and price.

- **Plain exchange tickers** work for common stocks, ADRs (including OTC ADRs such as `TCEHY`), and ETFs. All 102 common-stock symbols of the top 100 returned prices. `PBR` returned code 1 once in a 50-symbol batch, then succeeded in three reruns, so retry an isolated code 1 once before calling a symbol unsupported.
- **Classes that share a root ticker** (mostly NYSE listings) use a dot: `BRK.A`, `BRK.B`, `BF.B`, `LEN.B`, `HEI.A`, `MOG.A`, `PBR.A`. The dash and slash forms that other vendors use (`BRK-B`, `BRK/B`, `BF-B`, `HEI/A`) returned code 1. Concatenated forms (`BRKA`, `BRKB`, `BFB`, `PBRA`) returned the same instrument and price, but use the dot form.
- **Classes with their own ticker** (common on Nasdaq) use that ticker unchanged: Alphabet Class A is `GOOGL` and Class C is `GOOG`. Never add a class suffix to a ticker. `GOOG.A` and `GOOG.B` returned code 0 with the name `Alphabet Class C` but no price, and `GOOG.C` returned code 1. A code 0 alone does not prove a symbol is valid; the CLI reports the missing price as `invalid_price`.
- **Unlisted classes have no quote.** Alphabet Class B is not listed. `META`, `PLTR`, `CRWD`, `SPCX`, `SHOP`, `ACN`, and `DELL` are listed lines labeled Class A or Class C, and they are each company's only listed common line. Quote the listed ticker.
- **Preferred lines can look like sibling tickers.** `GOOGM` and `GOOGN` returned `subType=Preferred Stock`. `PBR.A` is Petrobras's ADS for preferred shares, and `PBR` is the ADS for common shares. Check `name` and `subType` before reporting a price as the common stock.
- **Thinly traded classes can lack a price.** `AGM.A`, `BIO.B`, and `WSO.B` returned code 0 with a name but no `last`, and their last times were one to two weeks old. Report the error; it is not a format problem.
- **When-issued lines** such as `MSGK.V` and `MSGR.V` (`MSGKw` and `MSGRw` in CQS) returned code 1. A `.V` suffix can also be a regular voting class (`MKC.V` worked), so do not infer meaning from the suffix letter.

Top-100 companies with more than one listed equity line:

| Company | Listed lines | CNBC symbols |
| --- | --- | --- |
| Alphabet | Class A and Class C common; Series A and Series B preferred depositary shares | `GOOGL`, `GOOG`; preferred `GOOGM`, `GOOGN` |
| Berkshire Hathaway | Class A and Class B common | `BRK.A`, `BRK.B` |
| Petrobras | Common-share ADS and preferred-share ADS | `PBR`, `PBR.A` |

FX `<CCY>=` symbols are not quoted in one direction: `CNY=` and `JPY=` returned `USD/CNY` and `USD/JPY`, while `EUR=`, `GBP=`, and `AUD=` returned `EUR/USD`, `GBP/USD`, and `AUD/USD`. Read the direction from the returned `name`; never infer or invert it from the symbol.

Futures names may identify a specific dated contract, for example `Gold COMEX (Dec'26)` with `type=DERIVATIVE` and `subType=Future`. Keep that name/type and do not relabel the instrument as spot gold or infer a roll schedule. Currency fields may be absent; do not invent a currency or convert prices. Preserve the case of `currencyCode`: London stocks such as `VOD-GB` returned `GBp`, meaning pence sterling, not pounds. `CNY=` is a currency pair quote, not an equity index.

## Structured output

`--json` emits one JSON object with `status`, `source_url`, `requested_symbols`, `timezone`, `fetched_at`, `max_age_minutes`, and an ordered `quotes` list. `fetched_at` is the response-processing time (or failure-completion time on whole-request errors), not the last trade. Overall status is `ok`, `partial`, or `error`. Errors include a machine-readable `type` and English `message`. A malformed list entry yields `schema_errors` without discarding other valid entries.

Each quote includes `requested_symbol`, returned `symbol`, unmodified provider `code`, CLI `status`, and `raw`. Successful provider records also expose `name`, `currencyCode`, `type`, `subType`, `provider`, `source`, `exchange`, `realTime`, and `curmktstatus`, plus independent `regular` and optional `extended` blocks. Unknown extra provider fields remain in `raw`; there is no field allowlist that discards them. Normalized missing metadata is null; inspect `raw` to distinguish missing fields from explicit null. Provider strings such as `realTime="true"` are not rewritten as certified booleans.

`regular` means the top-level quote structure, not a proven regular-session trade. Its `session` is null because `curmktstatus` describes provider market status rather than establishing the top-level trade's session. `extended.session` preserves nested `ExtendedMktQuote.type` (for example `PRE_MKT` or `POST_MKT`). Each block has its own `last`, `change`, `change_pct`, `change_bp`, `unit`, `time`, `status`, and warnings. The nested block also retains its own `raw`. Missing extended changes/time stay unknown; they are never copied from regular fields. Invalid nested structures/prices flag the symbol as an error while retaining any usable regular data.

Finite normalized numeric values are decimal strings, with grouping separators and a trailing percent sign removed. Nonfinite/invalid `last` is an explicit error; invalid optional change fields are null with warnings and remain in `raw`. `change_pct` is a percentage number, not a fraction: `"0.9287"` means 0.9287%. A percent-valued `BOND` last has `unit=yield_percent`; other quotes have `unit=price`. Percentage-valued yields are not bond transaction prices. Any separate `bond_last_price` fields remain raw.

For a yield, raw `change` is in percentage points. The client computes `change_bp = change * 100` with Decimal arithmetic. For example, raw `change="+0.046"` means **+4.6 bp**, while raw `change_pct="+0.9287%"` means **+0.9287% relative**. These are distinct quantities; never replace one with the other. Non-yield instruments have null `change_bp`.

Missing exact symbols, duplicate response symbols, missing/nonzero provider codes, invalid prices, malformed schemas, and whole-request failures are explicit errors. Raw CNBC code 3 is a per-instrument API error (exit 1), **not** the client's network-blocked exit 3. No failure drops another symbol's success.

## Time and freshness

Each session's `time` contains `raw`, `kind`, `converted`, `age_minutes`, `stale`, and `future`.

- Explicit-offset ISO `last_time` values are parsed, including `-0400`, `+0900`, `-04:00`, and `Z`. Converted timestamps include the full date, year, and UTC offset in the selected display zone. The original timestamp always remains visible in raw output.
- A valid date such as `2026-10-23` remains `date_only`, not an invented midnight or exchange close. `converted`, age, and freshness flags are null.
- A timestamp without an explicit offset remains `naive`; ambiguous/unparseable/non-string time is `unknown`. There is no guessing from `last_timedate`, `timeZone`, `EDT`, `JST`, country, symbol, or exchange.
- Age compares quote time to fetch time, independently for each session. For nonfuture timestamps, `stale` means age exceeds the configured threshold. Stale data can still be usable historical data and does not alone cause a nonzero exit.
- Future times have negative age and `future=true`, with `stale=null`, never a false promise of freshness. Unknown age/freshness remains null.
- Observed coverage on 2026-10-24, a Saturday outside trading hours: `.SPX`, `.IXIC`, `.DJI`, `.DXY`, `.HSI`, `.SSEC`, `.N225`, `.KS11`, and the regular and extended quotes for AAPL and NVDA returned date-only `last_time`, so they have no age or `stale` flag. `US10Y`, `CNY=`, `BTC.CM=`, and the futures returned explicit-offset timestamps. Trading-hours behavior was not checked. Report a date-only quote as dated, not as fresh or stale.
- Futures timestamps can be later than fetch time. In that check, `@GC.1` returned `2026-10-24T18:43:51.000-0400` and `@CL.1` one second later, about 18 hours after the fetch at 00:18 EDT, and `@LCO.1` was about 41 minutes ahead. The client reports `future=true` with `stale=null`. Treat this as a provider timestamp quirk, not a CLI failure. If timing matters, cite the contract name and, if present, the unconverted `raw.settleDate`.
- This is timestamp-age checking, not market-open validation. No exchange hours, close/holiday calendars, trading-day logic, or clock-quality guarantees are invented. `realTime=true` is not a freshness guarantee; `REG_MKT` is not evidence that the market is open now.

A top-level AAPL quote can remain at its regular-session close while `curmktstatus=POST_MKT` and `ExtendedMktQuote` has a different later price, change, and time. Present them separately; neither a newer extended time nor the provider status silently updates the top-level price.

```sh
python3 scripts/cnbc_quotes.py quote AAPL --json
python3 scripts/cnbc_quotes.py quote US10Y '@GC.1' 'CNY=' --tz Asia/Shanghai
```
