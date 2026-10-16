---
name: tradingview-news
description: Search and filter TradingView News Flow by market, country, sector, provider, or symbol; list headlines and read selected story bodies on demand.
---

# TradingView News Flow

Use only `scripts/tv_news.py` to retrieve TradingView news. Do not substitute another HTTP client, `tradingview-scraper`, or a browser. Report script errors; do not switch retrieval methods after a failure.

The CLI uses Python 3.9+ and the standard library only. The runtime must be able to reach `*.tradingview.com`. If the script reports `error=network_blocked`, relay its diagnostic rather than bypassing the restriction.

## Language and terminology

- Skill documentation and CLI-generated text use English, independently of the conversation language. The caller chooses how to discuss the results with the user.
- Preserve API field names, ids, enum values, and English display titles. Use the English API metadata as the reference for filter terminology; do not infer category boundaries from translated labels.
- Preserve news text in its source language. `--lang` controls the news request language, not CLI messages, the conversation language, or automatic translation. `filters` always requests English metadata.
- Time zone configuration is independent of language: the default remains `Asia/Shanghai` (GMT+8), overridable with `--tz` or `TV_NEWS_TZ`.

## Workflow

1. Run `list` with the requested filters. With no options, it sends only `lang=en` and prints the returned items. For a request for major wire coverage, the CLI-defined `--preset wires --hours 24` is a useful starting point; its exact query composition is below.
2. Check the `# Query N` coverage notes. A request near the item cap may omit earlier news. The script reports observed coverage, not a guarantee that every matching story exists in the result. Narrow the filters or use `--split` for multiple values when a broader window is needed.
3. Use list results as headlines only. Do not infer article details from titles or treat a `permission` value as proof that a body is available or unavailable.
4. Run `read` only for the specific stories whose bodies are needed. Do not batch-read stories merely to supplement a headline list.
5. Interpret the CLI's `status` separately from the API's `permission`:

   | CLI status | Meaning |
   | --- | --- |
   | `full` | Body text was extracted from `astDescription`. This does not verify completeness. Text exceeding `--max-chars` is truncated and marked. |
   | `preview` | No body text was extracted and `permission=preview`; print `shortDescription` if present. |
   | `restricted` | No body text was extracted and `permission` is `headline`, `provider`, or another non-null value not recognized by the CLI. Unknown values use this conservative fallback. |
   | `no_body` | No body text was extracted and `permission` is missing or null. This does not establish that the source article has no body or is a flash item. |
   | `error` | The request failed; details accompany the status. |

Always attempt to extract the body first. If the response contains extractable body text, print it with `status=full` regardless of `permission`, subject to `--max-chars`. Only use permission-based fallbacks when no body text was extracted. Do not infer a particular subscription requirement from the permission value alone.

## Filters

Different filter fields use AND; multiple values of one field use OR. Values may be space-separated or comma-separated. Quote values containing spaces. For example, `--market stock --country US JP` requests `market=stock` AND `market_country` in `US,JP`.

Each request returns at most 200 items under the observed API behavior; the CLI does not paginate. Broad filters can cover a shorter time span.

| CLI option | API filter id | Common accepted values |
| --- | --- | --- |
| `--market` | `market` | `stock` (Stocks), `etf` (ETFs), `crypto`, `forex`, `index` (Indices), `futures`, `bond` (Government bonds), `corp_bond` (Corporate bonds), `economic` (Economy) |
| `--country` | `market_country` | ISO 3166-1 alpha-2 codes: `US`, `CN`, `JP`, `KR`, `HK`, `TW`, `GB`, `DE`, `IN` |
| `--sector` | `sector` | `"Electronic Technology"`, `"Technology Services"`, `Finance`, `"Health Technology"`, `"Energy Minerals"`, `"Retail Trade"` |
| `--corp` | `corp_activity` | `earnings`, `earnings_calls`, `ipo`, `dividends`, `share_buybacks`, `mergers_and_acquisitions`, `strategy_business_products` (Strategy, business, and products), `management`, `insider_trading`, `ownership_changes`, `esg` (ESG and regulation), `recommendation` (Analysts), `credit_ratings` |
| `--econ` | `economic_category` | `gdp`, `labor`, `prices`, `money`, `trade`, `government`, `business`, `consumer`, `housing`, `taxes`, `health` |
| `--crypto` | `crypto_sections` | `market` (Market moves), `etfs` (Crypto ETFs), `pegs_reserves_and_liquidity` (Pegs, reserves, and liquidity), `regulation`, `adoption`, `technology`, `security`, `fundraising`, `tokenomics`, `exchanges`, `people` |
| `--priority` | `priority` | `flash`, `important`, `top_stories` (Top stories), `key_facts` (Key facts) |
| `--symbol` | `symbol` | `EXCHANGE:TICKER`, e.g. `NASDAQ:NVDA`, `NYSE:TSM`, `HKEX:700` |
| `--provider` | `provider` | `reuters`, `dow-jones`, `market-watch`, `trading-economics`, `tradingview`, `benzinga`, `seekingalpha`, `cointelegraph` |
| `--lang` | `lang` | One news language; default `en`. Examples: `zh-Hans`, `zh-Hant`, `ja`, `ko`. |

