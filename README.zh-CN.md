# pluiez-agent-skills

[English](README.md) | [简体中文](README.zh-CN.md)

个人 agent skills 与可复用工作流集合。

这个仓库有意保持运行时中立。不同 agent、编辑器和工具有不同的 skill 加载方式，所以这里仅提供 skill 目录及其配套资源，不绑定某一种安装流程。

## Skills

| Skill | 路径 | 说明 |
| --- | --- | --- |
| Conventional Commits | `skills/conventional-commits` | 编写或修改 git commit message 时遵循的 Conventional Commits 1.0.0 规范参考。 |
| Gemini Image CLI | `skills/gemini-image-cli` | 通过 Gemini-compatible endpoint 生成和编辑图像，内置一个 Bash CLI。 |
| GitHub Proxy | `skills/github-proxy` | 当 github.com 超时、连接被拒或返回空响应时，将 GitHub URL 通过 `gh-proxy.org` 转发。 |
| PDF Region Crop | `skills/pdf-region-crop` | 渲染 PDF 页面，并从原页面截取任意矩形区域（图、表、正文片段、标题、公式）为高清 PNG，内置一个 Python CLI。 |
| Paper zh Translation | `skills/paper-zh-translation` | 把学术论文 PDF 完整翻译成简体中文 Markdown，同时整理一份对应的原文 Markdown，并嵌入从原 PDF 截取的图表；出图依赖一个具备 PDF 区域截图能力的 skill。 |
| TradingView News | `skills/tradingview-news` | 按渐进式披露获取并总结 TradingView 全市场新闻流：先给精简标题列表，按需再取单篇全文，并遵守每篇文章的访问级别；内置一个只用标准库的 Python CLI。 |
| Verify with Citations | `skills/verify-with-citations` | 核实、查证类任务的引用格式：逐字引原文、署名作者或机构、标题用 Markdown 链接并附章节层级，超过 3 项时补来源清单表。 |

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

TradingView News skill 包含一个只用 Python 标准库的 CLI（Python 3.9+，无需安装任何包）。运行环境必须能访问 `*.tradingview.com`；在 Claude 云端环境中，需要在 Settings → Capabilities → Allow network egress → Additional allowed domains 里加入这个域名。

```bash
python3 skills/tradingview-news/scripts/tv_news.py list            # 第一级：与网页 News Flow 默认状态相同的新闻流
python3 skills/tradingview-news/scripts/tv_news.py read '#3' '#7'  # 第二级：展开上一次列表中的文章
python3 skills/tradingview-news/scripts/tv_news.py filters         # 查看可用的筛选取值
```

不带参数时，`list` 与网页 News Flow 页面的默认状态一致：只带语言筛选，发一次请求，输出返回的全部条目。筛选规则也与网页一致：不同筛选项之间是"并且"，同一筛选项的多个值之间是"或者"。服务端每次请求最多返回 200 条且不允许翻页（登录后也一样），所以每次列表都会报告每路查询的覆盖时间；加 `--split` 可按筛选值分别请求，覆盖更长时间。只有访问级别允许的文章才输出正文：预览级别只给摘要，仅标题级别只给标题和订阅提示。

## Verify with Citations

纯文档 skill，没有脚本。用户要求核实、查证、确认某个说法时，用统一的引用格式作答：先给结论，再给引用块——逐字引原文（不在引号内翻译）、加粗真正定案的那一句、署名作者或机构、标题用 Markdown 链接并在链接后附章节层级（`§4`、`Table 4`、`p. 7`），整体放在一个斜体 span 里。引用超过 3 项时，在末尾补一张来源清单表；来源立场不一致时按立场分组，查过但不支持结论的来源也一并列出。

硬约束是不编造引文、URL、作者和章节号，无法取得原文时宁可不引；取不到的信息就地标注（如"页面未声明所属机构""仅见摘要"）。

## 安全

环境变量可以避免把 secret 写进源码或 shell 命令历史，但它不是强安全边界；任何能在同一环境里执行任意 shell 命令的运行时，理论上都可能读取这些环境变量。

如果真实 Google Gemini API key 不应暴露给 CLI 运行时，建议使用本地 proxy 模式。真实 Google key 保存在本地 proxy 内部，CLI 只发送风险较低的本地 proxy key。

## License

MIT
