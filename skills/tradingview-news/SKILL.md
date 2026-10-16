---
name: tradingview-news
description: 搜索、筛选 TradingView 新闻流（News Flow）：市场要闻，以及按市场、国家、行业、新闻来源、标的筛选的最新新闻，可按需读取单篇正文。
---

# TradingView 新闻流

只用 `scripts/tv_news.py` 获取 TradingView 新闻流，不要改用 requests、`tradingview-scraper` 或浏览器。脚本报错时如实报告错误，不要换其他方式重试。

脚本分两级：

1. `list`：按筛选条件拉取新闻流，每条一行，包含序号、时间、来源、标题、相关标的、访问级别。
2. `read`：按 `#N` 或文章 id 读取单篇正文。只在需要具体某几条的正文时调用，不要为了补充标题列表而批量读取。

## 运行要求

- Python 3.9+，无需安装任何包。
- 运行环境必须能访问 `*.tradingview.com`。脚本输出 `error=network_blocked` 时，原样转告它给出的提示，不要绕过。

## 工作流程

1. 确定 `list` 的参数：
   - 没有特定范围：不带参数运行 `list`。
   - 要闻：`--preset wires --hours 24`。
   - 限定时间：加 `--hours N`。
   - 限定市场、国家、行业、公司事件、宏观类别、来源或标的：用"筛选"一节的参数。
2. 检查表头。`# 查询 N` 行给出每路查询的条数和覆盖时段。出现"已达单次上限，更早的新闻未获取"或"⚠ 窗口内更早的新闻未获取"时，结果只覆盖到表头所示的时间，并不完整。需要更长时段时，收窄筛选，或对多值筛选加 `--split`。
3. 只依据标题使用 `list` 的结果，不推断标题以外的内容。
4. 需要正文时运行 `read`。
5. 按 `read` 输出的 `status` 判断拿到了什么：
   - `full`：正文。超过 `--max-chars` 时被截断，末尾有标注。
   - `preview`：只有摘要，不是正文。
   - `restricted`：需要订阅，只有标题和链接。
   - `no_body`：纯标题快讯，本身没有正文。
   - `error`：获取失败，原因在同一段输出中。

   优先解析接口已返回的 `astDescription` 正文。只要解析出正文，就正常输出并标记 `status=full`，仍遵循 `--max-chars` 的截断规则；即使 `permission` 为 `headline`、`provider` 或 `preview`，也不丢弃已取得的正文。只有未解析出正文时，才根据权限信息判断预览或受限状态。

## 规则

- `#N` 只对最近一次 `list` 的结果有效，再次运行 `list` 后序号会重新编排。
- 时间默认按 GMT+8（`Asia/Shanghai`）显示，可用 `--tz` 或环境变量 `TV_NEWS_TZ` 修改。

## 筛选

不传某个筛选参数，即该项不限。不同筛选项之间是"并且"，同一筛选项的多个值之间是"或者"。例如 `--market stock --country US JP` 表示"股票，并且国家是美国或日本"。多个值用空格或逗号分隔，含空格的值要加引号。

每次请求最多返回 200 条，不能翻页。筛选越宽，覆盖的时段越短。

### 筛选参数

| 参数 | 含义 | 取值 |
| --- | --- | --- |
| `--market` | 市场类型 | `stock` 股票、`etf`、`crypto` 加密货币、`forex` 外汇、`index` 指数、`futures` 期货、`bond` 国债、`corp_bond` 公司债、`economic` 宏观经济 |
| `--country` | 国家 | ISO 3166-1 两位代码，如 `US` `CN` `JP` `KR` `HK` `TW` `GB` `DE` `IN` |
| `--sector` | 行业 | 常用：`"Electronic Technology"`（电子科技，含半导体、硬件）、`"Technology Services"`（科技服务，含软件、互联网）、`Finance` 金融、`"Health Technology"`（医疗科技，含制药）、`"Energy Minerals"`（能源矿产，含石油、煤炭）、`"Retail Trade"` 零售 |
| `--corp` | 公司事件 | `earnings` 财报、`earnings_calls` 财报电话会、`ipo`、`dividends` 分红、`share_buybacks` 回购、`mergers_and_acquisitions` 并购、`strategy_business_products` 战略与业务、`management` 管理层变动、`insider_trading` 内部人交易、`ownership_changes` 持股变动、`esg` ESG 与监管、`recommendation` 分析师评级、`credit_ratings` 信用评级 |
| `--econ` | 宏观类别 | `gdp`、`labor` 就业、`prices` 物价与通胀、`money` 央行与货币政策、`trade` 贸易、`government` 财政与政府政策、`business` 企业景气、`consumer` 消费、`housing` 房地产、`taxes` 税收、`health` 公共卫生与医保 |
| `--crypto` | 加密货币主题 | `market` 行情、`etfs`、`pegs_reserves_and_liquidity` 稳定币与流动性、`regulation` 监管、`adoption` 采用、`technology` 技术、`security` 安全事件、`fundraising` 融资、`tokenomics` 代币经济、`exchanges` 交易所、`people` 人物 |
| `--priority` | 新闻格式 | `flash` 快讯、`important` 重要、`top_stories` 编辑精选头条、`key_facts` 自动生成的要点摘要 |
| `--symbol` | 标的 | `交易所:代码`，如 `NASDAQ:NVDA` `NYSE:TSM` `HKEX:700` |
| `--provider` | 新闻来源 | 常用：`reuters`、`dow-jones`、`market-watch`、`trading-economics`、`tradingview`、`benzinga`、`seekingalpha`、`cointelegraph` |
| `--lang` | 语言，单选 | 默认 `en`；常用 `zh-Hans` `zh-Hant` `ja` `ko` |

