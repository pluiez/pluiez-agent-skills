---
name: tradingview-news
description: 获取并总结 TradingView 全市场新闻流（News Flow）：默认先给精简的新闻标题列表，用户点名后再取单篇全文。适用于看或总结 TradingView 新闻、news flow、市场要闻、今天有什么新闻，或某个市场、国家、行业、新闻来源、标的的最新新闻。只要是从 TradingView 获取新闻，都用本 skill 自带的脚本，不要自己用 requests 抓网页，也不要用 tradingview-scraper 库或浏览器。
---

# TradingView 新闻流

用本 skill 目录下的 `scripts/tv_news.py` 获取 TradingView 新闻。脚本只用 Python 标准库，无需安装任何包，直接调用 TradingView 网页本身使用的 JSON 接口。

信息分两级，按需逐级展开：

1. **第一级 `list`**：按筛选条件拉取新闻流，每条新闻输出一行（时间、来源、标题、相关标的、访问级别）。**默认只走这一级。**
2. **第二级 `read`**：按序号或文章 id 取单篇正文，并严格按该文章的访问级别输出。**只在用户点名要展开时才调用。**

不传任何参数时，`list` 的行为与 TradingView 网页 News Flow 页面的默认状态完全一致：只带语言筛选（英文），发一次请求，把返回的全部条目（最多 200 条）原样按时间倒序输出，不做时间截断，也不合并同标题条目。

不使用 `tradingview-scraper` 库的原因：它的正文解析已经失效，只返回空内容；全文请求走的根域名会被网络白名单拦截；也没有全市场新闻流接口。

## 运行要求

- Python 3.9+。
- 运行环境要能访问 `*.tradingview.com`。Claude 网页版的云端环境默认拦截这个域名。如果脚本输出 `error=network_blocked`，原样告诉用户：需要在 Claude 设置 → Capabilities → Allow network egress → Additional allowed domains 中加入 `*.tradingview.com`。不要换其他方式绕过。
- 不需要登录。实测登录后既不能翻页，也不能多拿条数；免费账户的付费文章权限也不会变化。

## 工作流程

1. **映射需求**：把用户的要求映射成 `list` 参数。
   - 没有特别要求：直接运行 `list`，与网页默认一致。
   - 用户提到时间范围（"今天""最近 24 小时""过去 3 小时"）：加 `--hours`。
   - 用户提到市场、国家、行业、公司事件、宏观类别、来源、标的：用下文"筛选"中的参数，取值直接查表，不必先运行 `filters`。
   - 用户要"要闻""重点新闻"：用 `--preset wires --hours 24`。
2. **读表头**：表头的 `# 查询 N` 行说明每路查询拿到了多少条、覆盖了哪段时间。出现"已达单次上限，更早的新闻未获取"或"⚠ 窗口内更早的新闻未获取"时，回复中必须告诉用户实际只覆盖到几点。如果用户需要更长的时间范围，建议收窄筛选，或对多值筛选加 `--split`。
3. **基于标题总结**，用中文写：
   - 按主题归类，例如宏观与央行、美股大盘、公司事件、行业、地区市场。同一事件的多条快讯合并成一点（Dow Jones 常连发多条）。
   - 每一点注明来源和时间（北京时间）。重要的点可以附上序号，例如 `#3`，方便用户点名展开。
   - 不要逐条罗列或逐条翻译整个列表，除非用户要求。只能从标题判断的内容不要过度推断，也不要补充列表里没有的事实。
4. **按需展开**：只有用户点名（"展开 #3、#7"、"详细说说 Netflix 那条"）时才运行 `read`。不要为了让总结更完整而主动去读全文。一次最多 5 篇。
5. **按 `status` 处理 `read` 的结果**：
   - `status=full`：基于正文概括要点，用中文写。不要整篇转贴或全文翻译，需要引用时只引一两句短句。
   - `status=preview`：明确说明只有摘要，不是全文。
   - `status=restricted`：明确告诉用户这篇需要 TradingView 订阅才能看全文，并给出链接。不要尝试用浏览器、网页抓取或其他接口绕过付费墙。
   - `status=no_body`：说明这是纯标题快讯，本身没有正文。
   - `status=error`：说明获取失败的原因。
6. **结尾提示**：可以提示用户能展开哪些条目。不要提及脚本、命令或参数本身。

## 规则

