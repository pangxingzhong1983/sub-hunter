from storage.secure import get_secret
from fetchers.github_adv import search_recent_repos
from fetchers.gh_files import list_repo_tree, candidate_paths, raw_url
from filters.extract import fetch_text, extract_candidate_urls
from filters.deduper import owner_of_repo, pick_one_per_repo, score_link
from checker.async_check import check_urls
from storage.history import load_history, save_history, update_all

import asyncio, os, sys, time

KEYWORDS = [
    "clash.yaml", "clash.yml", "clash订阅", "clash subscribe", "clash subscription", "clash sub", "clash free", "clash节点", "clash proxy",
    "v2ray订阅", "v2ray sub", "v2ray free", "v2ray节点", "v2ray proxy", "free v2ray", "free v2ray sub", "免费v2ray", "免费节点",
    "subconverter", "sub", "subscribe", "订阅", "机场订阅", "proxy subscribe", "proxy subscription", "proxy sub", "proxy list",
    "ss订阅", "ss sub", "trojan订阅", "trojan sub", "mihomo订阅", "mihomo sub", "clash.meta订阅", "clash.meta sub",
    "节点分享", "节点订阅", "SSR订阅", "SSR sub", "SSR free", "SSR节点", "SSR proxy", "SSR list"
]

MAX_REPOS = 100      # 调试限流，快速采集
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
        updated_at = repo.get("updated_at")  # ISO8601 字符串
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
            # 统计订阅条目数（proxies/vmess/vless/ss/trojan）
            entry_count = 0
            try:
                import yaml, re
                if path.lower().endswith(('.yaml','.yml')):
                    data = yaml.safe_load(txt)
                    if isinstance(data, dict) and "proxies" in data and isinstance(data["proxies"], list):
                        entry_count = len(data["proxies"])
                elif path.lower().endswith('.txt'):
                    entry_count = len(re.findall(r'(vmess://|vless://|trojan://|ss://)', txt, re.I))
            except Exception:
                entry_count = 0
            from filters.validator import is_valid_subscription
            for u in extract_candidate_urls(txt):
                # 只保留内容校验通过的订阅链接
                if is_valid_subscription(u, txt):
                    found.append({
                        "owner": owner_of_repo(full),
                        "src": full,
                        "path": path,
                        "url": u,
                        "score": score_link(u, path),
                        "updated_at": updated_at,
                        "entry_count": entry_count,
                    })
    from filters.deduper import pick_one_per_repo
    best = pick_one_per_repo(found)
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

    if len(all_urls) == 0:
        print(">>> 订阅链接数量为0，跳过 Gist 上传！")
    else:
        ok_up, code = upload_gist(all_urls)
        print(f">>> Gist上传: {ok_up} ({code})")

if __name__ == "__main__":
    main()
