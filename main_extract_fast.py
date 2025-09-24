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
    "订阅 转换","免费 节点","v2ray 订阅","free v2ray","free vpn","free clash"
]

MAX_REPOS = 10        # 先小批量验证，后续可改为 0=不限
PRINT_EVERY_REPO = 10  # 每处理多少仓库打一次进度
PRINT_EVERY_FILE = 50  # 每检查多少文件打一次进度

def gather_candidates(token):
    # 递归抓取所有链接，递归深度可配置
    def recursive_extract(urls, depth=2, visited=None, owner=None, src=None, path=None):
        if visited is None:
            visited = set()
        results = []
        SUFFIX_DIRECT_SAVE = (".txt", ".yaml", ".yml")
        DOMAIN_BLACKLIST = ("www.youtube.com", "youtu.be")
        from urllib.parse import urlparse
        TEXT_EXTS = ('.txt','.yaml','.yml','.md','.json','.conf','.ini','.list')
        SKIP_EXTS = ('.png','.jpg','.jpeg','.svg','.gif','.bmp','.ico','.webp','.pdf','.exe','.apk','.zip','.tar','.gz','.rar','.7z','.mp3','.mp4','.avi','.mov','.mkv','.woff2','.ttf','.otf','.eot')
        for url in urls:
            if url in visited:
                continue
            visited.add(url)
            try:
                domain = urlparse(url).netloc.lower()
            except Exception as e:
                print(f"[R] urlparse失败跳过: {url} ({e})")
                continue
            last = url.split('/')[-1].split('?')[0].split('#')[0].lower()
            # 黑名单域名直接跳过
            if domain in DOMAIN_BLACKLIST:
                print(f"[R] 黑名单域名跳过: {url}")
                continue
            # 命中白名单后缀或关键词的链接无条件保存
            from filters.extract import EXT_KEYS, SUFFIX_WHITELIST
            suf = last.split('.')[-1] if '.' in last else ''
            # 关键词模糊匹配（忽略大小写，部分匹配）
            url_lc = url.lower()
            fuzzy_hit = any(k.lower() in url_lc for k in EXT_KEYS)
            if suf in SUFFIX_WHITELIST or fuzzy_hit:
                print(f"[R] 直接保存URL（命中白名单/关键词）: {url}")
                results.append({
                    "owner": owner,
                    "src": src,
                    "path": path or url,
                    "url": url,
                    "score": score_link(url, path or url),
                })
                # 只要不是txt/yaml/yml，且是文本类才递归
                if suf not in SUFFIX_DIRECT_SAVE and any(last.endswith(suf2) for suf2 in TEXT_EXTS):
                    print(f"[R] 递归抓取: url={url} depth={depth}")
                    import concurrent.futures
                    txt = None
                    def fetch_with_timeout(u):
                        return fetch_text(u)
                    try:
                        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                            future = executor.submit(fetch_with_timeout, url)
                            txt = future.result(timeout=10)
                    except Exception:
                        print(f"[R] 抓取失败或超时: url={url} depth={depth}")
                        continue
                    extracted = list(extract_candidate_urls(txt))
                    print(f"[R] url={url} depth={depth} 抽取到新链接数: {len(extracted)}")
                    for u in extracted:
                        results.append({
                            "owner": owner,
                            "src": src,
                            "path": path or url,
                            "url": u,
                            "score": score_link(u, path or url),
                        })
                    if depth > 1:
                        results += recursive_extract(extracted, depth=depth-1, visited=visited, owner=owner, src=src, path=path or url)
                continue
            # 其它情况，只有文本类才递归
            if any(last.endswith(suf) for suf in TEXT_EXTS):
                print(f"[R] 递归抓取: url={url} depth={depth}")
                import concurrent.futures
                txt = None
                def fetch_with_timeout(u):
                    return fetch_text(u)
                try:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(fetch_with_timeout, url)
                        txt = future.result(timeout=10)
                except Exception:
                    print(f"[R] 抓取失败或超时: url={url} depth={depth}")
                    continue
                extracted = list(extract_candidate_urls(txt))
                print(f"[R] url={url} depth={depth} 抽取到新链接数: {len(extracted)}")
                for u in extracted:
                    results.append({
                        "owner": owner,
                        "src": src,
                        "path": path or url,
                        "url": u,
                        "score": score_link(u, path or url),
                    })
                if depth > 1:
                    results += recursive_extract(extracted, depth=depth-1, visited=visited, owner=owner, src=src, path=path or url)
        return results
    t0 = time.time()
    limit = MAX_REPOS if MAX_REPOS else None
    repos = search_recent_repos(KEYWORDS, token=token, limit=limit)
    if limit and len(repos) > limit:
        repos = repos[:limit]
    print(f"[I] 待处理仓库: {len(repos)}")
    found=[]; repo_cnt=0; file_cnt=0

    for repo in repos:
        full = repo.get("full_name")
        if not full:
            continue
        repo_cnt += 1
        if repo_cnt % PRINT_EVERY_REPO == 0:
            print(f"[I] 仓库进度: {repo_cnt}/{len(repos)} | 已命中链接: {len(found)} | 耗时: {int(time.time()-t0)}s")
        # 抓取 README.md 和 description
        desc = repo.get("description") or ""
        default_branch = repo.get("default_branch") or "HEAD"
        readme_branch = default_branch if default_branch else "HEAD"
        readme_url = f"https://raw.githubusercontent.com/{full}/{readme_branch}/README.md"
        readme_txt = ""
        try:
            readme_txt = fetch_text(readme_url)
        except Exception:
            pass
        from filters.extract import URL_RE
        meta_links = set(URL_RE.findall(desc) + URL_RE.findall(readme_txt))
        print(f"[D] 仓库:{full} meta页面抽取到链接数:{len(meta_links)}")
        # 递归抓取 meta_links
        found += recursive_extract(meta_links, depth=3, owner=owner_of_repo(full), src=full)
        # 继续原有文件树抓取
        tree = list_repo_tree(full, token)
        for path in candidate_paths(tree):
            file_cnt += 1
            if file_cnt % PRINT_EVERY_FILE == 0:
                print(f"[I] 文件进度: {file_cnt} | 已命中链接: {len(found)} | 当前仓库: {full}")
            url = raw_url(full, path)
            lp = path.lower()
            if lp.endswith(('.txt','.yaml','.yml')):
                print(f"[D] 仓库:{full} 路径:{path} 直接保存订阅文件URL: {url}")
                found.append({
                    "owner": owner_of_repo(full),
                    "src": full,
                    "path": path,
                    "url": url,
                    "score": score_link(url, path),
                })
                continue
            try:
                txt = fetch_text(url)
            except Exception:
                continue
            extracted = list(extract_candidate_urls(txt))
            print(f"[D] 仓库:{full} 路径:{path} 抽取到链接数:{len(extracted)}")
            # 递归抓取文件内容抽取到的链接
            found += recursive_extract(extracted, depth=3, owner=owner_of_repo(full), src=full, path=path)
    print(f"[I] 抓取/抽取后总链接数: {len(found)}")
    # 临时关闭 owner 去重，直接返回所有抽取结果
    uniq, seen = [], set()
    for it in found:
        if it["url"] not in seen:
            uniq.append(it); seen.add(it["url"])
    print(f"[I] 去重后链接数: {len(uniq)}")
    return uniq

