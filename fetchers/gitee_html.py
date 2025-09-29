import re

from utils.http_client import request

SEARCH_URL = "https://gitee.com/search"

# 先粗提取 href="/xxx/yyy"；再严过滤
HREF_RE = re.compile(r'href="(/[^"/]+/[^"/]+)"')

EXCLUDE_PREFIX = {
    "assets",
    "static",
    "favicon.ico",
    "notifications",
    "explore",
    "login",
    "signup",
    "register",
    "about",
    "press",
    "events",
    "jobs",
    "pricing",
    "search",
    "site",
    "enterprise",
    "organizations",
    "help",
    "issues",
    "pulls",
    "forks",
    "gists",
    "settings",
    "api",
    "opensearch",
    "sessions",
    "oauth",
    "users",
}


def _is_repo_path(path: str) -> bool:
    """
    仅保留 '/owner/repo'：
    - 恰好两段
    - 两段都不含 '.'（排除 .css/.ico 等静态）
    - 第一段不在排除前缀表
    """
    if not path.startswith("/"):
        return False
    parts = [p for p in path.split("/") if p]
    if len(parts) != 2:
        return False
    a, b = parts
    if a in EXCLUDE_PREFIX:
        return False
    if "." in a or "." in b:
        return False
    return True


def html_search_once(keyword: str, page: int = 1) -> list[str]:
    """
    HTML 搜索一页；返回 '/owner/repo' 路径列表
    """
    params = {"q": keyword, "type": "repository", "page": page}
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    resp = request("GET", SEARCH_URL, params=params, headers=headers, timeout=30)
    resp.raise_for_status()
    html = resp.text

    paths = set()
    for m in HREF_RE.finditer(html):
        p = m.group(1)
        if _is_repo_path(p):
            paths.add(p)
    return sorted(paths)


def html_search_iter(keywords: list[str], max_pages: int = 2) -> list[str]:
    """
    多关键词轮询 + 翻页；返回去重后的 https 仓库链接列表
    """
    seen = set()
    results = []
    for kw in keywords:
        for p in range(1, max_pages + 1):
            paths = html_search_once(kw, page=p)
            if not paths:
                break
            for path in paths:
                url = "https://gitee.com" + path
                if url not in seen:
                    seen.add(url)
                    results.append(url)
    return results
