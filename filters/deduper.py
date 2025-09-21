import re
from typing import List, Dict

def owner_of_repo(full_name: str) -> str:
    """
    提取 GitHub repo 的 owner 部分，例如:
    'user/repo' -> 'user'
    """
    return full_name.split("/")[0] if full_name and "/" in full_name else full_name

def score_link(url: str, path: str) -> int:
    """
    给订阅链接打分：yaml > txt > sub > 其他
    """
    url_l = url.lower()
    path_l = (path or "").lower()
    score = 0
    if any(x in url_l for x in ("yaml","yml")) or path_l.endswith((".yaml",".yml")):
        score += 3
    elif url_l.endswith(".txt") or path_l.endswith(".txt"):
        score += 2
    elif url_l.endswith(".sub") or path_l.endswith(".sub"):
        score += 1
    return score


def pick_one_per_repo(items: List[Dict]) -> List[Dict]:
    """
    每个 owner+repo 只保留：
    1. 最新更新时间（updated_at）
    2. 内容条目数最多（entry_count）
    3. txt 类型优先（score）
    """
    from datetime import datetime
    best = {}
    for it in items:
        owner = it.get("owner")
        repo = it.get("src")
        updated_at = it.get("updated_at")
        entry_count = it.get("entry_count", 0)
        score = it.get("score", 0)
        if not owner or not repo:
            continue
        key = f"{owner}/{repo}"
        try:
            ts = datetime.fromisoformat(updated_at) if updated_at else datetime.min
        except Exception:
            ts = datetime.min
        it["_ts"] = ts
        if key not in best:
            best[key] = it
        else:
            cur = best[key]
            if it["_ts"] > cur["_ts"]:
                best[key] = it
            elif it["_ts"] == cur["_ts"]:
                if entry_count > cur.get("entry_count", 0):
                    best[key] = it
                elif entry_count == cur.get("entry_count", 0):
                    if score > cur.get("score", 0):
                        best[key] = it
    for v in best.values():
        v.pop("_ts", None)
    return list(best.values())