def upload_gist_from_file(filepath):
    gid = get_secret("sub-hunter","GIST_ID")
    tok = get_secret("sub-hunter","GIST_TOKEN")
    if not gid or not tok:
        return False, "no gist secrets"
    import requests
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return False, f"file read error: {e}"
    payload = {"files": {"zhuquejisu.txt": {"content": content}}}
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
    # 统计输出
    print(f"[I] main流程收到 items 数量: {len(items)}")

    if len(items) == 0:
        print(">>> 去重后结果为0，跳过连通性检测和 Gist 上传！")
        return

    # 强化排除后缀，彻底剔除所有无关链接
    EXCLUDE_SUFFIXES = [
        ".lock", ".cache", ".pid", ".sock", ".out", ".err", ".log", ".tmp", ".swp", ".swo", ".swn", ".bak", ".old", ".orig", ".sample", ".test", ".demo", ".example", ".template", ".config", ".settings", ".env",
        ".mrs", ".list", ".html", ".ini", ".atom", ".git", ".go", ".md", ".pdf", ".doc", ".xls", ".ppt", ".exe", ".apk", ".zip", ".tar", ".gz", ".rar", ".7z", ".bmp", ".ttf", ".otf", ".eot", ".mp3", ".mp4", ".avi", ".mov", ".mkv", ".webm", ".json", ".xml", ".rss", ".atom", ".map", ".psd", ".ai", ".eps", ".dmg", ".iso", ".bin", ".csv", ".ts", ".tsx", ".jsx", ".vue", ".svelte", ".php", ".asp", ".aspx", ".jsp", ".cgi", ".pl", ".rb", ".go", ".rs", ".swift", ".kt", ".dart", ".sh", ".bat", ".cmd", ".ps1", ".dockerfile", ".gitignore", ".gitattributes", ".editorconfig", ".npmignore", ".yarn.lock", ".woff2", ".ico", ".svg", ".png", ".jpg", ".webp", ".css", ".js", ".fonts"
    ]
    KEYWORDS = [
        "subscribe", "sub", "clash", "v2ray", "ss", "vless", "vmess", "trojan", "hysteria2", "tuic", "yaml", "list", "v2", "free", "public", "Router"
    ]
    from filters.extract import SUFFIX_WHITELIST
    def is_subscription_url(url):
        last = url.split('/')[-1].split('?')[0].split('#')[0]
        # 0. 先排除EXCLUDE_SUFFIXES（无论是否有后缀）
        for suf in EXCLUDE_SUFFIXES:
            if last.lower().endswith(suf):
                print(f"[排除后缀剔除] {url}")
                return False
        # 1. 后缀为yaml/yml/txt强制保留
        if '.' in last:
            suf = last.split('.')[-1].lower()
            if suf in SUFFIX_WHITELIST:
                print(f"[机场订阅保留] {url}")
                return True
        # 2. 无后缀链接，必须命中英文关键词（关键词为独立单词，避免误判）
        import re
        url_lc = url.lower()
        for k in KEYWORDS:
            # 只保留英文关键词，忽略中文
            if re.search(rf'\b{k}\b', url_lc) and all(ord(c) < 128 for c in k):
                print(f"[关键词保留] {url}")
                return True
        # 3. 其余全部剔除
        print(f"[剔除] {url}")
        return False
    urls = [it["url"] for it in items if is_subscription_url(it["url"])]
    print(f"[统计] 抓取总数: {len(items)}，筛选后订阅数: {len(urls)}")

    hist = load_history()
    existing = hist.get("seen", []) or []

    merged = []
    seen_urls = set()
    for u in existing:
        if u and u not in seen_urls:
            merged.append(u)
            seen_urls.add(u)
    for u in urls:
        if u and u not in seen_urls:
            merged.append(u)
            seen_urls.add(u)

    print(f"[统计] 历史合并后待检测: {len(merged)}")
    if not merged:
        print(">>> 无可检测链接，跳过连通性检测和 Gist 上传！")
        return

    print(">>> 连通性检测…")
    ok = asyncio.run(check_urls(merged, concurrency=20))
    print(f"[统计] 可用订阅链接: {len(ok)}")

    all_urls = update_all(hist, ok)
    save_history(hist)
    print(f"[统计] 本次全量覆盖: {len(all_urls)} 条")

    os.makedirs("output", exist_ok=True)
    with open("output/subs_latest.txt","w",encoding="utf-8") as f:
        f.write("\n".join(all_urls))
    print(">>> 已写入 output/subs_latest.txt")

    if len(all_urls) == 0:
        print(">>> 订阅链接数量为0，跳过 Gist 上传！")
        return

    ok_up, code = upload_gist_from_file("output/subs_latest.txt")
    print(f">>> Gist上传: {ok_up} ({code})")

if __name__ == "__main__":
    main()
