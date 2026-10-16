# pluiez-agent-skills

[English](README.md) | [简体中文](README.zh-CN.md)

Personal agent skills and reusable workflows.

This repository is intentionally runtime-neutral. Different agents and editors load skills in different ways, so this repo only provides the skill folders and their bundled resources.

## Skills

| Skill | Path | Description |
| --- | --- | --- |
| Conventional Commits | `skills/conventional-commits` | Conventional Commits 1.0.0 reference for writing or amending git commit messages. |
| Gemini Image CLI | `skills/gemini-image-cli` | Generate and edit images through Gemini-compatible endpoints with a bundled Bash CLI. |
| GitHub Proxy | `skills/github-proxy` | Route GitHub URLs through `gh-proxy.org` when github.com is timing out, refusing connections, or returning empty responses. |
| PDF Region Crop | `skills/pdf-region-crop` | Render PDF pages and capture arbitrary rectangular regions (figures, tables, text fragments, titles, formulas) as high-resolution PNGs cut from the original page, with a bundled Python CLI. |
| Paper zh Translation | `skills/paper-zh-translation` | Translate an academic paper PDF into a complete Simplified Chinese Markdown translation, plus a matching original-text Markdown transcription, with embedded figures and tables; relies on any skill that provides PDF region capture. |
| TradingView News | `skills/tradingview-news` | Search and filter TradingView's News Flow by market, country, sector, provider or symbol: a compact headline list first, story text on demand, with raw API permission values separate from body extraction status; bundled stdlib-only Python CLI. |
| Verify with Citations | `skills/verify-with-citations` | Citation format for verification work: verbatim quote, author/organization attribution, Markdown-linked title with section path, and a source table past 3 sources. |

## Gemini Image CLI

The Gemini Image CLI skill includes a self-contained script:

```bash
skills/gemini-image-cli/scripts/gemini-image.sh "A cute orange kitten sitting on a soft blanket"
```

Print CLI help:

```bash
skills/gemini-image-cli/scripts/gemini-image.sh --help
```

The CLI supports:

- Gemini-compatible local proxy endpoints.
- Google official Gemini endpoints.
- Automatic provider selection: local first, Google fallback.
- MIME-aware image output using `.png`, `.jpg`, or `.webp`.
- Masked key logging and redacted input-image base64 in curl logs.

## PDF Region Crop

The PDF Region Crop skill includes a self-contained Python script that requires PyMuPDF (`pip install pymupdf`):

```bash
python skills/pdf-region-crop/scripts/pdf_regions.py prepare paper.pdf
python skills/pdf-region-crop/scripts/pdf_regions.py crop paper.pdf --regions regions.json --out assets
```

Print CLI help:

```bash
python skills/pdf-region-crop/scripts/pdf_regions.py --help
```

Regions are always normalised boxes `[fx0, fy0, fx1, fy1]` (0..1, origin at the top-left of the page as rendered). They are independent of the viewing zoom and also work on rotated pages.

## Paper zh Translation

Pure-documentation skill, with no scripts. It does not name a cropping skill. Instead, it states the capability it needs: render pages, crop given regions from the original PDF, let the caller choose the output directory and file names, and reject out-of-page boxes. The agent then picks any available skill that provides that capability. If none does, the skill stops and tells the user instead of improvising.

## TradingView News

The TradingView News skill includes a Python 3.9+ standard-library CLI with no package dependencies. The runtime must be able to reach `*.tradingview.com`. Documentation and CLI-generated text use English; news content retains its source language. `--lang` controls news requests, independently of conversation language and time zone settings.

```bash
python3 skills/tradingview-news/scripts/tv_news.py list            # headline list
python3 skills/tradingview-news/scripts/tv_news.py read '#3' '#7'  # selected story bodies
python3 skills/tradingview-news/scripts/tv_news.py filters         # current English API metadata
```

With no options, `list` sends only the news language filter and prints all returned items. Different filters use AND; multiple values of the same filter use OR. Each request has an observed cap of 200 items and the CLI does not paginate; coverage notes flag possible omissions. `--split` requests each filter-value combination separately and merges results by id. Presets such as `wires` are CLI-defined combinations of API filters.

Output preserves raw `permission` values separately from the CLI's `status`. `read` extracts returned body text first and reports `status=full` regardless of permission, retaining `--max-chars` truncation and its notice. Only when no body is extracted does it fall back to `preview`, `restricted`, or `no_body`. These states do not establish a specific subscription requirement or certify source completeness. The legacy `--full-only` list option selects missing/null permission, not verified body availability. Time display still defaults to `Asia/Shanghai`, configurable via `--tz` or `TV_NEWS_TZ`.

## Verify with Citations

Pure-documentation skill, with no scripts. When the user asks to verify or fact-check a claim, the answer leads with the verdict and backs it with citation blocks: the quote verbatim (never translated inside the quote marks), the decisive clause bolded, attribution to an author or organization, and the title as a Markdown link with a section path appended after it (`§4`, `Table 4`, `p. 7`), all inside one italic span. Past 3 sources, a summary table follows the prose, grouped by stance when sources disagree — including sources that were checked but did not support the claim.

The hard constraint is never fabricating a quote, URL, author, or section number: if the text cannot be retrieved, cite nothing and say so. Anything unconfirmed is marked in place (*affiliation not stated on the page*, *abstract only*).

## Security

Environment variables avoid storing secrets in source files or shell command history, but they are not a hard security boundary against any runtime that can execute arbitrary shell commands in the same environment.

Use local proxy mode when real Google Gemini API keys should remain outside the CLI runtime. The local proxy can keep the real Google key internally while the CLI sends only a lower-risk local proxy key.

## License

MIT
