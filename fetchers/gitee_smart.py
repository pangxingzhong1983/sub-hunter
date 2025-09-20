from typing import List
from storage.secure import get_secret
from fetchers.gitee import iter_search_repos as api_iter
from fetchers.gitee_html import html_search_iter as html_iter

def gitee_search_smart(keywords: List[str], max_pages: int = 2) -> List[str]:
    tok = get_secret("sub-hunter","GITEE_TOKEN")
    try:
        items = api_iter(keywords, max_pages=max_pages, token=tok)
    except Exception:
        items = []
    # 从 API 结果提取 URL
    urls = []
    seen = set()
    for it in items:
        u = it.get("html_url") or it.get("url")
        if u and u not in seen:
            seen.add(u); urls.append(u)
    # 若 API 命中为 0，再走 HTML 降级
    if not urls:
        urls = html_iter(keywords, max_pages=max_pages)
    return urls
