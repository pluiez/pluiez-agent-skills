---
name: tradingview-news
description: 获取并总结 TradingView 全市场新闻流（News Flow）：默认先给精简的新闻标题列表，用户点名后再取单篇全文。适用于看或总结 TradingView 新闻、news flow、市场要闻、今天有什么新闻，或某个市场、国家、行业、新闻来源、标的的最新新闻。只要是从 TradingView 获取新闻，都用本 skill 自带的脚本，不要自己用 requests 抓网页，也不要用 tradingview-scraper 库或浏览器。
---

# TradingView 新闻流

用本 skill 目录下的 `scripts/tv_news.py` 获取 TradingView 新闻。脚本只用 Python 标准库，无需安装任何包，直接调用 TradingView 网页本身使用的 JSON 接口。

信息分两级，按需逐级展开：

1. **第一级 `list`**：按筛选条件拉取新闻流，合并、去重后，每条新闻输出一行（时间、来源、标题、相关标的、访问级别）。**默认只走这一级。**
2. **第二级 `read`**：按序号或文章 id 取单篇正文，并严格按该文章的访问级别输出。**只在用户点名要展开时才调用。**

不使用 `tradingview-scraper` 库的原因：它的正文解析已经失效，只返回空内容；全文请求走的根域名会被网络白名单拦截；也没有全市场新闻流接口。

## 运行要求

- Python 3.9+。
- 运行环境要能访问 `*.tradingview.com`。Claude 网页版的云端环境默认拦截这个域名。如果脚本输出 `error=network_blocked`，原样告诉用户：需要在 Claude 设置 → Capabilities → Allow network egress → Additional allowed domains 中加入 `*.tradingview.com`。不要换其他方式绕过。
- 不需要登录。实测登录后既不能翻页，也不能多拿条数；免费账户的付费文章权限也不会变化。

## 工作流程

1. **映射需求**：把用户的要求映射成 `list` 参数。没有特别要求时直接运行 `list`，默认最近 24 小时，使用 `default` 预设。用户提到市场、国家、行业、公司事件、来源、标的或时间范围时，换用对应的预设或筛选参数（见下文"筛选"）。不确定某个取值怎么写时，先运行 `filters` 查看。
2. **读表头**：表头的 `# 查询 N` 行说明每路查询是否完整覆盖了时间窗口。出现 `⚠ 窗口内更早的新闻未获取` 时，回复中必须告诉用户实际只覆盖到几点，并建议收窄筛选（加国家、行业、来源等条件）或缩短时间窗口。
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

服务端有两个限制，决定了脚本的设计：

- **每次请求最多返回 200 条，而且不能翻页**：游标和起止日期参数都会被拒绝，登录后也一样。所以筛选越宽，200 条覆盖的时间越短。脚本会在表头报告每路查询的覆盖情况。
- **所有筛选条件都是"并且"关系**，同一参数的多个值也是如此。例如同时传两个标的，返回的是同时提到两者的新闻。为此脚本把同一参数的多个值拆成多次请求再合并，实现"或者"的效果；不同参数之间仍是"并且"。组合后的请求数上限为 30。

预设（`--preset`）：

| 预设 | 内容 | 实测量级 |
|---|---|---|
| `default` | TradingView 头条，加上 Reuters 和 Dow Jones 的"重要"新闻 | 一天约 25～30 条，完整覆盖 24 小时 |
| `top` | TradingView 编辑精选头条 | 一天约 3 条 |
| `important` | 所有"重要"新闻 | 约 98% 是 TradingView 自动生成的内容，200 条只覆盖约 6 小时 |
| `us-important` | 美股 + 重要 | 同上，以 TradingView 自动内容和分析师评级短讯为主 |
| `us-stocks` | 美股全部 | 200 条约覆盖 2～3 小时 |
| `macro` | 宏观经济 | 200 条约覆盖 10 小时 |
| `crypto` | 加密货币 | 200 条约覆盖一天 |
| `all` | 不加筛选 | 200 条不到 1 小时，只适合配合 `--hours 1` 看最新动态 |

给出任何筛选参数而不指定 `--preset` 时，只用这些参数查询。同时指定 `--preset` 时，这些参数会叠加到预设的每一路查询上。

筛选参数（取值以 `filters` 的输出为准）：

| 参数 | 含义 | 示例取值 |
|---|---|---|
| `--market` | 市场类型 | `stock` `etf` `crypto` `forex` `index` `futures` `bond` `corp_bond` `economic` |
| `--country` | 国家，两位代码 | `US` `CN` `JP` `KR` `HK` `TW` |
| `--sector` | 行业（名称含空格时加引号） | `"Electronic Technology"` `"Technology Services"` `Finance` |
| `--corp` | 公司事件 | `earnings` `ipo` `mergers_and_acquisitions` `recommendation` `management` |
| `--econ` | 宏观类别 | `gdp` `labor` `prices` `money` `trade` `housing` |
| `--crypto` | 加密货币主题 | `regulation` `etfs` `security` `exchanges` |
| `--provider` | 来源 | `reuters` `dow-jones` `market-watch` `benzinga` `seekingalpha` `tradingview` |
| `--priority` | 格式 | `top_stories` `important` `flash` `key_facts` |
| `--symbol` | 标的，写成"交易所:代码" | `NASDAQ:NVDA` `NYSE:TSM` `KRX:005930` |

本地筛选：`--keyword`（标题正则，多个之间为"或者"）、`--exclude-provider`（例如排除 `tradingview_analyst_updates`，即自动生成的分析师评级短讯）、`--full-only`（只看可读全文的）、`--flash-only`（只看快讯）、`--limit`（默认全部输出）。

## 常用命令

默认要闻，最近 24 小时：

```bash
python3 scripts/tv_news.py list
```

最近 12 小时的宏观新闻，以及最近 6 小时的美股新闻，去掉自动生成的评级短讯：

```bash
python3 scripts/tv_news.py list --preset macro --hours 12
python3 scripts/tv_news.py list --market stock --country US --hours 6 --exclude-provider tradingview_analyst_updates
```

美国电子科技行业，只看可读全文的；单个标的最近 3 天、标题含 China 或 export 的：

```bash
python3 scripts/tv_news.py list --sector "Electronic Technology" --country US --full-only
python3 scripts/tv_news.py list --symbol NASDAQ:NVDA --hours 72 --keyword "China|export"
```

中日韩股市（自动拆成 3 次请求再合并）：

```bash
python3 scripts/tv_news.py list --market stock --country CN JP KR --hours 12
```

展开上一次列表中的第 3 条和第 7 条；按 id 读取；放宽单篇字数上限：

```bash
python3 scripts/tv_news.py read '#3' '#7'
python3 scripts/tv_news.py read 'DJN_DN20261016003434:0'
python3 scripts/tv_news.py read '#3' --max-chars 20000
```

查看所有筛选项的取值：

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