- 只用本脚本获取 TradingView 新闻。脚本报错时如实告诉用户，不要临时改用其他抓取方式。
- 访问级别以接口返回的 `permission` 为准：`全文` 可读正文；`预览` 只给摘要；`仅标题` 和 `受限` 只给标题。接口有时会把受限文章的正文一起返回，但那是网页前端靠付费墙遮挡的内容，脚本不会输出，也不要设法获取。
- 时间默认按北京时间（GMT+8）显示，与 TradingView 网页在你的浏览器里显示的一致（网页按浏览者本地时区显示）。用户要求其他时区时用 `--tz`。
- `read` 的序号只对最近一次 `list` 的结果有效。重新运行 `list` 后，序号会重新编排。

## 筛选

### 服务端规则

- **不同筛选项之间是"并且"，同一筛选项的多个值之间是"或者"**，与网页端勾选筛选条件的效果一致。例如 `--market stock --country US JP` 表示"股票，并且国家是美国或日本"。
- **每次请求最多返回 200 条，而且不能翻页**：游标和起止日期参数都会被拒绝，登录后也一样。筛选越宽，200 条覆盖的时间越短，所以脚本会在表头报告每路查询的覆盖情况。
- 同一筛选项的多个值默认合并成一次请求，和网页一样，所有值共享 200 条上限。加 `--split` 则每个值各发一次请求，各自取 200 条后合并去重，覆盖时间更长。多个筛选项都多选时按组合拆分，拆分后的请求数上限为 30。
- 同一筛选项实测传 32 个标的、22 个来源都正常返回；更大的数量未测试。
- 语言只能选一个（服务端限制）。需要登录的"自选列表"筛选不支持。

### 预设

预设（`--preset`）是固定的筛选组合，**不能和筛选参数同时使用**。需要在预设基础上改条件时，直接写出完整的筛选参数。

| 预设 | 内容 | 实测量级 |
|---|---|---|
| 不用预设（默认） | 只带语言筛选，与网页默认一致 | 200 条，美股交易时段约覆盖 1 小时 |
| `wires` | TradingView 编辑精选头条，加上 Reuters 和 Dow Jones 的"重要"新闻 | 一天约 25～30 条；200 条可往回覆盖数天到数月，**务必配合 `--hours`** |
| `top` | TradingView 编辑精选头条 | 一天约 3 条；**务必配合 `--hours`** |
| `important` | 所有"重要"新闻 | 约 98% 是 TradingView 自动生成的内容，200 条约覆盖 6 小时 |
| `us-important` | 美股 + 重要 | 同上，以 TradingView 自动内容和分析师评级短讯为主 |
| `us-stocks` | 美股全部 | 200 条约覆盖 2～3 小时 |
| `macro` | 宏观经济 | 200 条约覆盖 10 小时 |
| `crypto` | 加密货币 | 200 条约覆盖一天 |

### 筛选参数与全部取值

多个值用空格或逗号分隔。行业名称含空格时，要给每个值加引号。

