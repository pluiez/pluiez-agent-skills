# pluiez-agent-skills

[English](README.md) | [简体中文](README.zh-CN.md)

个人 agent skills 与可复用工作流集合。

这个仓库有意保持运行时中立。不同 agent、编辑器和工具有不同的 skill 加载方式，所以这里仅提供 skill 目录及其配套资源，不绑定某一种安装流程。

## Skills

| Skill | 路径 | 说明 |
| --- | --- | --- |
| CNBC Quotes | `skills/cnbc-quotes` | 查询 CNBC 行情及分组市场快照，保留单标的错误、来源时间、来源给出完整时间时的报价年龄检查，以及独立的常规/盘前盘后行情；内置仅使用标准库的 Python CLI。 |
| Conventional Commits | `skills/conventional-commits` | 编写或修改 git commit message 时遵循的 Conventional Commits 1.0.0 规范参考。 |
| Gemini Image CLI | `skills/gemini-image-cli` | 通过 Gemini-compatible endpoint 生成和编辑图像，内置一个 Bash CLI。 |
| GitHub Proxy | `skills/github-proxy` | 当 github.com 超时、连接被拒或返回空响应时，将 GitHub URL 通过 `gh-proxy.org` 转发。 |
| PDF Region Crop | `skills/pdf-region-crop` | 渲染 PDF 页面，并从原页面截取任意矩形区域（图、表、正文片段、标题、公式）为高清 PNG，内置一个 Python CLI。 |
| Paper zh Translation | `skills/paper-zh-translation` | 把学术论文 PDF 完整翻译成简体中文 Markdown，同时整理一份对应的原文 Markdown，并嵌入从原 PDF 截取的图表；出图依赖一个具备 PDF 区域截图能力的 skill。 |
| TradingView News | `skills/tradingview-news` | 按市场、国家、行业、来源或标的搜索、筛选 TradingView 新闻流：先给精简标题列表，按需再读取单篇正文，原始 `permission` 与正文解析 `status` 分开表示；内置一个只用标准库的 Python CLI。 |
| Verify with Citations | `skills/verify-with-citations` | 核实、查证类任务的引用格式：逐字引原文、署名作者或机构、标题用 Markdown 链接并附章节层级，超过 3 项时补来源清单表。 |

## CNBC Quotes

CNBC Quotes skill 提供自包含的 Python 3.9+ 标准库 CLI，采集行情而不是新闻正文。运行环境需要能访问 `quote.cnbc.com`，不需要 API key 或安装依赖包。

```bash
python3 skills/cnbc-quotes/scripts/cnbc_quotes.py snapshot
python3 skills/cnbc-quotes/scripts/cnbc_quotes.py snapshot --preset asia
python3 skills/cnbc-quotes/scripts/cnbc_quotes.py quote AAPL .SPX US10Y '@GC.1' --json
python3 skills/cnbc-quotes/scripts/cnbc_quotes.py presets
python3 -B -m unittest discover -s tests -p 'test_cnbc_quotes.py'
```

预设是 CLI 定义的标的分组，不是 CNBC 的官方分类。自定义查询使用 CNBC 代码（例如 `700-HK`、`600519-CN`，而不是 `0700.HK`、`600519.SS`），不能直接套用 TradingView 或其他行情商的代码。缺失或不支持的标的会逐项报告，不会静默丢弃。

输出保留来源时间、币种、标的类型、`realTime`、`curmktstatus`，并将常规行情与盘前盘后行情分开。仅日期或含义不明确的时间不会被补成虚构的收盘时间。可配置的报价年龄检查只提示数据是否较旧，不推断交易所日历或休市状态；来源声称实时也不等于报价足够新鲜。很多报价只有日期（非交易时段实测，指数和美股都是如此），无法计算报价年龄；期货的报价时间也可能晚于抓取时间。期货保留实际合约名称。显示时区默认 `Asia/Shanghai`，可用 `--tz` 或 `CNBC_QUOTES_TZ` 修改。

skill 文档与 CLI 自身的输出使用英文，对话语言由调用方决定。接口字段、已观察到的代码和数据限制见 `skills/cnbc-quotes/references/quotes.md`。该网站行情服务可能变化或不可用，不保证它是官方承诺支持的 API，也不将其视为交易所认证的实时行情。

## Gemini Image CLI

Gemini Image CLI skill 包含一个自包含脚本：

```bash
skills/gemini-image-cli/scripts/gemini-image.sh "A cute orange kitten sitting on a soft blanket"
```

