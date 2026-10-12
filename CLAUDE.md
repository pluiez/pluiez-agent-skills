# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a personal agent skills library — a collection of reusable skill folders that agents and editors can load. The repo is intentionally runtime-neutral: it provides skill folders and bundled resources only, with no build system or test runner.

## Repository Structure

Each skill lives under `skills/<skill-name>/` and contains:
- `SKILL.md` — the skill definition loaded by the agent (frontmatter name/description + usage instructions)
- `scripts/` — self-contained shell scripts bundled with the skill
- `references/` — supplemental reference docs consulted only when needed (not loaded by default)

## Adding a New Skill

1. Create `skills/<skill-name>/SKILL.md` with YAML frontmatter (`name`, `description`) and usage instructions.
2. Add any bundled scripts to `skills/<skill-name>/scripts/`.
3. Add supplementary reference docs to `skills/<skill-name>/references/` if needed.
4. Add an entry to the skills table in `README.md` and `README.zh-CN.md`.
5. Add a `## <skill-name> Skill` section to this CLAUDE.md summarizing key commands, dependencies, env vars, and when to read on-demand references.

## Skill Authoring Conventions

- `SKILL.md` should include a **Workflow** section with numbered steps and a **Common Commands** section with ready-to-run examples.
- Reference docs (`references/`) should be self-contained and consulted lazily — the `SKILL.md` should explicitly list the conditions under which the agent should read them.
- Scripts print human-readable progress to **stderr** and machine-readable results to **stdout** (e.g., `key=value` lines).
- Environment variables are used for secrets and endpoint configuration. Default values must be safe to use in local-only scenarios.
- For security-sensitive skills, document the security model and key isolation tradeoffs explicitly.

## conventional-commits Skill

Pure-documentation skill (no `scripts/`, no `references/`). Spec reference for writing or amending git commit messages in this repo.

Format: `<type>[(scope)][!]: <description>`. Common types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`. Use `!` or a `BREAKING CHANGE:` footer for breaking changes.

House rule: do NOT append `Co-Authored-By:` or other AI/tool-attribution trailers unless the user explicitly asks.

## gemini-image-cli Skill

The bundled script requires `curl`, `jq`, and `base64`.

```bash
# Generate an image (auto-selects local proxy, falls back to Google)
skills/gemini-image-cli/scripts/gemini-image.sh "prompt text"

# Print full CLI help
skills/gemini-image-cli/scripts/gemini-image.sh --help
```

Environment variables:
- `GEMINI_LOCAL_ENDPOINT` — local proxy base origin (default: `http://127.0.0.1:8000`)
- `GEMINI_LOCAL_API_KEY` — local proxy key (default: `sk-123456`)
- `GEMINI_API_KEY` — required only when using `--provider google`

Provider auto-selection: checks local endpoint first; falls back to Google if unreachable. Use `--provider local` or `--provider google` to force one.

Read `skills/gemini-image-cli/references/behavior.md` only when choosing non-default models, configuring the local proxy, troubleshooting failures, or modifying the CLI.

## github-proxy Skill

Pure-documentation skill (no `scripts/`, no `references/`). Apply when github.com, `raw.githubusercontent.com`, or `api.github.com` are timing out, refusing connections, or returning empty responses while working in this repo.

Core pattern — prefix any GitHub URL with `https://gh-proxy.org/`:

```sh
git clone https://gh-proxy.org/https://github.com/<owner>/<repo>.git
```

Persistent git rewrite (undo with `--unset`):

```sh
git config --global url."https://gh-proxy.org/https://github.com/".insteadOf "https://github.com/"
```

For `curl ... | bash` install scripts, download → `sed`-rewrite embedded `github.com` / `api.github.com` / `raw.githubusercontent.com` URLs → run. Outer-URL proxying alone leaves the script's internal calls hitting GitHub directly.

Limitations: SSH remotes, `gh` CLI, and git-lfs aren't proxyable; PATs may be stripped by the proxy. Mirrors `v4.gh-proxy.org` / `v6.gh-proxy.org` / `cdn.gh-proxy.org` use the same prefix pattern.

## pdf-region-crop Skill

The bundled script requires Python 3.9+ and PyMuPDF (`pip install pymupdf`). No env vars, no `references/`.

```bash
# 1. render pages (+ page text, draft boxes) into a new temp dir, e.g. /tmp/pdf-regions-XXXX
python skills/pdf-region-crop/scripts/pdf_regions.py prepare paper.pdf [--pages 1-12] [--work-dir DIR]

# zoom into part of a page to check a boundary
python skills/pdf-region-crop/scripts/pdf_regions.py render paper.pdf 6 --rect 0.1 0.05 0.9 0.3 --scale 4

# 3. crop every region in regions.json into --out, plus manifest.json there
python skills/pdf-region-crop/scripts/pdf_regions.py crop paper.pdf --regions regions.json --out assets
```

Coordinates are normalised `[fx0, fy0, fx1, fy1]` in 0..1 of the page as rendered (rotation applied, origin top-left, y down). This is the only geometry mode, and the viewing zoom never changes it. The default crop scale is 3. Exit status: 0 = ok, 1 = some regions failed, 2 = bad input. The manifest stores the PDF file name and sha256, never machine paths.

## paper-zh-translation Skill

Pure-documentation skill written in Chinese, with no `scripts/`. It depends on a PDF region-capture capability, described by what it must do, never by skill name, so any equivalent skill can satisfy it. If no such skill is available, it must stop and tell the user. It must never write ad-hoc cropping code or fall back to full-page screenshots.

Output is a package next to the PDF: `<arXiv ID+version> <short name>/`, or `<short name>/` when no arXiv ID can be confirmed from the PDF. The package contains the original-text transcription `<PDF stem>.md`, the translation `<PDF stem>.zh-CN.md`, and `assets/` shared by both. The two Markdown files mirror each other section by section, and the translation is written from the checked transcription. Non-image files written into `assets/` by the capture tool are allowed; the skill never names them.

All math uses standard Markdown math syntax: `$...$` inline (including single variables and symbols), `$$...$$` on their own lines for display, `aligned`/`cases` inside one `$$` block for multi-line formulas, and `\tag{N}` to keep original equation numbers. No `\(...\)`/`\[...\]`, Unicode math characters, or images in place of formulas.

Read `skills/paper-zh-translation/references/revising.md` only when the target package already exists, when revising or correcting an existing translation, or when translating a different version of the same paper.

## verify-with-citations Skill

Pure-documentation skill (no `scripts/`, no `references/`). Applies when the user asks to verify, fact-check, confirm, or find authoritative backing for a claim — in English or Chinese ("核实", "查证", "确认一下", "出处是哪里").

Citation block format: blockquote with the verbatim quote, a blank quote line, then `—— <Author or Org>, *[Title](URL) §Section*`. The decisive clause is bolded; the title link and the section path sit inside one italic span. Quotes are never translated inside the quote marks.

Past 3 sources, a summary table (`Source | Author / Org | Key passage`) follows the prose, grouped by stance when sources disagree.

Hard constraints: never fabricate a quote, URL, author, or section number; mark unconfirmed details in place; separate quoted text from interpretation of it; date-stamp network sources that can change.
