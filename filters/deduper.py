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

def pick_one_per_owner(items: List[Dict]) -> List[Dict]:
    """
    每个 owner 只保留一条分数最高的
    """
    best = {}
    for it in items:
        owner = it.get("owner")
        score = it.get("score", 0)
        if not owner:
            continue
        if owner not in best or score > best[owner]["score"]:
            best[owner] = it
    return list(best.values())
