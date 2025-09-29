#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio
import os

from checker.async_check import check_urls
from config import (
    DAILY_INCREMENT,
    FAIL_THRESHOLD,
    FILENAME_IN_GIST,
    HIST_PATH,
    KEYWORDS,
    MAX_WORKERS,
    OUT_FILE,
    get_gist_id,
    get_gist_token,
    get_github_token,
)
from fetchers.gitee import collect_links as ge_collect
from fetchers.github import collect_links as gh_collect
from fetchers.gitlab import collect_links as gl_collect
from fetchers.utils import http_get
from filters.deduper import choose_best
from filters.validator import is_valid_subscription
from storage.gist import update_gist
from storage.history import ensure_increment


def fetch_all_candidates():
    token = get_github_token()
    # GitHub
    gh = gh_collect(KEYWORDS, per_key=20, token=token)
    # GitLab
    gl = gl_collect(KEYWORDS, per_key=15)
    # Gitee（当前占位，返回空列表）
    ge = ge_collect(KEYWORDS, per_key=10)

    urls = list(set(gh + gl + ge))
    return urls


def validate_contents(urls: list[str]) -> list[str]:
    ok = []
    for u in urls:
        try:
            r = http_get(u, timeout=12)
            if r.status_code < 400:
                # 先基于 Content-Type 做快速排除，减少对 HTML 登录页/错误页的误判
                ct = (r.headers.get("Content-Type") or "").lower()
                body = r.text or ""
                if (
                    "text/html" in ct
                    and "proxies" not in body.lower()
                    and not any(
                        p in body.lower()
                        for p in (
                            "vmess://",
                            "vless://",
                            "trojan://",
                            "ss://",
                            "ssr://",
                        )
                    )
                ):
                    continue

                if is_valid_subscription(u, body):
                    ok.append(u)
        except Exception:
            pass
    return ok


def save_text(path: str, text: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


async def main():
    # 1) 搜索源
    candidates = fetch_all_candidates()
    # 2) 发布者去重（yaml>txt>sub）
    best = choose_best(candidates)
    # 3) 异步连通性检测
    reachable = await check_urls(best, concurrency=MAX_WORKERS)
    # 4) 内容校验（真订阅）
    valid = validate_contents(reachable)
    # 5) 每日+10 / 候补 / 淘汰
    final_list = ensure_increment(valid, HIST_PATH, DAILY_INCREMENT, FAIL_THRESHOLD)
    # 6) 输出 + Gist
    save_text(OUT_FILE, "\n".join(final_list))
    code = update_gist(
        get_gist_id(), get_gist_token(), FILENAME_IN_GIST, "\n".join(final_list)
    )
    print(f"[DONE] {len(final_list)} saved → {OUT_FILE} ; Gist={code}")


if __name__ == "__main__":
    asyncio.run(main())
