from utils.http_client import request

SKIP_REPO_SUBSTR = ("github.io",)
KEEP_EXT = (".yaml",".yml",".txt",".conf",".ini",".md")
KEEP_KEYS = ("clash","mihomo","v2ray","sub","subscribe","subscrib","converter")
SKIP_DIRS = (
    "assets/","static/","images/","img/","css/","js/","fonts/","node_modules/",
    "public/","dist/","build/","docs/",".github/",".vitepress/",".vuepress/"
)

def list_repo_tree(full: str, token: str):
    if any(s in full.lower() for s in SKIP_REPO_SUBSTR):
        return []
    url = f"https://api.github.com/repos/{full}/git/trees/HEAD"
    try:
        r = request("GET", url, params={"recursive": "1"}, token=token, timeout=45)
        if not r.ok:
            return []
        return r.json().get("tree", []) or []
    except Exception:
        # 单仓异常直接跳过，防止整条任务中断
        return []

def candidate_paths(tree):
    for it in tree:
        if it.get("type") != "blob":
            continue
        p = it.get("path","")
        lp = p.lower()
        if any(lp.startswith(sd) for sd in SKIP_DIRS):
            continue
        if not lp.endswith(KEEP_EXT):
            continue
        if not any(k in lp for k in KEEP_KEYS):
            continue
        yield p

def raw_url(full: str, path: str):
    return f"https://raw.githubusercontent.com/{full}/HEAD/{path}"
