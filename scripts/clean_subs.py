#!/usr/bin/env python3
"""清理并规范化 output/subs_latest.txt
- 去除 proxy 包装（取内部 http(s) 链接）
- 将 github.com/.../raw/... 映射为 raw.githubusercontent.com 的 canonical 形式
- 按发布者/基础路径去重（因缺少 owner 信息，仅按 base 去重），优先保留 .txt 或 host 优先级
- 并发执行 HEAD（回退到 GET）校验：剔除非 2xx 或 content-type 明显非文本的 URL
- 备份原文件，写回清理后的 output/subs_latest.txt，并把被剔除的记录写到 output/subs_removed.txt
"""

import concurrent.futures
import os
import sys
from urllib.parse import urlparse

try:
    from filters.extract import normalize_url
except Exception:
    def normalize_url(u):
        return (u or "").strip()

import requests

INPUT = "output/subs_latest.txt"
BACKUP = "output/subs_latest.txt.bak"
REMOVED = "output/subs_removed.txt"

HOST_PRIORITY = [
    "raw.githubusercontent.com",
    "cdn.jsdelivr.net",
    "raw.fastgit.org",
    "ghproxy.net",
    "proxy.v2gh.com",
    "github.com",
]


def canonicalize_url(url: str) -> str:
    if not url:
        return url
    s = url.strip()
    last_http = max(s.rfind("http://"), s.rfind("https://"))
    if last_http > 0:
        return canonicalize_url(s[last_http:])
    try:
        p = urlparse(s)
        host = (p.netloc or "").lower()
        path = p.path or ""
        if host == "github.com" and "/raw/" in path:
            new_path = path.replace("/raw/refs/heads/", "/")
            new_path = new_path.replace("/raw/refs/", "/")
            new_path = new_path.replace("/raw/", "/")
            return f"https://raw.githubusercontent.com{new_path}"
    except Exception:
        pass
    return s


def strip_known_ext(u: str) -> str:
    low = u.lower()
    for ext in (".yaml", ".yml", ".txt"):
        if low.endswith(ext):
            return u[: -len(ext)]
    return u


def host_rank(u: str) -> int:
    try:
        h = urlparse(u).netloc.lower()
    except Exception:
        h = ""
    for idx, name in enumerate(HOST_PRIORITY):
        if name in h:
            return idx
    return len(HOST_PRIORITY)


def head_check_urls(urls, concurrency=12, timeout=15):
    allowed_text_indicators = ("text", "json", "yaml", "xml", "plain", "javascript", "x-yaml")
    disallow_prefix = ("image/", "video/", "audio/")
    session = requests.Session()
    session.headers.update({"User-Agent": "sub-hunter/clean/1.0"})

    ok_list = []
    removed = []

    def _check(u):
        try:
            r = session.head(u, allow_redirects=True, timeout=timeout)
        except Exception:
            try:
                r = session.get(u, allow_redirects=True, stream=True, timeout=timeout)
            except Exception as e:
                return (u, False, f"network:{e}")
        code = getattr(r, "status_code", 0)
        if code < 200 or code >= 300:
            return (u, False, f"status:{code}")
        ctype = (r.headers.get("content-type") or "").lower()
        if ctype:
            if any(ctype.startswith(p) for p in disallow_prefix):
                return (u, False, f"ctype_disallowed:{ctype}")
            if not any(k in ctype for k in allowed_text_indicators):
                return (u, False, f"ctype_nontext:{ctype}")
        return (u, True, f"ok:{code}:{ctype}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as ex:
        futs = {ex.submit(_check, u): u for u in urls}
        for fut in concurrent.futures.as_completed(futs):
            try:
                u, ok, reason = fut.result()
            except Exception as e:
                ok = False
                u = futs.get(fut, "<unknown>")
                reason = f"exception:{e}"
            if ok:
                ok_list.append(u)
            else:
                removed.append((u, reason))
    return ok_list, removed


def main():
    if not os.path.exists(INPUT):
        print("input file not found:", INPUT)
        sys.exit(1)
    with open(INPUT, "r", encoding="utf-8") as f:
        raw = [l.strip() for l in f if l.strip()]

    # 规范化并去重（按 canonical base + host 优先）
    canon_map = {u: canonicalize_url(u) for u in raw}
    grouped = {}
    for orig, canon in canon_map.items():
        base = strip_known_ext(canon)
        grouped.setdefault(base, []).append(canon)

    chosen = []
    for base, lst in grouped.items():
        # 保留稳定顺序，优先 .txt
        unique = list(dict.fromkeys(lst))
        if len(unique) == 1:
            chosen.append(unique[0])
            continue
        txts = [u for u in unique if u.lower().endswith('.txt')]
        if txts:
            chosen.append(txts[0])
            continue
        unique.sort(key=lambda u: (host_rank(u), u))
        chosen.append(unique[0])

    # 并发 HEAD 检查
    ok, removed = head_check_urls(chosen, concurrency=16, timeout=15)

    # 写回（先备份）
    os.makedirs("output", exist_ok=True)
    if os.path.exists(BACKUP):
        try:
            os.remove(BACKUP)
        except Exception:
            pass
    os.rename(INPUT, BACKUP)

    with open(INPUT, "w", encoding="utf-8") as f:
        f.write("\n".join(ok))

    with open(REMOVED, "w", encoding="utf-8") as f:
        for u, reason in removed:
            f.write(f"{u}\t{reason}\n")

    print(f"original={len(raw)} chosen_after_grouping={len(chosen)} ok_after_head={len(ok)} removed={len(removed)}")
    if removed:
        print(f"removed sample: {removed[:8]}")


if __name__ == '__main__':
    main()
