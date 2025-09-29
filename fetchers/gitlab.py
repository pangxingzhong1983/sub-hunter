import requests

from .utils import extract_links, http_get

# 公共 GitLab
SEARCH = "https://gitlab.com/api/v4/projects"


def search_repos(keyword: str, n: int):
    r = requests.get(
        SEARCH, params={"search": keyword, "simple": "true", "per_page": n}, timeout=20
    )
    r.raise_for_status()
    return r.json()


def fetch_readme_links(path_with_ns: str):
    # 尝试 main/master
    for branch in ("main", "master"):
        raw = f"https://gitlab.com/{path_with_ns}/-/raw/{branch}/README.md"
        try:
            t = http_get(raw, timeout=15)
            if t.status_code == 200:
                return extract_links(t.text)
        except Exception:
            pass
    return []


def collect_links(keywords: list[str], per_key: int):
    results = set()
    for kw in keywords:
        try:
            for proj in search_repos(kw, per_key):
                path = proj.get("path_with_namespace")
                if not path:
                    continue
                for u in fetch_readme_links(path):
                    results.add(u)
        except Exception:
            continue
    return list(results)