`tradingview_analyst_updates` occurs as a provider in news results but is not in the accepted provider filter values in the recorded metadata. Use `--exclude-provider tradingview_analyst_updates` to exclude it locally.

Read [references/filters.md](references/filters.md) when a sector, provider, or language value is absent from these tables. The tables are snapshots; run `filters` for current ids and English display titles.

## CLI presets

These names belong to this CLI, not the TradingView API. Results from the listed query groups are merged by story id. `--preset` cannot be combined with the filter options above except `--lang`; to customize a preset, supply explicit filters instead.

| Preset | Query definition |
| --- | --- |
| `wires` | `priority=top_stories` OR (`priority=important` AND `provider` in `reuters,dow-jones`) |
| `top` | `priority=top_stories` |
| `important` | `priority=important` |
| `us-important` | `market=stock` AND `market_country=US` AND `priority=important` |
| `us-stocks` | `market=stock` AND `market_country=US` |
| `macro` | `market=economic` |
| `crypto` | `market=crypto` |

`wires` includes `top_stories` from any provider. Neither `important` nor `top_stories` establishes how the content was selected or produced. Use `--hours` for time-bounded requests; sparse categories may return much older news.

## Other options

`--split` changes how requests are sent. The other `list` options below filter or limit returned items locally.

| `list` option | Behavior | Default |
| --- | --- | --- |
| `--split` | One request per filter-value combination, each with its own cap; merge by id. Maximum 30 requests. | Off; multiple values share a request cap |
| `--hours N` | Keep items published within the last N hours. | No time filter |
| `--keyword RE ...` | Keep titles matching any supplied regular expression, case-insensitively. | Off |
| `--exclude-provider P ...` | Exclude providers by id or display name, case-insensitively. | Off |
| `--full-only` | Keep items with missing or null `permission`. This legacy option name does not guarantee body availability and may exclude items with extractable bodies. | Off |
| `--flash-only` | Keep items with a truthy `is_flash` field. | Off |
| `--dedupe-titles` | Merge titles with the same lowercase ASCII alphanumeric normalization; keep the newest. | Off |
| `--limit N` | Limit displayed results. | All |

| `read` option | Behavior | Default |
| --- | --- | --- |
| Positional references | One or more `#N` references (`#` optional) or story ids. | Required |
| `--max-chars N` | Body character cap. Overlong bodies are cut at the last newline within the cap when one exists, and a truncation notice is appended. Metadata and notices are outside the cap. | 8000 |
| `--max-stories N` | Maximum stories per invocation; exceeding it is an error. | 5 |
| `--lang` | News request language. | `en` |

`#N` refers only to the latest `list` results. Another list run replaces their numbering. The shared cache defaults to a file in the system temporary directory; override it with `TV_NEWS_CACHE` when separate sessions need separate lists. References to a cache older than one hour produce a warning.

`--tz` and `--lang` are available on `list` and `read`. `filters` takes neither option: it always retrieves English metadata and does not display news timestamps.

## Common Commands

Paths below are relative to this skill directory.

```bash
python3 scripts/tv_news.py list
python3 scripts/tv_news.py list --preset wires --hours 24
python3 scripts/tv_news.py list --market stock --country US --hours 6 \
  --exclude-provider tradingview_analyst_updates
python3 scripts/tv_news.py list --symbol NASDAQ:NVDA NASDAQ:AMD --hours 72 --keyword "China|export"
python3 scripts/tv_news.py list --market stock --country CN JP KR --hours 12 --split
python3 scripts/tv_news.py read '#3' '#7'
python3 scripts/tv_news.py read 'DJN_DN20261016004257:0' --max-chars 8000
python3 scripts/tv_news.py filters
```

## Output and exit codes

Results go to stdout; progress and diagnostics go to stderr, except per-story errors and `error=network_blocked`, which are included in stdout. CLI-generated text is English. News titles, body text, and returned provider names retain their source language.

`list` starts with `# ` coverage and summary lines, followed by one line per story:

```text
#3 10-16 21:00 | Dow Jones Newswires | Example headline | ANET | permission=headline
```

`permission` preserves the API value: for example, `permission=headline`, `permission=preview`, or `permission=provider`. `permission=null` means an explicit JSON null; `permission=<missing>` means the field was absent. Neither is relabeled as full access. Flags use their API field names: `is_flash=true` and `isExclusive=true`.

`read` prints a title, metadata including the raw permission, a source link when available, a `status=...` line, and body text or a diagnostic. For example, `permission=headline` in the metadata and `status=full` below it are compatible: the body was extracted despite the permission label. Status values are CLI-defined, not API permission values.

Exit codes: 0 = completed without request failures (including preview, restricted, and no-body results); 1 = one or more requests failed; 2 = invalid arguments; 3 = network blocked.
