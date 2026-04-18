# pluiez-agent-skills

[English](README.md) | [简体中文](README.zh-CN.md)

Personal agent skills and reusable workflows.

This repository is intentionally runtime-neutral. Different agents and editors load skills in different ways, so this repo only provides the skill folders and their bundled resources.

## Skills

| Skill | Path | Description |
| --- | --- | --- |
| Gemini Image CLI | `skills/gemini-image-cli` | Generate and edit images through Gemini-compatible endpoints with a bundled Bash CLI. |

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

## Security

Environment variables avoid storing secrets in source files or shell command history, but they are not a hard security boundary against any runtime that can execute arbitrary shell commands in the same environment.

Use local proxy mode when real Google Gemini API keys should remain outside the CLI runtime. The local proxy can keep the real Google key internally while the CLI sends only a lower-risk local proxy key.

## License

MIT
