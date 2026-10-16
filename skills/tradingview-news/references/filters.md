# Filter value reference

Snapshot of accepted values, checked against the English metadata on 2026-10-17. This file supplements the common values in `SKILL.md`; it does not define the scope of TradingView categories. Run `python3 scripts/tv_news.py filters` for current API ids and English display titles. Do not translate or normalize the ids used in requests.

## `--sector` (`sector`)

Use the exact English names below. Quote each value containing spaces. No additional industry membership is implied by this reference.

- `"Commercial Services"`
- `Communications`
- `"Consumer Durables"`
- `"Consumer Non-Durables"`
- `"Consumer Services"`
- `"Distribution Services"`
- `"Electronic Technology"`
- `"Energy Minerals"`
- `Finance`
- `Government`
- `"Health Services"`
- `"Health Technology"`
- `"Industrial Services"`
- `Miscellaneous`
- `"Non-Energy Minerals"`
- `"Process Industries"`
- `"Producer Manufacturing"`
- `"Retail Trade"`
- `"Technology Services"`
- `Transportation`
- `Utilities`

## `--provider` (`provider`)

These are request ids, including their original spelling and case. Display titles are separate metadata: for example, `dow-jones` has the display title `Dow Jones Newswires`, and `forexlive` has `InvestingLive`. Use `filters` for current titles. `--exclude-provider` accepts ids or names returned in news results.

`reuters`, `dow-jones`, `market-watch`, `trading-economics`, `sharecast`, `dpa_afx`, `macenews`, `business_wire`, `tradingview`, `marketbeat`, `barchart`, `cointelegraph`, `cme_group`, `quartr`, `quartr_insights`, `beincrypto`, `newsbtc`, `zacks`, `stockstory`, `marketindex`, `99Bitcoins`, `acceswire`, `acn`, `bravenewcoin`, `chainwire`, `coindar`, `coinmarketcal`, `coinpedia`, `cryptobriefing`, `cryptonews`, `eqs`, `etfcom`, `financemagnates`, `financewire`, `forexlive`, `globenewswire`, `gurufocus`, `investorplace`, `invezz`, `jcn`, `leverage_shares`, `lse`, `miranda_partners`, `modular_finance`, `moneycontrol`, `nbd`, `tmx_newsfile`, `pressetext`, `prnewswire`, `smallcaps`, `stocktwits`, `the_block`, `thenewswire`, `u_today`, `zawya`, `baystreet`, `cryptoprowl`, `moodys`, `mint`, `benzinga`, `seekingalpha`, `business_line_india`, `economic_times_india`, `businessworld_india`, `bloomingbit`, `asian_news_international`, `binance_news`

## `--lang` (`lang`)

One news request language per invocation; default `en`. These values do not select the CLI's output language or change the display time zone. Preserve the codes exactly, including `en_IN`, `zh-Hans`, and `zh-Hant`.

`ar`, `de`, `en`, `en_IN`, `es`, `fr`, `he`, `id`, `it`, `ja`, `ko`, `ms`, `pl`, `pt`, `ru`, `th`, `tr`, `vi`, `zh-Hans`, `zh-Hant`
