# 筛选取值全表

`SKILL.md` 只列常用取值，本文件列出全部取值。这是某一时刻的快照，服务端当前的取值以 `python3 scripts/tv_news.py filters` 的输出为准。

## `--sector`

行业名称含空格时，要给每个值加引号。

| 取值 | 含义 |
| --- | --- |
| `"Commercial Services"` | 商业服务 |
| `Communications` | 通信 |
| `"Consumer Durables"` | 耐用消费品 |
| `"Consumer Non-Durables"` | 非耐用消费品 |
| `"Consumer Services"` | 消费者服务 |
| `"Distribution Services"` | 分销服务 |
| `"Electronic Technology"` | 电子科技，含半导体、硬件 |
| `"Energy Minerals"` | 能源矿产，含石油、煤炭 |
| `Finance` | 金融 |
| `Government` | 政府 |
| `"Health Services"` | 医疗服务 |
| `"Health Technology"` | 医疗科技，含制药、医疗器械 |
| `"Industrial Services"` | 工业服务 |
| `Miscellaneous` | 其他 |
| `"Non-Energy Minerals"` | 非能源矿产，含金属、采矿 |
| `"Process Industries"` | 流程工业，含化工、材料 |
| `"Producer Manufacturing"` | 生产制造 |
| `"Retail Trade"` | 零售 |
| `"Technology Services"` | 科技服务，含软件、互联网 |
| `Transportation` | 交通运输 |
| `Utilities` | 公用事业 |

## `--provider`

括号内为网页显示名，`--exclude-provider` 也可以按显示名匹配。

`reuters`（Reuters）、`dow-jones`（Dow Jones Newswires）、`market-watch`（MarketWatch）、`trading-economics`（Trading Economics）、`sharecast`（ShareCast）、`dpa_afx`（dpa-AFX）、`macenews`（Mace News）、`business_wire`（BusinessWire）、`tradingview`（TradingView）、`marketbeat`、`barchart`、`cointelegraph`、`cme_group`（CME Group）、`quartr`、`quartr_insights`（Quartr Insights）、`beincrypto`、`newsbtc`、`zacks`、`stockstory`（Stock Story）、`marketindex`（Market Index）、`99Bitcoins`、`acceswire`（ACCESS Newswire）、`acn`（Asian Corporate Newswire）、`bravenewcoin`（Brave New Coin）、`chainwire`、`coindar`、`coinmarketcal`（CoinMarketCal）、`coinpedia`、`cryptobriefing`（Crypto Briefing）、`cryptonews`（CryptoNews）、`eqs`（EQS）、`etfcom`（etf.com）、`financemagnates`（Finance Magnates）、`financewire`（FinanceWire）、`forexlive`（InvestingLive）、`globenewswire`（GlobeNewswire）、`gurufocus`（GuruFocus）、`investorplace`（InvestorPlace）、`invezz`、`jcn`（Japan Corporate News）、`leverage_shares`（Leverage Shares）、`lse`（London Stock Exchange）、`miranda_partners`（Miranda Partners）、`modular_finance`（MFN by Modular Finance）、`moneycontrol`、`nbd`（National Bank Of Denmark）、`tmx_newsfile`（TMX Newsfile）、`pressetext`、`prnewswire`（PR Newswire）、`smallcaps`（Small Caps）、`stocktwits`、`the_block`（The Block）、`thenewswire`（TheNewswire）、`u_today`（U.Today）、`zawya`、`baystreet`（BayStreet）、`cryptoprowl`（CryptoProwl）、`moodys`（Moody's）、`mint`、`benzinga`、`seekingalpha`（Seeking Alpha）、`business_line_india`（Business Line）、`economic_times_india`（Economic Times）、`businessworld_india`（Businessworld）、`bloomingbit`、`asian_news_international`（Asian News International）、`binance_news`（Binance News）

## `--lang`

单选，默认 `en`。

`ar` 阿拉伯语、`de` 德语、`en` 英语、`en_IN` 英语（印度）、`es` 西班牙语、`fr` 法语、`he` 希伯来语、`id` 印尼语、`it` 意大利语、`ja` 日语、`ko` 韩语、`ms` 马来语、`pl` 波兰语、`pt` 葡萄牙语、`ru` 俄语、`th` 泰语、`tr` 土耳其语、`vi` 越南语、`zh-Hans` 简体中文、`zh-Hant` 繁体中文
