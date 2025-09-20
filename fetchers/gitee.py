from utils.http_client import request
BASE = "https://gitee.com/api/v5"

def ge_search_repos(keyword: str, page: int = 1, per_page: int = 20, token: str = None):
    """
    Gitee 仓库搜索（支持匿名/Token）
    仅支持参数：q / page / per_page；access_token 放 query
    """
    url = f"{BASE}/search/repositories"
    params = {"q": keyword, "page": page, "per_page": per_page}
    if token:
        params["access_token"] = token
    resp = request("GET", url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()

def iter_search_repos(keywords, max_pages: int = 2, token: str = None):
    seen = set()
    results = []
    for kw in keywords:
        for p in range(1, max_pages+1):
            items = ge_search_repos(kw, page=p, token=token)
            if not items:
                break
            for it in items:
                rid = it.get("html_url") or it.get("full_name") or it.get("id")
                if rid and rid not in seen:
                    seen.add(rid); results.append(it)
            if len(items) < 20:
                break
    return results
