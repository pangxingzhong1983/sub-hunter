import datetime as _dt
from typing import List, Dict, Any, Iterable, Tuple
from utils.http_client import request
from config.search_policy import DAYS_BACK, SLICE_DAYS, PER_PAGE

BASE = "https://api.github.com"

def _date_str(d: _dt.date) -> str:
    return d.isoformat()

def _preflight_repo_count(q: str, token: str) -> int:
    # 轻量探测：per_page=1 拿 total_count
    params = {"q": q, "per_page": 1}
    r = request("GET", f"{BASE}/search/repositories", params=params, token=token, timeout=45)
    r.raise_for_status()
    return int(r.json().get("total_count", 0))

def _page_all_repos(q: str, token: str) -> Iterable[Dict[str, Any]]:
    page = 1
    fetched = 0
    while True:
        params = {
            "q": q, "page": page, "per_page": PER_PAGE,
            "sort": "updated", "order": "desc"
        }
        r = request("GET", f"{BASE}/search/repositories", params=params, token=token, timeout=60)
        r.raise_for_status()
        data = r.json()
        items = data.get("items", []) or []
        if not items:
            break
        for it in items:
            yield it
        fetched += len(items)
        # GitHub 对单次搜索最多返回前 1000 条
        if fetched >= 1000:
            break
        if len(items) < PER_PAGE:
            break
        page += 1

def _split_range(s: _dt.date, e: _dt.date) -> Tuple[Tuple[_dt.date,_dt.date], Tuple[_dt.date,_dt.date]]:
    mid = s + _dt.timedelta(days=(e - s).days // 2 or 1)
    return (s, mid - _dt.timedelta(days=1)), (mid, e)

def _search_window(keyword: str, start: _dt.date, end: _dt.date, token: str) -> Iterable[Dict[str,Any]]:
    """
    对 [start, end] 作仓库搜索；若命中>=1000，递归二分时间区间。
    """
    q = f'{keyword} pushed:{_date_str(start)}..{_date_str(end)}'
    total = _preflight_repo_count(q, token)
    if total >= 1000 and (end - start).days >= 1:
        a, b = _split_range(start, end)
        yield from _search_window(keyword, a[0], a[1], token)
        yield from _search_window(keyword, b[0], b[1], token)
    else:
        yield from _page_all_repos(q, token)

def search_recent_repos(keywords: List[str], token: str, limit: int | None = None) -> List[Dict[str,Any]]:
    """
    近 DAYS_BACK 天内，按 SLICE_DAYS 切片；对每个关键词覆盖所有结果（无页数上限），自动避开1000限制
    """
    today = _dt.date.today()
    since = today - _dt.timedelta(days=DAYS_BACK)
    out: Dict[str, Dict[str,Any]] = {}  # full_name -> repo

    if limit is not None and limit <= 0:
        limit = None
    for kw in keywords:
        # 滚动窗口（大窗口可能仍会被递归二分）
        s = since
        while s <= today:
            e = min(s + _dt.timedelta(days=SLICE_DAYS-1), today)
            for it in _search_window(kw, s, e, token):
                name = it.get("full_name")
                if name and name not in out:
                    out[name] = it
                    if limit and len(out) >= limit:
                        return list(out.values())
            if limit and len(out) >= limit:
                break
            s = e + _dt.timedelta(days=1)
        if limit and len(out) >= limit:
            break
    return list(out.values())
