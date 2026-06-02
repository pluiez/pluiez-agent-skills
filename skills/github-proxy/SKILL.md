---
name: github-proxy
description: Use when GitHub (github.com, raw.githubusercontent.com, api.github.com) is timing out, refusing connection, or returning empty responses. Prefix URLs with https://gh-proxy.org/. For install scripts (`curl ... | bash`), embedded URLs need sed rewrite, not just outer-URL proxying.
---

# GitHub Proxy (gh-proxy.org)

Prefix any GitHub URL with `https://gh-proxy.org/`:

```
https://github.com/X/Y.git → https://gh-proxy.org/https://github.com/X/Y.git
```

Verify before relying on it (proxy can 404 even when GitHub serves):

```sh
curl -sI -o /dev/null -w '%{http_code}\n' "https://gh-proxy.org/<URL>"
```

## Persistent git rewrite

```sh
git config --global url."https://gh-proxy.org/https://github.com/".insteadOf "https://github.com/"
```

Undo with `--unset`. SSH (`git@github.com:...`) can't be proxied — switch the remote to HTTPS first.

## Install scripts with embedded GitHub URLs

Outer-URL proxying isn't enough — the script's internal calls still hit github.com directly. Download → rewrite → run:

```sh
curl -fsSL -o /tmp/install "https://gh-proxy.org/<RAW_URL>"
sed -i \
  -e 's|https://api.github.com|https://gh-proxy.org/https://api.github.com|g' \
  -e 's|https://github.com|https://gh-proxy.org/https://github.com|g' \
  -e 's|https://raw.githubusercontent.com|https://gh-proxy.org/https://raw.githubusercontent.com|g' \
  /tmp/install
grep -nE 'https?://' /tmp/install   # show the user before running
bash /tmp/install <args>
```

## Limitations

- **SSH, git-lfs, `gh` CLI** — not proxyable; suggest VPN or HTTPS remote.
- **PAT / auth** — proxy may strip `Authorization`; test first.
- **404 from proxy** — could be the upstream's bad asset filename, not a proxy issue. Check via `.../api.github.com/repos/<owner>/<repo>/releases/latest`.

## Mirrors (same prefix pattern, all under gh-proxy.org)

Default: `https://gh-proxy.org/`. Variants if the default is slow or routing-broken:

- `https://v4.gh-proxy.org/` — IPv4 only
- `https://v6.gh-proxy.org/` — IPv6 only
- `https://cdn.gh-proxy.org/` — CDN-fronted