| 参数 | 含义 | 全部取值 |
|---|---|---|
| `--market` | 市场类型 | `stock`（股票）、`etf`（Exchange-Traded Fund，交易所交易基金）、`crypto`（加密货币）、`forex`（外汇）、`index`（指数）、`futures`（期货）、`bond`（Government bonds，国债）、`corp_bond`（Corporate bonds，公司债）、`economic`（Economy，宏观经济） |
| `--country` | 国家 | ISO 3166-1 两位国家代码，如 `US` `CN` `JP` `KR` `HK` `TW` `GB` `DE` `IN`（不穷举） |
| `--sector` | 行业（TradingView 行业分类） | `"Commercial Services"`（商业服务）、`Communications`（通信）、`"Consumer Durables"`（耐用消费品）、`"Consumer Non-Durables"`（非耐用消费品）、`"Consumer Services"`（消费者服务）、`"Distribution Services"`（分销服务）、`"Electronic Technology"`（电子科技，含半导体、硬件）、`"Energy Minerals"`（能源矿产，含石油、煤炭）、`Finance`（金融）、`Government`（政府）、`"Health Services"`（医疗服务）、`"Health Technology"`（医疗科技，含制药、医疗器械）、`"Industrial Services"`（工业服务）、`Miscellaneous`（其他）、`"Non-Energy Minerals"`（非能源矿产，含金属、采矿）、`"Process Industries"`（流程工业，含化工、材料）、`"Producer Manufacturing"`（生产制造）、`"Retail Trade"`（零售）、`"Technology Services"`（科技服务，含软件、互联网）、`Transportation`（交通运输）、`Utilities`（公用事业） |
| `--corp` | 公司事件 | `ipo`（Initial Public Offering，首次公开募股）、`earnings`（财报）、`earnings_calls`（财报电话会）、`dividends`（分红）、`share_buybacks`（股票回购）、`strategy_business_products`（Strategy, business, and products，战略、业务与产品）、`mergers_and_acquisitions`（并购）、`management`（管理层变动）、`insider_trading`（内部人交易）、`ownership_changes`（持股变动）、`esg`（Environmental, Social, and Governance，网页显示为"ESG and regulation"，ESG 与监管）、`recommendation`（网页显示为"Analysts"，分析师评级与观点）、`credit_ratings`（信用评级） |
| `--econ` | 宏观类别 | `gdp`（Gross Domestic Product，国内生产总值）、`labor`（就业与劳动力）、`prices`（物价与通胀）、`health`（网页显示为"Health"，实测以公共卫生和疫情、医疗支出与医保为主）、`money`（网页显示为"Money"，实测以央行与利率、货币政策、信贷为主）、`trade`（贸易）、`government`（实测以财政预算、赤字、政府政策为主）、`business`（实测以企业与行业景气数据为主，如钻井数）、`consumer`（消费）、`housing`（房地产）、`taxes`（税收） |
| `--crypto` | 加密货币主题 | `market`（Market moves，行情变动）、`etfs`（Crypto ETFs，加密货币 ETF）、`pegs_reserves_and_liquidity`（Pegs, reserves, and liquidity，稳定币锚定、储备与流动性）、`regulation`（监管）、`adoption`（采用与普及）、`technology`（技术）、`security`（安全事件）、`fundraising`（融资）、`tokenomics`（代币经济学）、`exchanges`（交易所）、`people`（人物） |
| `--priority` | 新闻格式 | `flash`（快讯，通常为纯标题）、`important`（重要，以 TradingView 自动内容为主）、`top_stories`（编辑精选头条）、`key_facts`（TradingView 自动生成的要点摘要，以加密货币为主） |
| `--symbol` | 标的 | "交易所:代码"，如 `NASDAQ:NVDA` `NYSE:TSM` `KRX:005930` `TSE:6981` `HKEX:700`（不穷举） |
| `--lang` | 语言（单选，默认 `en`） | `ar` `de` `en` `en_IN`（English (India)）`es` `fr` `he` `id`（印尼语）`it` `ja` `ko` `ms`（马来语）`pl` `pt` `ru` `th` `tr` `vi` `zh-Hans`（简体中文）`zh-Hant`（繁体中文） |
| `--provider` | 新闻来源 | 见下表 |

`--provider` 的全部取值（id 后括号内为网页显示名）：

`reuters`、`market-watch`（MarketWatch）、`dow-jones`（Dow Jones Newswires）、`trading-economics`（Trading Economics）、`sharecast`（ShareCast）、`dpa_afx`（dpa-AFX）、`macenews`（Mace News）、`business_wire`（BusinessWire）、`tradingview`、`marketbeat`、`barchart`、`cointelegraph`、`cme_group`（CME Group）、`quartr`、`quartr_insights`（Quartr Insights）、`beincrypto`、`newsbtc`、`zacks`、`stockstory`（Stock Story）、`marketindex`（Market Index）、`99Bitcoins`、`acceswire`（ACCESS Newswire）、`acn`（Asian Corporate Newswire）、`bravenewcoin`（Brave New Coin）、`chainwire`、`coindar`、`coinmarketcal`（CoinMarketCal）、`coinpedia`、`cryptobriefing`（Crypto Briefing）、`cryptonews`（CryptoNews）、`eqs`（EQS）、`etfcom`（etf.com）、`financemagnates`（Finance Magnates）、`financewire`（FinanceWire）、`forexlive`（现显示名为 InvestingLive）、`globenewswire`（GlobeNewswire）、`gurufocus`（GuruFocus）、`investorplace`（InvestorPlace）、`invezz`、`jcn`（Japan Corporate News）、`leverage_shares`（Leverage Shares）、`lse`（London Stock Exchange）、`miranda_partners`（Miranda Partners）、`modular_finance`（MFN by Modular Finance）、`moneycontrol`、`nbd`（网页显示名为 National Bank Of Denmark）、`tmx_newsfile`（TMX Newsfile）、`pressetext`、`prnewswire`（PR Newswire）、`smallcaps`（Small Caps）、`stocktwits`、`the_block`（The Block）、`thenewswire`（TheNewswire）、`u_today`（U.Today）、`zawya`、`baystreet`（BayStreet）、`cryptoprowl`（CryptoProwl）、`moodys`（Moody's）、`mint`、`benzinga`、`seekingalpha`（Seeking Alpha）、`business_line_india`（Business Line）、`economic_times_india`（Economic Times）、`businessworld_india`（Businessworld）、`bloomingbit`、`asian_news_international`（Asian News International）、`binance_news`（Binance News）

