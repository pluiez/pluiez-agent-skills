#!/usr/bin/env python3
"""TradingView News Flow CLI: compact headline lists and on-demand full stories.

Subcommands:
  list     Fetch the market-wide news flow with filters, merge, dedupe and print
           one compact line per story (level 1).
  read     Print the text of selected stories by list index (#3) or story id,
           respecting each story's access level (level 2).
  filters  Print the filter ids and values the news flow accepts.

Standard library only. Results go to stdout; progress and errors go to stderr.
Exit status: 0 ok, 1 some requests failed, 2 bad input, 3 network blocked.
"""

import argparse
import itertools
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from zoneinfo import ZoneInfo

FLOW_URL = "https://news-mediator.tradingview.com/public/news-flow/v2/news"
META_URL = "https://news-mediator.tradingview.com/public/news-flow/v1/meta"
STORY_URL = "https://news-headlines.tradingview.com/v3/story"
SITE = "https://www.tradingview.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")

# The server returns at most this many items per request and refuses
# pagination (cursor / start_date / end_date) for every client we tested.
PAGE_CAP = 200
MAX_REQUESTS = 30
# Transient failures (connection resets, 429, 5xx) are retried this many
# times with a growing delay before a request counts as failed.
RETRIES = 2
DEFAULT_TZ = "Asia/Shanghai"
# A #N reference into a list cache older than this gets a warning, since
# another session may have overwritten the shared cache in the meantime.
CACHE_STALE_SECS = 3600

# CLI option -> news-flow filter id. Like the web page, the server ANDs
# different filters and ORs the values of one filter, which are sent as one
# comma-joined, sorted list ("filter=provider:dow-jones,reuters"). Filters
# must also be sent in sorted order, or the server answers 400.
FILTER_OPTS = {
    "market": "market",
    "country": "market_country",
    "sector": "sector",
    "corp": "corp_activity",
    "econ": "economic_category",
    "crypto": "crypto_sections",
    "provider": "provider",
    "priority": "priority",
    "symbol": "symbol",
}

# With no preset and no filter, the CLI sends exactly what the web News Flow
# page sends by default: the language filter only, one request, and prints
# every item returned. Presets are optional shortcuts; each one is a list of
# query groups whose results are merged. "important" alone is ~98%
# TradingView's own auto-generated items (analyst rating blurbs and the
# like), so "wires" takes TradingView's curated top stories plus the
# "important" items of the two big newswires.
PRESETS = {
    "wires": [
        {"priority": ["top_stories"]},
        {"priority": ["important"], "provider": ["reuters", "dow-jones"]},
    ],
    "top": [{"priority": ["top_stories"]}],
    "important": [{"priority": ["important"]}],
    "us-important": [{"market": ["stock"], "market_country": ["US"], "priority": ["important"]}],
    "us-stocks": [{"market": ["stock"], "market_country": ["US"]}],
    "macro": [{"market": ["economic"]}],
    "crypto": [{"market": ["crypto"]}],
}

ACCESS_LABEL = {None: "全文", "preview": "预览", "headline": "仅标题", "provider": "受限"}


class NetworkBlocked(Exception):
    pass


class ApiError(Exception):
    pass


class _Transient(Exception):
    """A failure worth retrying: connection reset, timeout, 429 or 5xx."""


def log(msg):
    print(msg, file=sys.stderr)


def get_tz(name):
    try:
        return ZoneInfo(name)
    except Exception:
        # Without a tz database (e.g. Windows without the tzdata package) the
        # default zone is still usable, because Shanghai has no DST.
        if name == DEFAULT_TZ:
            return timezone(timedelta(hours=8), "GMT+8")
        raise ValueError(f"无法识别的时区：{name}（应为 IANA 时区名，如 America/New_York）") from None


