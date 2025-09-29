import asyncio
import os
import sys

from checker.async_check import check_urls
from fetchers.gh_files import candidate_paths, list_repo_tree, raw_url
from fetchers.github_adv import search_recent_repos
from filters.deduper import owner_of_repo, pick_one_per_owner, score_link
from filters.extract import extract_candidate_urls, fetch_text
from storage.history import load_history, save_history, update_all
from storage.secure import get_secret

# 关键词可增删；已含中英混合
KEYWORDS = [
    "clash.yaml",
    "clash subscription",
    "free v2ray sub",
    "订阅 转换",
    "免费 节点",
    "v2ray 订阅",
]


def gather_candidates(token):
    repos = search_recent_repos(KEYWORDS, token=token)
    found = []
    for repo in repos:
        full = repo.get("full_name")
        if not full:
            continue
        tree = list_repo_tree(full, token)
        for path in candidate_paths(tree):
            url = raw_url(full, path)
            try:
                txt = fetch_text(url)
            except Exception:
                continue
            urls = list(extract_candidate_urls(txt))
            for u in urls:
                found.append(
                    {
                        "owner": owner_of_repo(full),
                        "src": full,
                        "path": path,
                        "url": u,
                        "score": score_link(u, path),
                    }
                )
    # 同发布者仅留“最强”一条
    best = pick_one_per_owner(found)
    # 链接去重
    uniq, seen = [], set()
    for it in best:
        if it["url"] not in seen:
            uniq.append(it)
            seen.add(it["url"])
    return uniq


def upload_gist(lines):
    gid = get_secret("sub-hunter", "GIST_ID")
    tok = get_secret("sub-hunter", "GIST_TOKEN")
    if not gid or not tok:
        return False, "no gist secrets"
    import requests

    payload = {"files": {"zhuquejisu.txt": {"content": "\n".join(lines)}}}
    r = requests.patch(
        f"https://api.github.com/gists/{gid}",
        headers={
            "Authorization": f"Bearer {tok}",
            "Accept": "application/vnd.github+json",
        },
        json=payload,
        timeout=30,
    )
    return r.ok, r.status_code


def main():
    tok = get_secret("sub-hunter", "GITHUB_TOKEN") or get_secret(
        "sub-hunter", "GIST_TOKEN"
    )
    if not tok:
        print("ERROR: no GitHub token in keychain (GITHUB_TOKEN/GIST_TOKEN).")
        sys.exit(2)

    print(">>> 搜索 & 抽取…")
    items = gather_candidates(tok)
    print(f">>> 发布者去重后候选: {len(items)}")

    urls = [it["url"] for it in items]
    print(">>> 连通性检测…")
    ok = asyncio.run(check_urls(urls, concurrency=20))
    print(f">>> 可用链接: {len(ok)}")

    hist = load_history()
    all_urls = update_all(hist, ok)  # ✅ 全量覆盖，不限 +10
    save_history(hist)
    print(f">>> 本次全量覆盖: {len(all_urls)} 条")

    os.makedirs("output", exist_ok=True)
    with open("output/subs_latest.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(all_urls))
    print(">>> 已写入 output/subs_latest.txt")

    ok_up, code = upload_gist(all_urls)
    print(f">>> Gist上传: {ok_up} ({code})")


if __name__ == "__main__":
    main()