另有一个不在上面列表中、但大量出现在数据里的来源：`tradingview_analyst_updates`，是 TradingView 自动生成的分析师评级短讯（"某机构维持某评级、目标价若干"）。它不能用作 `--provider` 筛选，但常用于 `--exclude-provider` 排除噪音。

### 本地筛选与输出控制

| 参数 | 作用 |
|---|---|
| `--hours N` | 只保留最近 N 小时（默认不过滤，与网页一致） |
| `--keyword RE ...` | 只保留标题匹配任一正则的条目，忽略大小写 |
| `--exclude-provider P ...` | 排除这些来源，按 id 或显示名匹配 |
| `--full-only` | 只保留可读全文的条目 |
| `--flash-only` | 只保留快讯 |
| `--dedupe-titles` | 合并标题相同的条目，保留最新一条（默认关闭，与网页一致） |
| `--split` | 多值筛选按值分别请求再合并，见上文"服务端规则" |
| `--limit N` | 最多输出 N 条（默认全部） |
| `--tz` | 显示时区，默认 `Asia/Shanghai` |

## 常用命令

与网页 News Flow 默认状态相同：

```bash
python3 scripts/tv_news.py list
```

今天的要闻；最近 12 小时的宏观新闻：

```bash
python3 scripts/tv_news.py list --preset wires --hours 24
python3 scripts/tv_news.py list --preset macro --hours 12
```

最近 6 小时的美股新闻，去掉自动生成的评级短讯：

```bash
python3 scripts/tv_news.py list --market stock --country US --hours 6 --exclude-provider tradingview_analyst_updates
```

美国电子科技行业，只看可读全文的；单个标的最近 3 天、标题含 China 或 export 的：

```bash
python3 scripts/tv_news.py list --sector "Electronic Technology" --country US --full-only
python3 scripts/tv_news.py list --symbol NASDAQ:NVDA --hours 72 --keyword "China|export"
```

中日韩股市，一次请求（共享 200 条）或按国家拆分（各 200 条，覆盖更长）：

```bash
python3 scripts/tv_news.py list --market stock --country CN JP KR --hours 12
python3 scripts/tv_news.py list --market stock --country CN JP KR --hours 12 --split
```

一组标的中任一只的新闻：

```bash
python3 scripts/tv_news.py list --symbol NASDAQ:NVDA NASDAQ:AMD NYSE:TSM --hours 24
```

展开上一次列表中的第 3 条和第 7 条；按 id 读取；放宽单篇字数上限：

```bash
python3 scripts/tv_news.py read '#3' '#7'
python3 scripts/tv_news.py read 'DJN_DN20261016003434:0'
python3 scripts/tv_news.py read '#3' --max-chars 20000
```

从服务端实时查看筛选取值（只在怀疑上表已过时才需要）：

```bash
python3 scripts/tv_news.py filters
```

## 输出与退出码

结果写到标准输出，进度写到标准错误。`list` 的表头以 `# ` 开头，之后每条一行：

```
#3 10-16 21:00 | Dow Jones Newswires | Canada Housing Starts Rise in September, ... | CAHST | 全文
```

行尾可能带有 `快讯` 或 `独家` 标记。`read` 的每篇文章先输出标题、来源、时间、标的、访问级别和链接，然后是一行 `status=...`，最后是正文或说明。

退出码：0 成功；1 部分请求失败（表头或 `status=error` 会说明原因）；2 参数错误；3 网络被拦截。