查看完整 CLI 帮助：

```bash
skills/gemini-image-cli/scripts/gemini-image.sh --help
```

这个 CLI 支持：

- Gemini-compatible 本地 proxy endpoint。
- Google 官方 Gemini endpoint。
- 自动 provider 选择：优先本地 proxy，失败后 fallback 到 Google。
- 根据返回 MIME 类型保存 `.png`、`.jpg` 或 `.webp`。
- curl 日志中 mask key，并隐藏输入图片 base64。

## PDF Region Crop

PDF Region Crop skill 包含一个自包含 Python 脚本，依赖 PyMuPDF（`pip install pymupdf`）：

```bash
python skills/pdf-region-crop/scripts/pdf_regions.py prepare paper.pdf
python skills/pdf-region-crop/scripts/pdf_regions.py crop paper.pdf --regions regions.json --out assets
```

查看完整 CLI 帮助：

```bash
python skills/pdf-region-crop/scripts/pdf_regions.py --help
```

区域一律用归一化坐标 `[fx0, fy0, fx1, fy1]`（0..1，原点在页面左上角）表示，与查看时的缩放倍率无关，旋转页面同样适用。

## Paper zh Translation

纯文档 skill，没有脚本。它不写死截图工具的名字，只声明需要的能力（渲染页面、从原 PDF 截取指定区域、输出目录和文件名由调用方指定、越界时报错），由 agent 从可用的 skill 中按能力挑选。找不到满足条件的 skill 时，会停下来提示用户，不会临时写代码顶替。

## TradingView News

TradingView News skill 包含一个仅使用 Python 3.9+ 标准库的 CLI，无需安装依赖包。运行环境须能访问 `*.tradingview.com`。skill 文档与工具自身的输出统一使用英文，新闻内容保留来源语言。`--lang` 只控制新闻请求语言，与对话语言、时区设置相互独立。

```bash
python3 skills/tradingview-news/scripts/tv_news.py list            # 标题列表
python3 skills/tradingview-news/scripts/tv_news.py read '#3' '#7'  # 按需读取正文
python3 skills/tradingview-news/scripts/tv_news.py filters         # 当前英文 API metadata
```

不带参数时，`list` 只发送新闻语言筛选，并输出接口返回的全部条目。不同 filter 之间使用 AND，同一 filter 的多个值使用 OR。已观察到的单次请求上限为 200 条，CLI 不执行分页，覆盖范围说明会提示可能遗漏的内容。`--split` 按每种 filter-value combination 分别请求，再按 id 合并。`wires` 等 preset 是 CLI 定义的筛选组合；API 字段、枚举、分类名称及英文 display title 保留原始形式。

输出分别保留 API 原始 `permission` 和 CLI 定义的 `status`。`read` 优先解析已返回的正文，成功后输出 `status=full`，不因 `permission` 丢弃正文，仍遵循 `--max-chars` 截断规则并附加提示。只有未解析出正文时，才回退到 `preview`、`restricted` 或 `no_body`；这些状态不证明某种具体订阅要求，也不保证原文完整性。保留的 `--full-only` 参数仅筛选 `permission` 缺失或为 null 的列表条目，不验证正文是否可用。显示时区仍默认为 `Asia/Shanghai`，可用 `--tz` 或 `TV_NEWS_TZ` 修改。

## Verify with Citations

纯文档 skill，没有脚本。用户要求核实、查证、确认某个说法时，用统一的引用格式作答：先给结论，再给引用块——逐字引原文（不在引号内翻译）、加粗真正定案的那一句、署名作者或机构、标题用 Markdown 链接并在链接后附章节层级（`§4`、`Table 4`、`p. 7`），整体放在一个斜体 span 里。引用超过 3 项时，在末尾补一张来源清单表；来源立场不一致时按立场分组，查过但不支持结论的来源也一并列出。

硬约束是不编造引文、URL、作者和章节号，无法取得原文时宁可不引；取不到的信息就地标注（如"页面未声明所属机构""仅见摘要"）。

## 安全

环境变量可以避免把 secret 写进源码或 shell 命令历史，但它不是强安全边界；任何能在同一环境里执行任意 shell 命令的运行时，理论上都可能读取这些环境变量。

如果真实 Google Gemini API key 不应暴露给 CLI 运行时，建议使用本地 proxy 模式。真实 Google key 保存在本地 proxy 内部，CLI 只发送风险较低的本地 proxy key。

## License

MIT
