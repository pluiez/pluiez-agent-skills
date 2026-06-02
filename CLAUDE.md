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
