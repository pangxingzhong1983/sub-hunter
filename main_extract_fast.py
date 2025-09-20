from storage.secure import get_secret
from fetchers.github_adv import search_recent_repos
from fetchers.gh_files import list_repo_tree, candidate_paths, raw_url
from filters.extract import fetch_text, extract_candidate_urls
from filters.deduper import owner_of_repo, pick_one_per_owner, score_link
from checker.async_check import check_urls
from storage.history import load_history, save_history, update_all

import asyncio, os, sys, time

KEYWORDS = [
    "clash.yaml","clash subscription","free v2ray sub",
    "订阅 转换","免费 节点","v2ray 订阅"
]

MAX_REPOS = 0        # 先小批量验证，后续可改为 0=不限
PRINT_EVERY_REPO = 10  # 每处理多少仓库打一次进度
PRINT_EVERY_FILE = 50  # 每检查多少文件打一次进度

def gather_candidates(token):
    t0 = time.time()
    repos = search_recent_repos(KEYWORDS, token=token)
    if MAX_REPOS and len(repos) > MAX_REPOS:
        repos = repos[:MAX_REPOS]
    print(f"[I] 待处理仓库: {len(repos)}")
    found=[]; repo_cnt=0; file_cnt=0

    for repo in repos:
        full = repo.get("full_name")
        if not full:
            continue
        repo_cnt += 1
        if repo_cnt % PRINT_EVERY_REPO == 0:
            print(f"[I] 仓库进度: {repo_cnt}/{len(repos)} | 已命中链接: {len(found)} | 耗时: {int(time.time()-t0)}s")
        tree = list_repo_tree(full, token)
        for path in candidate_paths(tree):
            file_cnt += 1
            if file_cnt % PRINT_EVERY_FILE == 0:
                print(f"[I] 文件进度: {file_cnt} | 已命中链接: {len(found)} | 当前仓库: {full}")
            url = raw_url(full, path)
            try:
                txt = fetch_text(url)
            except Exception:
                continue
            for u in extract_candidate_urls(txt):
                found.append({
                    "owner": owner_of_repo(full),
                    "src": full,
                    "path": path,
                    "url": u,
                    "score": score_link(u, path),
                })
    best = pick_one_per_owner(found)
    uniq, seen = [], set()
    for it in best:
        if it["url"] not in seen:
            uniq.append(it); seen.add(it["url"])
    print(f"[I] 提取完成：候选(去重后)={len(uniq)}")
    return uniq

def upload_gist(lines):
    gid = get_secret("sub-hunter","GIST_ID")
    tok = get_secret("sub-hunter","GIST_TOKEN")
    if not gid or not tok:
        return False, "no gist secrets"
    import requests
    payload = {"files": {"zhuquejisu.txt": {"content": "\n".join(lines)}}}
    r = requests.patch(
        f"https://api.github.com/gists/{gid}",
        headers={"Authorization": f"Bearer {tok}",
                 "Accept": "application/vnd.github+json"},
        json=payload, timeout=30
    )
    return r.ok, r.status_code

def main():
    tok = get_secret("sub-hunter","GITHUB_TOKEN") or get_secret("sub-hunter","GIST_TOKEN")
    if not tok:
        print("ERROR: no GitHub token in keychain (GITHUB_TOKEN/GIST_TOKEN)."); sys.exit(2)

    print(">>> 搜索 & 抽取…(可见进度)")
    items = gather_candidates(tok)
    print(f">>> 发布者去重后候选: {len(items)}")

    urls = [it["url"] for it in items]
    print(">>> 连通性检测…")
    ok = asyncio.run(check_urls(urls, concurrency=20))
    print(f">>> 可用链接: {len(ok)}")

    hist = load_history()
    all_urls = update_all(hist, ok)
    save_history(hist)
    print(f">>> 本次全量覆盖: {len(all_urls)} 条")

    os.makedirs("output", exist_ok=True)
    with open("output/subs_latest.txt","w",encoding="utf-8") as f:
        f.write("\n".join(all_urls))
    print(">>> 已写入 output/subs_latest.txt")

    ok_up, code = upload_gist(all_urls)
    print(f">>> Gist上传: {ok_up} ({code})")

if __name__ == "__main__":
    main()