def tz_label(dt):
    off = dt.utcoffset() or timedelta(0)
    hours = int(off.total_seconds() // 3600)
    mins = int(abs(off.total_seconds()) % 3600 // 60)
    return f"GMT{hours:+d}" + (f":{mins:02d}" if mins else "")


def http_json_once(url, timeout):
    """One attempt. Returns the parsed body, or raises NetworkBlocked,
    ApiError (permanent) or _Transient (worth retrying)."""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Origin": SITE,
        "Referer": SITE + "/",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        try:
            msg = json.loads(body).get("message", body)
        except Exception:
            msg = body
        err = f"HTTP {e.code}: {msg}"
        if e.code == 429 or e.code >= 500:
            raise _Transient(err) from None
        raise ApiError(err) from None
    except urllib.error.URLError as e:
        reason = str(e.reason)
        if "403" in reason or "Tunnel" in reason or "Forbidden" in reason:
            host = urllib.parse.urlparse(url).hostname
            raise NetworkBlocked(host) from None
        raise _Transient(f"network error: {reason}") from None
    except (OSError, ValueError) as e:  # reset mid-read, timeout, bad JSON
        raise _Transient(f"network error: {e}") from None


def http_json(url, timeout=20):
    for attempt in range(RETRIES + 1):
        try:
            return http_json_once(url, timeout)
        except _Transient as e:
            if attempt == RETRIES:
                raise ApiError(str(e)) from None
            delay = 1.5 * (attempt + 1)
            log(f"  {e}；{delay:g} 秒后重试（{attempt + 1}/{RETRIES}）")
            time.sleep(delay)


def blocked_message(host):
    return (f"error=network_blocked host={host}\n"
            "无法连接 TradingView：当前运行环境的出站网络拦截了这个域名。"
            "在 Claude 网页版 Settings → Capabilities → Allow network egress → "
            "Additional allowed domains 中加入 *.tradingview.com 后重试。")


# ---------------------------------------------------------------- list

def build_query_groups(args):
    """Return ([{filter_id: [values]}, ...], label) before request expansion."""
    explicit = {}
    for opt, fid in FILTER_OPTS.items():
        vals = getattr(args, opt) or []
        vals = [v.strip() for chunk in vals for v in chunk.split(",") if v.strip()]
        if vals:
            explicit[fid] = list(dict.fromkeys(vals))
    if args.preset and explicit:
        raise ValueError("--preset 不能和筛选参数同时使用：预设只是固定的筛选组合，"
                         "需要改条件时直接写出完整的筛选参数（用 filters 查看预设展开后的内容）。")
    if args.preset:
        return [dict(g) for g in PRESETS[args.preset]], f"预设 {args.preset}"
    if explicit:
        return [explicit], "自定义筛选"
    return [{}], "网页默认（仅语言筛选）"


def expand(groups, split):
    """One request per group with comma-joined values (server-side OR), or,
    with split, one request per value combination (each gets its own cap)."""
    out = []
    for g in groups:
        if not split:
            out.append({k: sorted(v) for k, v in g.items()})
            continue
        keys = sorted(g)
        for combo in itertools.product(*(sorted(g[k]) for k in keys)):
            out.append({k: [v] for k, v in zip(keys, combo)})
    seen, uniq = set(), []
    for q in out:
        key = tuple((k, tuple(v)) for k, v in sorted(q.items()))
        if key not in seen:
            seen.add(key)
            uniq.append(q)
    return uniq


def flow_url(query, lang):
    filters = sorted([f"lang:{lang}"] + [f"{k}:{','.join(sorted(v))}" for k, v in query.items()])
    qs = "&".join("filter=" + urllib.parse.quote(f, safe=":") for f in filters)
    return f"{FLOW_URL}?{qs}&client=web&streaming=false"


def query_label(query):
    if not query:
        return "仅语言"
    return " & ".join(f"{k}={','.join(v) if isinstance(v, list) else v}"
                      for k, v in sorted(query.items()))


def provider_of(item):
    p = item.get("provider")
    if isinstance(p, dict):
        return p.get("id") or "", p.get("name") or p.get("id") or ""
    return p or "", item.get("source") or p or ""


def norm_title(t):
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def short_symbols(item, n=4):
    syms = [s.get("symbol", "") for s in item.get("relatedSymbols") or []]
    syms = list(dict.fromkeys(s.split(":", 1)[-1] for s in syms if s))
    extra = len(syms) - n
    return ",".join(syms[:n]) + (f"+{extra}" if extra > 0 else "")


def fmt_short(ts, tz):
    # Presets like wires can reach back months, past New Year; add the year
    # whenever it is not the current one so "12-19" is not read as upcoming.
    dt = datetime.fromtimestamp(ts, tz)
    if dt.year != datetime.now(tz).year:
        return dt.strftime("%Y-%m-%d %H:%M")
    return dt.strftime("%m-%d %H:%M")


def fmt_long(ts, tz):
    dt = datetime.fromtimestamp(ts, tz)
    return dt.strftime("%b %d, %Y, %H:%M ") + tz_label(dt)


def cache_path():
    return os.environ.get("TV_NEWS_CACHE") or os.path.join(
        tempfile.gettempdir(), "tv_news_last_list.json")


def cmd_list(args):
    try:
        tz = get_tz(args.tz)
    except ValueError as e:
        log(f"error=bad_tz {e}")
        return 2
    now = time.time()
    since = now - args.hours * 3600 if args.hours else None
    try:
        pats = [re.compile(k, re.I) for k in args.keyword or []]
    except re.error as e:
        log(f"error=bad_keyword {e}")
        return 2
    try:
        groups, source = build_query_groups(args)
    except ValueError as e:
        log(f"error=bad_args {e}")
        return 2
    queries = expand(groups, args.split)
    if len(queries) > MAX_REQUESTS:
        log(f"error=too_many_requests count={len(queries)} max={MAX_REQUESTS}")
        log("--split 拆出的请求太多，请减少多选的值，或去掉 --split。")
        return 2

    merged, failures, notes = {}, 0, []
    for i, q in enumerate(queries, 1):
        label = query_label(q)
        log(f"[{i}/{len(queries)}] {label}")
        try:
            items = http_json(flow_url(q, args.lang)).get("items") or []
        except NetworkBlocked as e:
            print(blocked_message(str(e)))
            return 3
        except ApiError as e:
            failures += 1
            notes.append(f"# 查询 {i}（{label}）失败：{e}")
            continue
        oldest = min((it["published"] for it in items), default=None)
        # The server sometimes returns slightly fewer than PAGE_CAP items for
        # a full page, so treat anything close to the cap as truncated.
        capped = len(items) >= PAGE_CAP - 10
        if since is None:
            span = (f"，{fmt_short(oldest, tz)} → {fmt_short(max(it['published'] for it in items), tz)}"
                    f"（约 {(now - oldest) / 3600:.1f} 小时）") if items else ""
            cap = "，已达单次上限，更早的新闻未获取" if capped else ""
            notes.append(f"# 查询 {i}（{label}）：{len(items)} 条{span}{cap}")
            kept = items
        else:
            kept = [it for it in items if it.get("published", 0) >= since]
            if capped and oldest is not None and oldest > since:
                notes.append(
                    f"# 查询 {i}（{label}）：{len(items)} 条，只覆盖到 {fmt_short(oldest, tz)}"
                    f"（约 {(now - oldest) / 3600:.1f} 小时），⚠ 窗口内更早的新闻未获取")
            else:
                notes.append(f"# 查询 {i}（{label}）：窗口内 {len(kept)} 条（完整）")
        for it in kept:
            merged.setdefault(it["id"], it)

    rows = sorted(merged.values(), key=lambda x: x.get("published", 0), reverse=True)
    fetched = len(rows)

    # local filters
    if pats:
        rows = [r for r in rows if any(p.search(r.get("title", "")) for p in pats)]
    if args.exclude_provider:
        ex = {e.strip().lower() for chunk in args.exclude_provider for e in chunk.split(",")}
        rows = [r for r in rows if provider_of(r)[0].lower() not in ex
                and provider_of(r)[1].lower() not in ex]
    if args.full_only:
        rows = [r for r in rows if r.get("permission") is None]
    if args.flash_only:
        rows = [r for r in rows if r.get("is_flash")]
    dup = 0
    if args.dedupe_titles:  # same headline from several feeds: keep the newest
        seen, deduped = set(), []
        for r in rows:
            key = norm_title(r.get("title", ""))
            if key and key in seen:
                dup += 1
                continue
            seen.add(key)
            deduped.append(r)
        rows = deduped
    total = len(rows)
    if args.limit and args.limit > 0:
        rows = rows[:args.limit]

    tzname = tz_label(datetime.fromtimestamp(now, tz))
    window = (f"最近 {args.hours:g} 小时（{fmt_short(since, tz)} → {fmt_short(now, tz)}）"
              if since is not None else "不限时间（与网页一致，取每次请求返回的全部条目）")
    print(f"# TradingView News Flow | {source} | 语言 {args.lang} | {window} | 时区 {tzname}")
    for n in notes:
        print(n)
    shown = f"，显示前 {len(rows)} 条" if len(rows) < total else ""
    dropped = fetched - total - dup
    detail = [f"{'窗口内' if since is not None else '共'} {fetched} 条（已按 id 去重）"]
    if dup:
        detail.append(f"合并同标题 {dup} 条")
    if dropped:
        detail.append(f"本地筛选去掉 {dropped} 条")
    print(f"# 合计 {total} 条：{'，'.join(detail)}{shown}；"
          f"格式：序号 时间 | 来源 | 标题 | 相关标的 | 访问级别 [| 标记]")

    cache = {"created": int(now), "items": []}
    for idx, r in enumerate(rows, 1):
        pid, pname = provider_of(r)
        title = (r.get("title") or "").replace("|", "/").strip()
        flags = []  # urgency=1 tags nearly every "important" item, so it is not shown
        if r.get("is_flash"):
            flags.append("快讯")
        if r.get("isExclusive"):
            flags.append("独家")
        parts = [f"#{idx} {fmt_short(r['published'], tz)}", pname, title,
                 short_symbols(r) or "-", ACCESS_LABEL.get(r.get("permission"), "受限")]
        if flags:
            parts.append("/".join(flags))
        print(" | ".join(parts))
        cache["items"].append({
            "id": r["id"], "title": r.get("title"), "provider": pname,
            "published": r.get("published"), "permission": r.get("permission"),
            "storyPath": r.get("storyPath"),
        })
    try:
        with open(cache_path(), "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
    except OSError as e:
        log(f"warning: could not write list cache: {e}")
    if total == 0:
        print("# 窗口内没有符合条件的新闻。")
    return 1 if failures else 0


# ---------------------------------------------------------------- read

BLOCK_TYPES = {"p", "list", "table", "twitter", "h1", "h2", "h3", "h4", "h5", "h6",
               "blockquote", "quote"}
DROP_TYPES = {"disclaimer", "news-image", "image"}


def inline_text(node):
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(inline_text(c) for c in node)
    if not isinstance(node, dict):
        return ""
    t = node.get("type")
    params = node.get("params") or {}
    if t in DROP_TYPES:
        return ""
    if t == "symbol":
        return params.get("text") or params.get("symbol") or ""
    if t == "url":
        text = params.get("linkText") or inline_text(node.get("children", []))
        return text or params.get("url", "")
    return inline_text(node.get("children", []))


def ast_to_text(node):
    """Convert TradingView's story AST to plain text paragraphs."""
    blocks = []

    def walk(n):
        if isinstance(n, str):
            if n.strip():
                blocks.append(n.strip())
            return
        if isinstance(n, list):
            for c in n:
                walk(c)
            return
        if not isinstance(n, dict):
            return
        t = n.get("type")
        if t in DROP_TYPES:
            return
        if t == "list":
            lines = [f"- {inline_text(c).strip()}" for c in n.get("children", [])
                     if inline_text(c).strip()]
            if lines:
                blocks.append("\n".join(lines))
            return
        if t == "table":
            rows = []

            def collect(x):
                if isinstance(x, dict):
                    if x.get("type") == "table-row":
                        cells = [inline_text(c).strip().replace("|", "/")
                                 for c in x.get("children", [])]
                        rows.append("| " + " | ".join(cells) + " |")
                    else:
                        for c in x.get("children", []):
                            collect(c)
            collect(n)
            if rows:
                blocks.append("\n".join(rows))
            return
        if t == "twitter":
            p = n.get("params") or {}
            body = " ".join(inline_text(c).strip() for c in n.get("children", []))
            blocks.append(f"[推文 @{p.get('username', '')}] {body}".strip())
            return
        if t in BLOCK_TYPES:
            text = inline_text(n).strip()
            if text:
                blocks.append(text)
            return
        if t == "root" or n.get("children"):
            children = n.get("children", [])
            if t != "root" and all(isinstance(c, str) or (isinstance(c, dict) and c.get("type") not in BLOCK_TYPES | {"list", "table"}) for c in children):
                text = inline_text(n).strip()
                if text:
                    blocks.append(text)
                return
            for c in children:
                walk(c)

    walk(node)
    return "\n\n".join(blocks)


def resolve_refs(refs):
    cache = None
    out = []
    for ref in refs:
        m = re.fullmatch(r"#?(\d+)", ref.strip())
        if m:
            if cache is None:
                try:
                    with open(cache_path(), encoding="utf-8") as f:
                        cache = json.load(f)
                except (OSError, ValueError):
                    raise ValueError("找不到上一次 list 的结果，请先运行 list，或直接传入文章 id。")
                age = time.time() - cache.get("created", 0)
                if age > CACHE_STALE_SECS:
                    log(f"warning: 上一次 list 的结果是 {age / 3600:.1f} 小时前生成的，"
                        "缓存文件可能已被其他会话覆盖；请核对输出的标题，或重新运行 list。")
            idx = int(m.group(1))
            items = cache.get("items", [])
            if not 1 <= idx <= len(items):
                raise ValueError(f"序号 #{idx} 超出上一次列表范围（共 {len(items)} 条）。")
            out.append((f"#{idx}", items[idx - 1]["id"]))
        else:
            out.append((ref.strip(), ref.strip()))
    return out


def cmd_read(args):
    try:
        tz = get_tz(args.tz)
    except ValueError as e:
        log(f"error=bad_tz {e}")
        return 2
    try:
        refs = resolve_refs(args.refs)
    except ValueError as e:
        log(f"error=bad_ref {e}")
        return 2
    if len(refs) > args.max_stories:
        log(f"error=too_many_stories count={len(refs)} max={args.max_stories}")
        log("一次展开的文章太多，请分批，或用 --max-stories 调大上限。")
        return 2

    failures = 0
    for n, (label, sid) in enumerate(refs):
        if n:
            print("\n" + "=" * 60 + "\n")
        url = f"{STORY_URL}?id={urllib.parse.quote(sid, safe='')}&lang={args.lang}"
        try:
            s = http_json(url)
        except NetworkBlocked as e:
            print(blocked_message(str(e)))
            return 3
        except ApiError as e:
            failures += 1
            print(f"## {label}\nstatus=error id={sid}\n获取失败：{e}")
            continue

        perm = s.get("permission")
        access = ACCESS_LABEL.get(perm, "受限")
        prov = s.get("provider")
        pname = prov.get("name") if isinstance(prov, dict) else (prov or "")
        syms = ", ".join(x.get("symbol", "") for x in s.get("relatedSymbols") or [])
        read_time = s.get("read_time") or 0
        link = SITE + s["storyPath"] if s.get("storyPath") else ""

        print(f"## {label} {s.get('title', '').strip()}")
        meta = [f"来源: {pname}"]
        if s.get("published"):
            meta.append(f"时间: {fmt_long(s['published'], tz)}")
        if syms:
            meta.append(f"标的: {syms}")
        meta.append(f"访问级别: {access}")
        if read_time:
            meta.append(f"预计阅读 {max(1, round(read_time / 60))} 分钟")
        print(" | ".join(meta))
        if link:
            print(f"链接: {link}")
        print("---")

        if perm in ("headline", "provider"):
            print(f"status=restricted permission={perm}")
            print("这篇文章需要 TradingView 相应的订阅权限才能阅读全文；当前（未登录）只能看到标题。"
                  "如需阅读，请在 TradingView 用有权限的账户打开上面的链接。")
            continue
        if perm == "preview":
            desc = (s.get("shortDescription") or "").strip()
            print("status=preview permission=preview")
            print("这篇文章当前只开放预览，以下为摘要，并非全文：")
            print((desc + ("…" if len(desc) >= 290 else "")) if desc else "（没有可用的摘要）")
            continue
        if perm is not None:
            print(f"status=restricted permission={perm}")
            print("这篇文章的访问级别无法识别，按受限处理，不输出正文。")
            continue

        text = ast_to_text(s.get("astDescription")) if s.get("astDescription") else ""
        if not text:
            desc = (s.get("shortDescription") or "").strip()
            print("status=no_body")
            print("这条是纯标题快讯，没有正文。" + (f"\n摘要：{desc}" if desc else ""))
            continue
        truncated = len(text) > args.max_chars
        if truncated:
            text = text[:args.max_chars].rsplit("\n", 1)[0]
        print("status=full")
        print(text)
        notes = []
        if truncated:
            notes.append(f"[已截断：正文超过 {args.max_chars} 字符，可用 --max-chars 调大]")
        expected = read_time * 20  # ~200 wpm, ~6 chars/word, padded low
        if read_time >= 30 and len(text) < expected * 0.5 and not truncated:
            notes.append("[提示：正文长度明显短于预计阅读时长，内容可能不完整]")
        for x in notes:
            print(x)
    return 1 if failures else 0


# ---------------------------------------------------------------- filters

def cmd_filters(args):
    url = f"{META_URL}?lang={args.lang}&user_prostatus=non_pro"
    try:
        meta = http_json(url)
    except NetworkBlocked as e:
        print(blocked_message(str(e)))
        return 3
    except ApiError as e:
        log(f"error=api {e}")
        return 1
    opt_of = {v: k for k, v in FILTER_OPTS.items()}
    print("# 每个筛选项：CLI 参数 (服务端 id)：可选值（括号内为显示名）")
    print("# 不同筛选项之间是\"并且\"，同一筛选项的多个值之间是\"或者\"（与网页端一致）。")
    for f in meta.get("filters", []):
        fid = f.get("id")
        if fid == "lang":
            vals = [v.get("id") for v in (f.get("constraints") or {}).get("values", [])]
            print(f"--lang (lang)：{', '.join(vals)}")
            continue
        opt = opt_of.get(fid)
        if not opt:
            continue
        vals = (f.get("constraints") or {}).get("values") or []
        if vals:
            shown = ", ".join(v["id"] if v.get("title", "").lower() == v["id"].lower()
                              else f"{v['id']}（{v.get('title')}）" for v in vals)
        elif fid == "market_country":
            shown = "ISO 3166-1 两位国家代码，如 US, CN, JP, KR, GB, DE, HK, TW, IN"
        elif fid == "symbol":
            shown = "交易所:代码，如 NASDAQ:NVDA、NYSE:TSM、KRX:005930、TSE:6981"
        else:
            shown = "（无固定取值）"
        print(f"--{opt} ({fid})：{shown}")
    print("# 预设（多路查询合并）：" + "; ".join(
        f"{k} = " + " ∪ ".join(f"({query_label(q)})" for q in v) for k, v in PRESETS.items()))
    return 0


# ---------------------------------------------------------------- main

def positive(kind):
    def parse(text):
        try:
            v = kind(text)
        except ValueError:
            raise argparse.ArgumentTypeError(f"不是有效的数字：{text}") from None
        if v <= 0:
            raise argparse.ArgumentTypeError(f"必须大于 0：{text}")
        return v
    return parse


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--tz", default=os.environ.get("TV_NEWS_TZ", DEFAULT_TZ),
                        help="display time zone (default Asia/Shanghai, i.e. GMT+8)")
    common.add_argument("--lang", default="en", help="news language (default en)")
    sub = p.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("list", parents=[common], help="level 1: compact headline list")
    pl.add_argument("--preset", choices=sorted(PRESETS),
                    help="optional query preset; cannot be combined with filter options")
    pl.add_argument("--hours", type=positive(float), default=None,
                    help="keep only the last N hours (default: no time filter, like the web page)")
    for opt, fid in FILTER_OPTS.items():
        pl.add_argument(f"--{opt}", nargs="+", metavar="V",
                        help=f"news-flow filter '{fid}' (several values = OR)")
    pl.add_argument("--split", action="store_true",
                    help="one request per filter value (each gets its own 200-item cap) "
                         "instead of one comma-joined request")
    pl.add_argument("--dedupe-titles", action="store_true",
                    help="merge items with the same headline (off by default, like the web page)")
    pl.add_argument("--keyword", nargs="+", metavar="RE", help="keep titles matching any regex")
    pl.add_argument("--exclude-provider", nargs="+", metavar="P", help="drop these providers")
    pl.add_argument("--full-only", action="store_true", help="only stories readable in full")
    pl.add_argument("--flash-only", action="store_true", help="only flash (breaking) items")
    pl.add_argument("--limit", type=positive(int), default=0, help="max lines to print (default all)")
    pl.set_defaults(func=cmd_list)

    pr = sub.add_parser("read", parents=[common], help="level 2: story text by #index or id")
    pr.add_argument("refs", nargs="+", help="#N from the last list, or a story id")
    pr.add_argument("--max-chars", type=positive(int), default=8000, help="per-story text cap")
    pr.add_argument("--max-stories", type=positive(int), default=5, help="stories per call")
    pr.set_defaults(func=cmd_read)

    pf = sub.add_parser("filters", parents=[common], help="print accepted filter values")
    pf.set_defaults(func=cmd_filters)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    try:
        code = main()
        sys.stdout.flush()
    except BrokenPipeError:  # output piped into head etc.; not a failure
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        code = 0
    sys.exit(code)
