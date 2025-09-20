import math
from utils.http_client import request

BASE = "https://api.github.com"

def gh_search_code(keyword: str, page: int = 1, per_page: int = 30, token: str = None):
    """
    调用 GitHub API 搜索代码
    :param keyword: 搜索关键词，例如 "free clash"
    :param page: 页码
    :param per_page: 每页数量 (最大100)
    :param token: GitHub Token (Bearer)
    :return: JSON dict
    """
    url = f"{BASE}/search/code"
    params = {"q": keyword, "page": page, "per_page": per_page}
    resp = request("GET", url, params=params, token=token, timeout=30)
    resp.raise_for_status()
    return resp.json()

def gh_search_repo(keyword: str, page: int = 1, per_page: int = 30, token: str = None):
    """
    调用 GitHub API 搜索仓库
    :param keyword: 搜索关键词，例如 "free v2ray"
    """
    url = f"{BASE}/search/repositories"
    params = {"q": keyword, "page": page, "per_page": per_page}
    resp = request("GET", url, params=params, token=token, timeout=30)
    resp.raise_for_status()
    return resp.json()

def iter_search_code(keyword: str, max_pages: int = 3, token: str = None):
    """
    自动翻页搜索，默认最多翻3页
    """
    all_items = []
    for p in range(1, max_pages+1):
        data = gh_search_code(keyword, page=p, token=token)
        items = data.get("items", [])
        all_items.extend(items)
        if len(items) < 30:  # 不满一页说明到底了
            break
    return all_items

def iter_search_repo(keyword: str, max_pages: int = 3, token: str = None):
    all_items = []
    for p in range(1, max_pages+1):
        data = gh_search_repo(keyword, page=p, token=token)
        items = data.get("items", [])
        all_items.extend(items)
        if len(items) < 30:
            break
    return all_items