数据中常见的 `tradingview_analyst_updates`（自动生成的分析师评级短讯）不能用作 `--provider`，只能用 `--exclude-provider` 排除。

表中未列出的行业、来源、语言取值，读 `references/filters.md`。怀疑取值已过时，运行 `filters` 查看服务端当前的取值。

### 预设

`--preset` 是固定的筛选组合，不能与筛选参数同时使用。需要在预设基础上改条件时，直接写出完整的筛选参数。

| 预设 | 内容 |
| --- | --- |
| `wires` | 编辑精选头条，加上 Reuters 和 Dow Jones 的重要新闻 |
| `top` | 编辑精选头条 |
| `important` | 所有重要新闻，以 TradingView 自动生成的内容为主 |
| `us-important` | 美股中的重要新闻 |
| `us-stocks` | 美股 |
| `macro` | 宏观经济 |
| `crypto` | 加密货币 |

`wires` 和 `top` 每天只有几条到几十条，200 条可能回溯数月，必须配合 `--hours`。

### `list` 的其他参数

`--split` 决定怎么发请求；其余参数都在拿到服务端结果之后处理，不影响请求本身。

| 参数 | 作用 | 默认 |
| --- | --- | --- |
| `--split` | 同一筛选项的每个值单独请求（多个筛选项都多选时，按每种组合请求），各取 200 条后按 id 合并，覆盖更长时段；最多 30 个请求 | 关闭：多个值合并成一次请求，共享 200 条 |
| `--hours N` | 只保留最近 N 小时 | 不过滤 |
| `--keyword RE ...` | 只保留标题匹配任一正则的条目，忽略大小写 | 不过滤 |
| `--exclude-provider P ...` | 排除这些来源，按 id 或显示名匹配 | 不排除 |
| `--full-only` | 只保留访问级别为 `全文` 的条目 | 关闭 |
| `--flash-only` | 只保留快讯 | 关闭 |
| `--dedupe-titles` | 合并标题相同的条目，保留最新一条 | 关闭 |
| `--limit N` | 最多输出 N 条 | 全部输出 |

### `read` 的参数

| 参数 | 作用 | 默认 |
| --- | --- | --- |
| 位置参数 | 一个或多个 `#N`（`#` 可省略）或文章 id | 必填 |
| `--max-chars N` | 每篇正文的字符上限，超出部分截断 | 8000 |
| `--max-stories N` | 一次最多读取几篇，超出时报错 | 5 |
| `--lang` | 读取正文时使用的语言 | `en` |

## 常用命令

命令中的路径相对本 skill 目录。

```bash
python3 scripts/tv_news.py list                                   # 不带筛选
python3 scripts/tv_news.py list --preset wires --hours 24         # 最近 24 小时要闻
python3 scripts/tv_news.py list --market stock --country US --hours 6 \
  --exclude-provider tradingview_analyst_updates                  # 美股，去掉评级短讯
python3 scripts/tv_news.py list --symbol NASDAQ:NVDA NASDAQ:AMD --hours 72 --keyword "China|export"
python3 scripts/tv_news.py list --market stock --country CN JP KR --hours 12 --split
python3 scripts/tv_news.py read '#3' '#7'
python3 scripts/tv_news.py filters                                # 服务端当前的筛选取值
```

## 输出与退出码

结果写到标准输出，进度写到标准错误。`list` 的表头以 `# ` 开头，之后每条一行：

```
#3 10-16 21:00 | Dow Jones Newswires | Canada Housing Starts Rise in September, ... | CAHST | 全文
```

`list` 的访问级别来自接口权限标签：`全文`、`预览`、`仅标题`、`受限`，不能据此确定 `read` 是否能取得正文；`--full-only` 也仅按此标签筛选。行尾可能带有 `快讯` 或 `独家` 标记。`read` 若解析出正文，访问级别显示为 `全文`，实际读取结果以 `status` 为准。

`read` 的每篇文章依次输出标题、元信息（来源、时间、标的、访问级别）、链接、一行 `status=...`，最后是正文或说明。

退出码：0 成功；1 部分请求失败；2 参数错误；3 网络被拦截。
