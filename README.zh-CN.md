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

## 安全

环境变量可以避免把 secret 写进源码或 shell 命令历史，但它不是强安全边界；任何能在同一环境里执行任意 shell 命令的运行时，理论上都可能读取这些环境变量。

如果真实 Google Gemini API key 不应暴露给 CLI 运行时，建议使用本地 proxy 模式。真实 Google key 保存在本地 proxy 内部，CLI 只发送风险较低的本地 proxy key。

## License

MIT
