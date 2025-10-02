import asyncio
import base64
import binascii
import os
import re
import string
import sys
import time
from urllib.parse import urlparse

from checker.async_check import check_urls
from config import (
    DAILY_INCREMENT,
    FAIL_THRESHOLD,
    HIST_PATH,
    TRUSTED_GET_HOSTS,
    TRUSTED_GET_TIMEOUT,
    TRUSTED_GET_VERIFY,
)
from fetchers.gh_files import candidate_paths, list_repo_tree, raw_url
from fetchers.github_adv import search_recent_repos
from filters.deduper import owner_of_repo, score_link
from filters.extract import extract_candidate_urls, fetch_text, normalize_url
from storage.history import ensure_increment, load_history, save_history
from storage.secure import get_secret

KEYWORDS = [
    # Core English phrases
    "clash.yaml",
    "clash subscription",
    "free v2ray sub",
    "free clash",
    "free vpn",
    "free proxy list",
    "subscription link",
    "node share",
    "trojan subscription",
    "wireguard subscription",
    "hysteria subscription",
    "tuic subscription",
    "mihomo config",
    "clash nodes",
    # Chinese combinations
    "订阅 转换",
    "免费 节点",
    "免费 机场",
    "机场 节点",
    "节点 分享",
    "白嫖 节点",
    "机场 订阅",
    "免费 v2ray",
    "免费 trojan",
    "免费 vless",
    "免费 hysteria",
    "免费 wireguard",
    "机场 转换",
    "机场 分享",
    # Mixed keywords often seen in repos
    "clash meta",
    "clash config",
    "v2ray subscription",
    "proxy subscription",
]

URL_SUBSTR_BLACKLIST = [
    "blackmatrix7/ios_rule_script",
    "domain-filter/",
    "easylist",
    "easyprivacy",
    "easylistchina",
    "adrules",
    "adguard",
    "clashx-pro/distribution_groups",
    "sub-web.netlify.app",
    "loyalsoldier/clash-rules",
    "help.wwkejishe.top/free-shadowrocket",
    # 新增：排除明显的非订阅链接
    "forums/topic/",
    "forum.php",
    "/thread-",
    "/viewtopic.php",
    "/showthread.php",
    "/discussion/",
    "sockscap64.com/forums",
    "github.com/releases",
    "/issues/",
    "/pull/",
    "/wiki/",
    "/docs/",
    "youtube.com",
    "youtu.be",
    "bilibili.com",
    "telegram.me",
    "t.me/",
    "/download/",
    "/archive/",
    "/blob/",  # GitHub blob 页面
    "/commit/",
    "/compare/",
]

MAX_REPOS = 50  # 先小批量验证，后续可改为 0=不限
PRINT_EVERY_REPO = 10  # 每处理多少仓库打一次进度
PRINT_EVERY_FILE = 50  # 每检查多少文件打一次进度


def gather_candidates(token):
    # 递归抓取所有链接，递归深度可配置
    def recursive_extract(urls, depth=2, visited=None, owner=None, src=None, path=None):
        if visited is None:
            visited = set()
        results = []
        # Note: compare against `suf` (no leading dot), so list must not include dots
        SUFFIX_DIRECT_SAVE = ("yaml", "yml")
        DOMAIN_BLACKLIST = ("www.youtube.com", "youtu.be")

        TEXT_EXTS = (".txt", ".yaml", ".yml", ".md", ".json", ".conf", ".ini", ".list")
        SKIP_EXTS = (
            ".png",
            ".jpg",
            ".jpeg",
            ".svg",
            ".gif",
            ".bmp",
            ".ico",
            ".webp",
            ".pdf",
            ".exe",
            ".apk",
            ".zip",
            ".tar",
            ".gz",
            ".rar",
            ".7z",
            ".mp3",
            ".mp4",
            ".avi",
            ".mov",
            ".mkv",
            ".woff2",
            ".ttf",
            ".otf",
            ".eot",
        )
        for raw_url_val in urls:
            url = normalize_url(raw_url_val)
            if not url:
                continue
            # canonicalize to collapse proxy wrappers (eg. gh.xx/https://raw...)
            try:
                canon = canonicalize_url(url)
            except Exception:
                canon = url
            # soft cap to avoid runaway recursion
            if len(visited) > 2000:
                print(f"[R] 访问集合过大，跳过剩余: {len(visited)}")
                break
            if canon in visited:
                continue
            visited.add(canon)
            try:
                domain = urlparse(url).netloc.lower()
            except Exception as e:
                print(f"[R] urlparse失败跳过: {url} ({e})")
                continue
            last = url.split("/")[-1].split("?")[0].split("#")[0].lower()
            # 黑名单域名直接跳过
            if domain in DOMAIN_BLACKLIST:
                print(f"[R] 黑名单域名跳过: {url}")
                continue
            # 命中白名单后缀或关键词的链接无条件保存
            from filters.extract import EXT_KEYS, SUFFIX_WHITELIST

            suf = last.split(".")[-1] if "." in last else ""
            # 关键词模糊匹配（忽略大小写，部分匹配）
            url_lc = url.lower()
            fuzzy_hit = any(k.lower() in url_lc for k in EXT_KEYS)
            if suf in SUFFIX_WHITELIST or fuzzy_hit:
                print(f"[R] 直接保存URL（命中白名单/关键词）: {url}")
                results.append(
                    {
                        "owner": owner,
                        "src": src,
                        "path": path or url,
                        "url": canon,
                        "score": score_link(canon, path or url),
                    }
                )
                # 只要不是txt/yaml/yml，且是文本类才递归
                if suf not in SUFFIX_DIRECT_SAVE and any(
                    last.endswith(suf2) for suf2 in TEXT_EXTS
                ):
                    print(f"[R] 递归抓取: url={url} depth={depth}")
                    import concurrent.futures

                    txt = None

                    def fetch_with_timeout(u):
                        return fetch_text(u)

                    try:
                        with concurrent.futures.ThreadPoolExecutor(
                            max_workers=1
                        ) as executor:
                            future = executor.submit(fetch_with_timeout, url)
                            txt = future.result(timeout=10)
                    except Exception:
                        print(f"[R] 抓取失败或超时: url={url} depth={depth}")
                        continue
                    extracted = list(extract_candidate_urls(txt))
                    print(
                        f"[R] url={url} depth={depth} 抽取到新链接数: {len(extracted)}"
                    )
                    canonical_extracted = []
                    for u in extracted:
                        nu = normalize_url(u)
                        if not nu:
                            continue
                        try:
                            cnu = canonicalize_url(nu)
                        except Exception:
                            cnu = nu
                        canonical_extracted.append(cnu)
                        results.append(
                            {
                                "owner": owner,
                                "src": src,
                                "path": path or url,
                                "url": cnu,
                                "score": score_link(cnu, path or url),
                            }
                        )
                    if depth > 1:
                        results += recursive_extract(
                            canonical_extracted,
                            depth=depth - 1,
                            visited=visited,
                            owner=owner,
                            src=src,
                            path=path or url,
                        )
                continue
            # 其它情况，只有文本类才递归
            if any(last.endswith(suf) for suf in TEXT_EXTS):
                print(f"[R] 递归抓取: url={url} depth={depth}")
                import concurrent.futures

                txt = None

                def fetch_with_timeout(u):
                    return fetch_text(u)

                try:
                    with concurrent.futures.ThreadPoolExecutor(
                        max_workers=1
                    ) as executor:
                        future = executor.submit(fetch_with_timeout, url)
                        txt = future.result(timeout=10)
                except Exception:
                    print(f"[R] 抓取失败或超时: url={url} depth={depth}")
                    continue
                extracted = list(extract_candidate_urls(txt))
                print(f"[R] url={url} depth={depth} 抽取到新链接数: {len(extracted)}")
                canonical_extracted = []
                for u in extracted:
                    nu = normalize_url(u)
                    if not nu:
                        continue
                    try:
                        cnu = canonicalize_url(nu)
                    except Exception:
                        cnu = nu
                    canonical_extracted.append(cnu)
                    results.append(
                        {
                            "owner": owner,
                            "src": src,
                            "path": path or url,
                            "url": cnu,
                            "score": score_link(cnu, path or url),
                        }
                    )
                if depth > 1:
                    results += recursive_extract(
                        canonical_extracted,
                        depth=depth - 1,
                        visited=visited,
                        owner=owner,
                        src=src,
                        path=path or url,
                    )
        return results

    t0 = time.time()
    limit = MAX_REPOS if MAX_REPOS else None
    repos = search_recent_repos(KEYWORDS, token=token, limit=limit)
    if limit and len(repos) > limit:
        repos = repos[:limit]
    print(f"[I] 待处理仓库: {len(repos)}")
    found = []
    repo_cnt = 0
    file_cnt = 0

    for repo in repos:
        full = repo.get("full_name")
        if not full:
            continue
        repo_cnt += 1
        if repo_cnt % PRINT_EVERY_REPO == 0:
            print(
                f"[I] 仓库进度: {repo_cnt}/{len(repos)} | 已命中链接: {len(found)} | 耗时: {int(time.time()-t0)}s"
            )
        # 抓取 README.md 和 description
        desc = repo.get("description") or ""
        default_branch = repo.get("default_branch") or "HEAD"
        readme_branch = default_branch if default_branch else "HEAD"
        readme_url = (
            f"https://raw.githubusercontent.com/{full}/{readme_branch}/README.md"
        )
        readme_txt = ""
        try:
            readme_txt = fetch_text(readme_url)
        except Exception:
            pass
        from filters.extract import URL_RE

        meta_links = {
            normalize_url(u)
            for u in (URL_RE.findall(desc) + URL_RE.findall(readme_txt))
            if normalize_url(u)
        }
        print(f"[D] 仓库:{full} meta页面抽取到链接数:{len(meta_links)}")
        # 递归抓取 meta_links
        found += recursive_extract(
            meta_links, depth=3, owner=owner_of_repo(full), src=full
        )
        # 继续原有文件树抓取
        tree = list_repo_tree(full, token)
        for path in candidate_paths(tree):
            file_cnt += 1
            if file_cnt % PRINT_EVERY_FILE == 0:
                print(
                    f"[I] 文件进度: {file_cnt} | 已命中链接: {len(found)} | 当前仓库: {full}"
                )
            url = raw_url(full, path)
            url = normalize_url(url)
            lp = path.lower()
            if lp.endswith((".yaml", ".yml")):
                print(f"[D] 仓库:{full} 路径:{path} 直接保存订阅文件URL: {url}")
                found.append(
                    {
                        "owner": owner_of_repo(full),
                        "src": full,
                        "path": path,
                        "url": url,
                        "score": score_link(url, path),
                    }
                )
                continue
            if lp.endswith(".txt"):
                print(f"[D] 仓库:{full} 路径:{path} 保存并递归解析TXT: {url}")
                found.append(
                    {
                        "owner": owner_of_repo(full),
                        "src": full,
                        "path": path,
                        "url": url,
                        "score": score_link(url, path),
                    }
                )
            try:
                txt = fetch_text(url)
            except Exception:
                continue
            extracted = list(extract_candidate_urls(txt))
            print(f"[D] 仓库:{full} 路径:{path} 抽取到链接数:{len(extracted)}")
            # 递归抓取文件内容抽取到的链接
            found += recursive_extract(
                extracted, depth=3, owner=owner_of_repo(full), src=full, path=path
            )
    print(f"[I] 抓取/抽取后总链接数: {len(found)}")
    # 先按发布者与基础 URL（去除常见后缀）进行分组，优先保留 .txt 格式

    groups = {}

    def strip_known_ext(u: str) -> str:
        low = u.lower()
        for ext in (".yaml", ".yml", ".txt"):
            if low.endswith(ext):
                return u[: -len(ext)]
        return u

    for it in found:
        owner = it.get("owner") or "__no_owner__"
        key = (owner, strip_known_ext(it.get("url", "")))
        groups.setdefault(key, []).append(it)

    filtered_found = []
    for key, items in groups.items():
        if len(items) == 1:
            filtered_found.append(items[0])
            continue
        # 多个后缀版本：尝试优先保留 .txt
        txts = [i for i in items if i.get("url", "").lower().endswith(".txt")]
        if txts:
            chosen = txts[0]
            filtered_found.append(chosen)
            for i in items:
                if i is not chosen:
                    print(
                        f"[发布者同名去重] 保留 .txt：{chosen.get('url')}，剔除：{i.get('url')}"
                    )
        else:
            # 否则保留第一个遇到的（保持稳定性）
            chosen = items[0]
            filtered_found.append(chosen)
            for i in items[1:]:
                print(
                    f"[发布者同名去重] 保留：{chosen.get('url')}，剔除：{i.get('url')}"
                )
    # 最后按 URL 去重（跨发布者同 URL 也只保留一份）
    uniq, seen = [], set()
    for it in filtered_found:
        if it["url"] not in seen:
            uniq.append(it)
            seen.add(it["url"])
    print(f"[I] 去重后链接数: {len(uniq)}")
    return uniq


def _is_valid_token(token: str) -> bool:
    """验证订阅链接中的 token 是否有效。
    无效特征：
    1. 全是相同字符（如：000000... 或 aaaa...）
    2. 明显的占位符模式（如：demo, test, example, placeholder等）
    3. 过短或过长的 token
    4. 包含明显的测试/示例词汇
    """
    if not token or len(token) < 8:
        return False
    
    # 过长的 token（可能是错误的）
    if len(token) > 128:
        return False
    
    token_lower = token.lower()
    
    # 检查明显的占位符
    placeholders = {
        'demo', 'test', 'example', 'placeholder', 'sample', 'fake',
        'invalid', 'expired', 'none', 'null', 'undefined', 'default',
        'temp', 'temporary', 'admin', 'user', 'guest', 'public'
    }
    
    for placeholder in placeholders:
        if placeholder in token_lower:
            return False
    
    # 检查是否全是相同字符
    if len(set(token)) <= 2:  # 只有1-2个不同字符
        return False
    
    # 检查是否为简单递增数字序列（123456...）
    if token.isdigit():
        if len(token) >= 6:
            # 检查是否为连续数字
            is_sequential = True
            for i in range(1, len(token)):
                if int(token[i]) != (int(token[i-1]) + 1) % 10:
                    is_sequential = False
                    break
            if is_sequential:
                return False
        # 检查是否为重复数字（111111, 222222等）
        if len(set(token)) == 1:
            return False
    
    # 检查十六进制模式中的明显无效值
    if re.match(r'^[0-9a-fA-F]+$', token):
        # 全0或全F的十六进制
        if token_lower in ['00000000', 'ffffffff'] or \
           token_lower == '0' * len(token) or \
           token_lower == 'f' * len(token):
            return False
    
    return True


def _validate_subscription_url_params(url: str) -> bool:
    """验证订阅链接的参数是否有效。
    主要检查 token/key 等参数的合法性。
    """
    try:
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        
        # 检查 token 参数
        if 'token' in params:
            tokens = params['token']
            if tokens:  # token 参数存在
                token = tokens[0]  # 取第一个 token 值
                if not _is_valid_token(token):
                    return False
        
        # 检查 key 参数（有些机场用 key 而不是 token）
        if 'key' in params:
            keys = params['key']
            if keys:
                key = keys[0]
                if not _is_valid_token(key):
                    return False
        
        return True
    except Exception:
        return True  # 解析失败时不拒绝，避免误杀


def _maybe_base64_subscription(text: str) -> bool:
    cleaned = "".join(text.strip().split())
    if len(cleaned) > 8192:
        trimmed = cleaned[:8192]
        cleaned = trimmed
    if len(cleaned) < 16:
        return False

    allowed = set(string.ascii_letters + string.digits + "+/=_-")
    ratio = sum(1 for ch in cleaned if ch in allowed) / len(cleaned)
    if ratio < 0.97:
        return False

    pad = (-len(cleaned)) % 4
    candidate = cleaned + ("=" * pad)
    decoders = (
        lambda data: base64.b64decode(data, validate=False),
        lambda data: base64.urlsafe_b64decode(data),
    )
    for decoder in decoders:
        try:
            decoded = decoder(candidate)
        except (binascii.Error, ValueError):
            continue
        if not decoded:
            continue
        lower = decoded.decode("utf-8", "ignore").lower()
        POSITIVE = (
            "vmess://",
            "ss://",
            "ssr://",
            "trojan://",
            "vless://",
            "hysteria",
            "tuic",
        )
        if any(sig in lower for sig in POSITIVE):
            return True
    return False


def filter_subscription_content(urls):
    POSITIVE = (
        "proxies:",
        "proxy-groups",
        "vmess://",
        "ss://",
        "ssr://",
        "trojan://",
        "vless://",
        "hysteria",
        "tuic",
        "mixed-port",
        "servers:",
        "port:",
    )
    NEGATIVE = (
        "domain,",
        "domain-suffix",
        "domain-keyword",
        "ip-cidr",
        "payload:",
        "rule-set",
        "rules:",
    )
    kept = []
    pending = []
    # Use centralized validator for content validation to reduce false positives.
    from filters import validator

    for url in urls:
        try:
            text = fetch_text(url, timeout=25)
        except Exception:
            print(f"[内容获取失败缓存] {url}")
            pending.append(url)
            continue
        snippet = text.strip()
        if not snippet:
            print(f"[内容为空剔除] {url}")
            continue

        # Prefer strict validator which applies length checks, HTML detection,
        # YAML parsing and base64 heuristics consistently.
        try:
            if validator.is_valid_subscription(url, snippet):
                kept.append(url)
                continue
            else:
                # If the centralized validator rejects, still perform a lightweight
                # base64 heuristic as a final check (covers some short base64 subs).
                if _maybe_base64_subscription(snippet):
                    kept.append(url)
                    continue
                # Count negative indicators - if many, treat as rules/config file and drop.
                neg_hits = sum(snippet.lower().count(kw) for kw in NEGATIVE)
                if neg_hits >= 3:
                    print(f"[判定为规则剔除] {url}")
                    continue
                print(f"[缺少订阅特征剔除] {url}")
        except Exception as e:
            print(f"[验证器异常] {url} -> {e}")
            # on validator error, move to pending for retry
            pending.append(url)
            continue
    return kept, pending


def upload_gist_from_file(filepath):
    gid = get_secret("sub-hunter", "GIST_ID")
    tok = get_secret("sub-hunter", "GIST_TOKEN")
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
        headers={
            "Authorization": f"Bearer {tok}",
            "Accept": "application/vnd.github+json",
        },
        json=payload,
        timeout=30,
    )
    return r.ok, r.status_code


# 新增：规范化 URL（去 proxy 包装、把 github.com/raw/... 转为 raw.githubusercontent.com）
def canonicalize_url(url: str) -> str:
    if not url:
        return url
    s = url.strip()
    # 如果内部包含另一个 http(s) 链接（如 proxy/.../https://...），取最后一个
    last_http = max(s.rfind("http://"), s.rfind("https://"))
    if last_http > 0:
        return canonicalize_url(s[last_http:])
    try:
        p = urlparse(s)
        host = (p.netloc or "").lower()
        path = p.path or ""
        
        # 使用智能 GitHub 检测和转换
        username, repo, branch, detected_path = _detect_github_info_from_url(s)
        if username and repo and detected_path:
            converted_url = f"https://raw.githubusercontent.com/{username}/{repo}/{branch}{detected_path}"
            print(f"[智能GitHub转换] {s} -> {converted_url}")
            return converted_url
        
        # GitHub.com raw 地址转换
        if host == "github.com" and "/raw/" in path:
            new_path = path.replace("/raw/refs/heads/", "/")
            new_path = new_path.replace("/raw/refs/", "/")
            new_path = new_path.replace("/raw/", "/")
            converted_url = f"https://raw.githubusercontent.com{new_path}"
            print(f"[GitHub Raw转换] {s} -> {converted_url}")
            return converted_url
    except Exception:
        pass
    return s


# 新增：并发 HEAD 检查（回退到 GET），剔除非 2xx 或 content-type 明显非文本的 URL
def head_check_urls(urls, concurrency=12, timeout=15):
    import concurrent.futures

    import requests

    allowed_text_indicators = (
        "text",
        "json",
        "yaml",
        "xml",
        "plain",
        "javascript",
        "x-yaml",
    )
    disallow_prefix = ("image/", "video/", "audio/")

    session = requests.Session()
    session.headers.update({"User-Agent": "sub-hunter/1.0 (+https://github.com)"})

    ok_list = []
    removed = []

    def _check(u):
        try:
            r = session.head(u, allow_redirects=True, timeout=timeout)
        except Exception:
            try:
                r = session.get(u, allow_redirects=True, stream=True, timeout=timeout)
            except Exception as e:
                return (u, False, f"network:{e}")
        code = getattr(r, "status_code", 0)
        if code < 200 or code >= 300:
            return (u, False, f"status:{code}")
        ctype = (r.headers.get("content-type") or "").lower()
        # 明确：若 Content-Type 为空，则视为不可接受，直接剔除
        if not ctype:
            # 如果 HEAD 没有返回 content-type，尝试 GET 以避免过度剔除（某些服务器在 HEAD 不提供 headers）
            try:
                r_get = session.get(
                    u, allow_redirects=True, stream=True, timeout=timeout
                )
                ctype_get = (r_get.headers.get("content-type") or "").lower()
                if ctype_get:
                    ctype = ctype_get
                    r = r_get
                else:
                    # 读取少量内容判断是否有订阅特征（vmess://, ss://, proxies:, proxy-groups 等）
                    try:
                        snippet = r_get.content[:4096]
                        text = snippet.decode("utf-8", errors="ignore")
                        lower = text.lower()
                        signs = (
                            "proxies:",
                            "proxy-groups",
                            "vmess://",
                            "ss://",
                            "ssr://",
                            "trojan://",
                            "vless://",
                            "hysteria",
                            "tuic",
                        )
                        if any(
                            sig in lower for sig in signs
                        ) or _maybe_base64_subscription(text):
                            return (u, True, f"ok_get_content_snippet:{len(text)}")
                    except Exception:
                        pass
                    return (u, False, "ctype_empty")
            except Exception:
                return (u, False, "ctype_empty_head_get_fail")
        if ctype:
            if any(ctype.startswith(p) for p in disallow_prefix):
                return (u, False, f"ctype_disallowed:{ctype}")
            if not any(k in ctype for k in allowed_text_indicators):
                return (u, False, f"ctype_nontext:{ctype}")
        return (u, True, f"ok:{code}:{ctype}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as ex:
        futs = {ex.submit(_check, u): u for u in urls}
        for fut in concurrent.futures.as_completed(futs):
            try:
                u, ok, reason = fut.result()
            except Exception as e:
                ok = False
                u = futs.get(fut, "<unknown>")
                reason = f"exception:{e}"
            if ok:
                ok_list.append(u)
            else:
                removed.append((u, reason))
    return ok_list, removed


# 新增：对受信任 host 在被判定为“规则/剔除”前做一次 GET 验证
def trusted_verify_single(url: str, timeout: int | None = None):
    """对单个 URL 做 GET 并由 centralized validator 复审。返回 (bool, reason).
    该函数使用已有的 fetch_text 与 filters.validator.is_valid_subscription，以尽量复用项目已有逻辑。
    """
    from filters import validator

    t = timeout or TRUSTED_GET_TIMEOUT
    try:
        text = fetch_text(url, timeout=t)
    except Exception as e:
        print(f"[受信任源GET失败] {url} -> {e}")
        return False, f"fetch_error:{e}"
    if not text or not text.strip():
        return False, "empty"
    try:
        if validator.is_valid_subscription(url, text):
            return True, "validated"
        if _maybe_base64_subscription(text):
            return True, "validated_b64"
    except Exception as e:
        print(f"[受信任源验证异常] {url} -> {e}")
        return False, f"validator_error:{e}"
    return False, "not_subscription"


def main():
    tok = get_secret("sub-hunter", "GITHUB_TOKEN") or get_secret(
        "sub-hunter", "GIST_TOKEN"
    )
    if not tok:
        print("ERROR: no GitHub token in keychain (GITHUB_TOKEN/GIST_TOKEN).")
        sys.exit(2)

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
        ".lock",
        ".cache",
        ".pid",
        ".sock",
        ".out",
        ".err",
        ".log",
        ".tmp",
        ".swp",
        ".swo",
        ".swn",
        ".bak",
        ".old",
        ".orig",
        ".sample",
        ".test",
        ".demo",
        ".example",
        ".template",
        ".config",
        ".settings",
        ".env",
        ".mrs",
        ".list",
        ".html",
        ".ini",
        ".atom",
        ".git",
        ".go",
        ".md",
        ".pdf",
        ".doc",
        ".xls",
        ".ppt",
        ".exe",
        ".apk",
        ".zip",
        ".tar",
        ".gz",
        ".rar",
        ".7z",
        ".bmp",
        ".ttf",
        ".otf",
        ".eot",
        ".mp3",
        ".mp4",
        ".avi",
        ".mov",
        ".mkv",
        ".webm",
        ".json",
        ".xml",
        ".rss",
        ".atom",
        ".map",
        ".psd",
        ".ai",
        ".eps",
        ".dmg",
        ".iso",
        ".bin",
        ".csv",
        ".ts",
        ".tsx",
        ".jsx",
        ".vue",
        ".svelte",
        ".php",
        ".asp",
        ".aspx",
        ".jsp",
        ".cgi",
        ".pl",
        ".rb",
        ".go",
        ".rs",
        ".swift",
        ".kt",
        ".dart",
        ".sh",
        ".bat",
        ".cmd",
        ".ps1",
        ".dockerfile",
        ".gitignore",
        ".gitattributes",
        ".editorconfig",
        ".npmignore",
        ".yarn.lock",
        ".woff2",
        ".ico",
        ".svg",
        ".png",
        ".jpg",
        ".webp",
        ".css",
        ".js",
        ".fonts",
    ]
    KEYWORDS = [
        "subscribe",
        "sub",
        "clash",
        "v2ray",
        "ss",
        "vless",
        "vmess",
        "trojan",
        "hysteria2",
        "tuic",
        "yaml",
        "list",
        "v2",
        "free",
        "public",
        "Router",
    ]
    from filters.extract import SUFFIX_WHITELIST

    def is_subscription_url(url):
        last = url.split("/")[-1].split("?")[0].split("#")[0]
        full_lc = url.lower()
        if any(sub in full_lc for sub in URL_SUBSTR_BLACKLIST):
            print(f"[黑名单URL剔除] {url}")
            return False
        
        # 验证 URL 参数（特别是 token）
        if not _validate_subscription_url_params(url):
            print(f"[无效token剔除] {url}")
            return False
        try:
            from urllib.parse import urlparse

            path = urlparse(url).path.lower()
        except Exception:
            path = ""
        if path.endswith("/releases") or path.endswith("/releases/"):
            print(f"[Releases剔除] {url}")
            return False
        # 0. 先排除EXCLUDE_SUFFIXES（无论是否有后缀）
        for suf in EXCLUDE_SUFFIXES:
            if last.lower().endswith(suf):
                print(f"[排除后缀剔除] {url}")
                return False

        # 新增：基于文件名/路径的黑名单，排除常见的 config/template/dist 等目录或文件名
        NAME_EXCLUDE_TOKENS = (
            "config",
            "clash_config",
            "dist",
            "dist_",
            "template",
            "example",
            "sample",
            "settings",
            "env",
            "ci",
            "docker",
            "init",
            "default",
            "readme",
        )
        # NOTE: do NOT treat generic 'clash' token as subscription indicator here — config files often include 'clash' in name
        SUB_KEYWORDS = (
            "subscribe",
            "subscription",
            "sub",
            "nodes",
            "proxies",
            "proxy",
            "v2ray",
            "vmess",
            "vless",
            "trojan",
            "ss",
            "hysteria",
            "tuic",
            "mix",
            "meta",
            "list",
            "share",
        )
        last_lc = last.lower()
        url_lc = url.lower()
        if ("/dist/" in url_lc) or any(tok in last_lc for tok in NAME_EXCLUDE_TOKENS):
            # 如果 URL 本身没有明显的订阅相关关键词，则认为它是配置/模板文件，剔除
            if not any(k in url_lc for k in SUB_KEYWORDS):
                print(f"[文件名黑名单剔除] {url}")
                return False

        # 1. 后缀为yaml/yml/txt强制保留
        if "." in last:
            suf = last.split(".")[-1].lower()
            if suf in SUFFIX_WHITELIST:
                print(f"[机场订阅保留] {url}")
                return True
        # 2. 无后缀链接，仍需命中关键词（放宽为子串匹配）
        url_lc = url.lower()
        for k in KEYWORDS:
            k_lc = k.lower()
            if k_lc in url_lc:
                print(f"[关键词保留] {url}")
                return True
        # 3. 其余全部剔除 — 在完全剔除前，对受信任的 host 尝试一次 GET 验证以降低误判
        host = ""
        try:
            host = urlparse(url).netloc.lower()
        except Exception:
            host = ""
        if TRUSTED_GET_VERIFY and host in TRUSTED_GET_HOSTS:
            print(f"[受信任源二次GET验证触发] {url}")
            ok, reason = trusted_verify_single(url)
            if ok:
                print(f"[受信任源二次GET验证通过] {url} -> {reason}")
                return True
            else:
                print(f"[受信任源二次GET验证未通过] {url} -> {reason}")
        print(f"[剔除] {url}")
        return False

    urls = []
    for it in items:
        nu = normalize_url(it.get("url"))
        if not nu:
            continue
        # 应用 GitHub Pages 转换
        converted_url = _convert_github_pages_to_raw(nu)
        it["url"] = converted_url
        if is_subscription_url(converted_url):
            urls.append(converted_url)
    print(f"[统计] 抓取总数: {len(items)}，筛选后订阅数: {len(urls)}")

    hist = load_history(HIST_PATH)
    existing_raw = hist.get("seen", []) or []
    existing = []
    for u in existing_raw:
        nu = normalize_url(u)
        if nu:
            existing.append(nu)

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
    # === 新增：对 merged 列表做 owner 级别裁剪，避免历史累积导致单一发布者资源过多 ===
    PER_OWNER_LIMIT = int(os.environ.get("PER_OWNER_LIMIT", "5"))

    def prune_merged_by_owner(merged_list, hist, limit: int):
        res_keys = hist.get("resource_keys", {}) or {}
        # env controls for last-mod sampling during pruning
        PRUNE_LASTMOD_ENABLE = os.environ.get("PRUNE_LASTMOD_ENABLE", "1") in (
            "1",
            "true",
            "True",
        )
        PRUNE_LASTMOD_SAMPLE = int(os.environ.get("PRUNE_LASTMOD_SAMPLE", "10"))
        PRUNE_LASTMOD_CONCURRENCY = int(
            os.environ.get("PRUNE_LASTMOD_CONCURRENCY", "6")
        )
        PRUNE_LASTMOD_TIMEOUT = int(os.environ.get("PRUNE_LASTMOD_TIMEOUT", "6"))
        OWNER_LASTMOD_TRIGGER = int(os.environ.get("OWNER_LASTMOD_TRIGGER", "20"))

        # group urls by owner preserving original order
        owners = {}
        owner_seq = []
        for idx, u in enumerate(merged_list):
            # determine owner via resource_keys if present
            owner = None
            try:
                meta = res_keys.get(u)
                if meta and meta.get("owner_key"):
                    owner = meta.get("owner_key")
            except Exception:
                owner = None
            if not owner:
                try:
                    owner, _ = get_resource_key(u)
                except Exception:
                    owner = "__no_owner__"
            if owner not in owners:
                owners[owner] = []
                owner_seq.append(owner)
            owners[owner].append((u, idx))

        out = []
        skipped_total = 0

        for owner in owner_seq:
            items = owners[owner]
            if len(items) <= limit:
                # small owners keep all
                out.extend([u for u, _ in items])
                continue

            # If last-mod sampling enabled, sample up to PRUNE_LASTMOD_SAMPLE candidates (head of owner's list)
            if PRUNE_LASTMOD_ENABLE and len(items) > OWNER_LASTMOD_TRIGGER:
                # cache TTL for lastmod (seconds)
                LASTMOD_CACHE_TTL = int(os.environ.get("LASTMOD_CACHE_TTL", "86400"))
                now_ts = int(time.time())
                # decide which URLs actually need sampling (missing or stale cache)
                to_sample = []
                sample_candidates = [u for u, _ in items[:PRUNE_LASTMOD_SAMPLE]]
                for u in sample_candidates:
                    cached = None
                    try:
                        cached = hist.get("resource_keys", {}).get(u, {}).get("lastmod")
                    except Exception:
                        cached = None
                    if not cached or (now_ts - int(cached) > LASTMOD_CACHE_TTL):
                        to_sample.append(u)

                lm_map = {}
                if to_sample:
                    # avoid re-sampling same URL globally in this run
                    try:
                        lm_map = sample_last_modified(
                            to_sample,
                            concurrency=PRUNE_LASTMOD_CONCURRENCY,
                            timeout=PRUNE_LASTMOD_TIMEOUT,
                        )
                    except Exception as e:
                        print(f"[LastMod采样异常] {e}")
                        lm_map = {}

                # build enriched list with timestamps from sampled results or cache
                enriched = []
                for u, idx in items:
                    ts = None
                    if u in lm_map and lm_map[u] is not None:
                        ts = lm_map[u]
                        hist.setdefault("resource_keys", {})
                        hist["resource_keys"].setdefault(u, {})
                        hist["resource_keys"][u]["lastmod"] = ts
                    else:
                        try:
                            ts = hist.get("resource_keys", {}).get(u, {}).get("lastmod")
                        except Exception:
                            ts = None
                    ts_val = int(ts) if ts else 0
                    enriched.append((u, ts_val, idx))

                # persist cache to disk to reduce future sampling
                try:
                    save_history(hist, HIST_PATH)
                except Exception as e:
                    print(f"[保存 LastMod 缓存失败] {e}")

                # sort by lastmod desc, then original index
                enriched.sort(key=lambda t: (-t[1], t[2]))
                # choose top N
                chosen_urls = [t[0] for t in enriched[:limit]]
                out.extend(chosen_urls)
                # count skipped items for reporting
                skipped_total += max(0, len(items) - len(chosen_urls))
            else:
                # Fallback when last-mod sampling is disabled or owner list is not large enough for sampling.
                # Preserve the first `limit` items in original order to avoid accidental data loss.
                chosen_urls = [u for u, _ in items[:limit]]
                out.extend(chosen_urls)
                skipped_total += max(0, len(items) - len(chosen_urls))

        if skipped_total:
            print(f"[裁剪历史] 共跳过 {skipped_total} 条 (每发布者限 {limit})")
        return out

    merged_pruned = prune_merged_by_owner(merged, hist, PER_OWNER_LIMIT)
    print(f"[统计] 裁剪后待检测数: {len(merged_pruned)} (原始 {len(merged)})")
    merged = merged_pruned
    if not merged:
        print(">>> 无可检测链接，跳过连通性检测和 Gist 上传！")
        return

    print(">>> 连通性检测…")
    ok = asyncio.run(check_urls(merged, concurrency=16))
    print(f"[统计] 可用订阅链接: {len(ok)}")

    filtered_ok, pending = filter_subscription_content(ok)
    print(f"[统计] 内容校验后保留: {len(filtered_ok)} | 待重试: {len(pending)}")

    if pending:
        print(">>> 对内容获取失败链接进行二次尝试…")
        retried_ok = []
        for url in pending:
            try:
                text = fetch_text(url, timeout=45)
            except Exception:
                print(f"[二次尝试失败] {url}")
                continue
            snippet = text.strip()
            if not snippet:
                print(f"[二次尝试内容为空] {url}")
                continue
            lower = snippet.lower()
            if any(
                sig in lower
                for sig in (
                    "proxies:",
                    "proxy-groups",
                    "vmess://",
                    "ss://",
                    "ssr://",
                    "trojan://",
                    "vless://",
                    "hysteria",
                    "tuic",
                )
            ) or _maybe_base64_subscription(snippet):
                retried_ok.append(url)
            else:
                print(f"[二次尝试缺少特征] {url}")
        if retried_ok:
            print(f"[统计] 二次尝试成功: {len(retried_ok)}")
            filtered_ok.extend(retried_ok)

    # 使用 ensure_increment 对历史进行每日增量/淘汰处理并写回统一的 hist_path
    # ---------------
    # 在写入前执行：
    # 1) 使用 gather 到 items 中的 owner/path 信息做 owner+base 去重；
    # 2) canonicalize URL（去 proxy 包装并规范 github raw）；
    # 3) 优先保留 .txt，按 host 优先级选择 canonical 版本；
    # 4) 对最终候选并发 HEAD 检查，剔除非 2xx/非文本的 URL；
    # 5) 把通过的 URL 写回历史（ensure_increment）和 output 文件。
    # ---------------

    # 构建 url -> {owner,path} 映射（items 来自 gather_candidates，包含 owner/path）
    cand_map = {}
    for entry in items:
        u0 = normalize_url(entry.get("url") or "")
        if not u0:
            continue
        cand_map[u0] = {
            "owner": entry.get("owner") or "__no_owner__",
            "path": entry.get("path") or u0,
        }

    def strip_known_ext(u: str) -> str:
        low = u.lower()
        for ext in (".yaml", ".yml", ".txt"):
            if low.endswith(ext):
                return u[: -len(ext)]
        return u

    host_priority = [
        "raw.githubusercontent.com",
        "cdn.jsdelivr.net",
        "raw.fastgit.org",
        "ghproxy.net",
        "proxy.v2gh.com",
        "github.com",
    ]

    def host_rank(u: str) -> int:
        try:
            h = urlparse(u).netloc.lower()
        except Exception:
            h = ""
        for idx, name in enumerate(host_priority):
            if name in h:
                return idx
        return len(host_priority)

    # canonicalize 并按 owner+base 分组
    groups = {}
    for u in filtered_ok:
        orig = u
        canon = canonicalize_url(orig)
        meta = (
            cand_map.get(normalize_url(orig))
            or cand_map.get(normalize_url(canon))
            or {"owner": "__no_owner__", "path": orig}
        )
        owner = meta.get("owner") or "__no_owner__"
        base = strip_known_ext(canon)
        groups.setdefault((owner, base), []).append(canon)

    chosen = []
    for key, lst in groups.items():
        # 保持稳定顺序并去重
        lst = list(dict.fromkeys(lst))
        if len(lst) == 1:
            chosen.append(lst[0])
            continue
        # 优先 .txt
        txts = [v for v in lst if v.lower().endswith(".txt")]
        if txts:
            chosen.append(txts[0])
            for v in lst:
                if v != txts[0]:
                    print(f"[发布者同名去重] 保留：{txts[0]}，剔除：{v}")
            continue
        # 否则按 host 优先级排序
        lst.sort(key=lambda v: (host_rank(v), v))
        chosen.append(lst[0])
        for v in lst[1:]:
            print(f"[发布者同名去重] 保留：{lst[0]}，剔除：{v}")

    # 最终 HEAD 检查
    print(">>> 最终可用性校验（HEAD content-type）...")
    ok_head, removed_head = head_check_urls(chosen, concurrency=16, timeout=15)
    for u, reason in removed_head:
        print(f"[可用性剔除] {u} -> {reason}")

    # persist removed list for audit
    os.makedirs("output", exist_ok=True)
    removed_file = os.path.join("output", "subs_removed.txt")
    with open(removed_file, "w", encoding="utf-8") as rf:
        for u, reason in removed_head:
            line = f"[可用性剔除] {u}\t{reason}\n"
            rf.write(line)
            print(line, end="")
    # also persist other rejection logs captured earlier via printed messages is difficult; we ensure
    # filter_subscription_content writes its own logs; here we dump the final removed_head for audit

    # 为历史保存构建 resource_map（url -> {owner_key, base}），便于长期去重追踪
    resource_map = {}
    for u in ok_head:
        # 尝试使用候选映射中的 owner 信息作为 get_resource_key 的 owner_from_meta
        meta = cand_map.get(normalize_url(u)) or {}
        owner_meta = meta.get("owner") if meta else None
        owner_key, base = get_resource_key(u, owner_meta)
        resource_map[u] = {"owner_key": owner_key, "base": base}

    # 写回历史与输出（把 resource_map 传入 ensure_increment）
    all_urls = ensure_increment(
        ok_head, HIST_PATH, DAILY_INCREMENT, FAIL_THRESHOLD, resource_map=resource_map
    )
    print(f"[统计] 本次全量覆盖: {len(all_urls)} 条")

    os.makedirs("output", exist_ok=True)
    with open("output/subs_latest.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(all_urls))
    print(">>> 已写入 output/subs_latest.txt")

    if len(all_urls) == 0:
        print(">>> 订阅链接数量为0，跳过 Gist 上传！")
        return

    ok_up, code = upload_gist_from_file("output/subs_latest.txt")
    print(f">>> Gist上传: {ok_up} ({code})")


# 新增：在 main() 之前定义资源键提取函数，避免运行时 NameError
def extract_github_owner_repo_path(url: str):
    """Try to extract (owner/repo, path_without_ext) for common GitHub/CDN forms.
    Returns (owner_repo, base_path) or (None, None) if not recognized.
    """
    try:
        p = urlparse(url)
        host = (p.netloc or "").lower()
        path = (p.path or "").lstrip("/")
        parts = path.split("/")
        # raw.githubusercontent.com/{owner}/{repo}/{branch}/path...
        if host == "raw.githubusercontent.com" and len(parts) >= 3:
            owner = parts[0]
            repo = parts[1]
            rel = "/".join(parts[2:])
            base = rel.rsplit(".", 1)[0] if "." in rel else rel
            return f"{owner}/{repo}", base
        # github.com/{owner}/{repo}/raw/{branch}/path...
        if host == "github.com" and len(parts) >= 4 and "raw" in parts:
            # find raw index
            idx = parts.index("raw")
            if idx >= 2 and len(parts) > idx + 1:
                owner = parts[0]
                repo = parts[1]
                rel = "/".join(parts[idx + 1 :])
                base = rel.rsplit(".", 1)[0] if "." in rel else rel
                return f"{owner}/{repo}", base
        # jsdelivr gh pattern: /gh/{owner}/{repo}/{branch}/path  or /gh/{owner}/{repo}@{ver}/path
        if host.endswith("cdn.jsdelivr.net") and parts and parts[0] in ("gh", "ghcdn"):
            # /gh/{owner}/{repo}/{branch}/...
            if len(parts) >= 4:
                owner = parts[1]
                repo = parts[2]
                rel = "/".join(parts[3:])
                base = rel.rsplit(".", 1)[0] if "." in rel else rel
                return f"{owner}/{repo}", base
            # /gh/{owner}/{repo}@ver/...
            if len(parts) >= 3 and "@" in parts[2]:
                owner = parts[1]
                repo = parts[2].split("@", 1)[0]
                rel = "/".join(parts[3:])
                base = rel.rsplit(".", 1)[0] if "." in rel else rel
                return f"{owner}/{repo}", base
    except Exception:
        pass
    return None, None


def get_resource_key(url: str, owner_from_meta: str | None = None):
    """Return a stable (owner_key, base_path) used for deduplication.
    Prefer explicit GitHub owner/repo extraction; fall back to provided owner or host+path base.
    """
    canon = canonicalize_url(url)
    owner_repo, base = extract_github_owner_repo_path(canon)
    if owner_repo:
        return owner_repo, base
    # if we have owner metadata from gather_candidates, use it
    if owner_from_meta and owner_from_meta != "__no_owner__":
        # use owner + base path of URL (without branch) to group
        try:
            p = urlparse(canon)
            rel = (p.path or "").lstrip("/")
            base = rel.rsplit(".", 1)[0] if "." in rel else rel
            return owner_from_meta, base
        except Exception:
            return owner_from_meta, canon
    # generic fallback: host + path base
    try:
        p = urlparse(canon)
        host = (p.netloc or "").lower()
        rel = (p.path or "").lstrip("/")
        base = rel.rsplit(".", 1)[0] if "." in rel else rel
        return host, base
    except Exception:
        return canon, canon


def _parse_last_modified(h: str):
    try:
        from email.utils import parseddate_to_datetime

        dt = parseddate_to_datetime(h)
        # normalize to timestamp
        return int(dt.timestamp())
    except Exception:
        return None


def _detect_github_info_from_url(url: str) -> tuple:
    """
    智能检测 URL 中的 GitHub 信息，返回 (username, repo, branch, path)
    支持各种 GitHub 相关的域名和CDN代理
    """
    try:
        p = urlparse(url)
        host = p.netloc.lower()
        path = p.path or ""
        
        # 1. 标准 GitHub Pages: *.github.io
        if host.endswith(".github.io"):
            username = host.replace(".github.io", "")
            if username:
                return username, f"{username}.github.io", "main", path
        
        # 2. jsdelivr CDN: cdn.jsdelivr.net/gh/user/repo
        if host == "cdn.jsdelivr.net" and path.startswith("/gh/"):
            parts = path[4:].split("/")  # 移除 "/gh/"
            if len(parts) >= 2:
                user = parts[0]
                repo = parts[1]
                if "@" in repo:
                    repo, branch = repo.split("@", 1)
                else:
                    branch = "main"
                remaining_path = "/" + "/".join(parts[2:]) if len(parts) > 2 else ""
                return user, repo, branch, remaining_path
        
        # 3. 其他可能的 GitHub Pages 代理域名
        # 通过路径模式识别：包含 /uploads/YYYY/MM/ 这种典型的 GitHub Pages 模式
        github_page_patterns = [
            r"/uploads/\d{4}/\d{2}/[^/]+\.(txt|yaml|yml)$",  # /uploads/2025/10/file.txt
            r"/\d{4}/\d{2}/[^/]+\.(txt|yaml|yml)$",           # /2025/10/file.txt  
            r"/files/[^/]+\.(txt|yaml|yml)$",                 # /files/file.txt
            r"/raw/[^/]+\.(txt|yaml|yml)$",                   # /raw/file.txt
        ]
        
        for pattern in github_page_patterns:
            if re.search(pattern, path):
                # 尝试从域名推断 GitHub 用户名
                # 很多 GitHub Pages 使用自定义域名，但域名通常包含用户名信息
                
                # 方法1: 提取域名中可能的用户名（去掉常见后缀）
                domain_parts = host.split('.')
                if len(domain_parts) >= 2:
                    # 移除常见的CDN/代理标识，尝试多种组合
                    potential_usernames = []
                    
                    # 原始第一部分
                    first_part = domain_parts[0]
                    
                    # 尝试不同的清理方式
                    candidates = [
                        first_part,  # 原始
                        re.sub(r'^(www|cdn|api|node|free|sub|clash)[-_]?', '', first_part),  # 移除前缀
                        re.sub(r'[-_]?(node|cc|site|net|page|cdn)$', '', first_part),      # 移除后缀
                        re.sub(r'^(www|cdn|api|node|free|sub|clash)[-_]?', '', 
                               re.sub(r'[-_]?(node|cc|site|net|page|cdn)$', '', first_part)) # 移除前缀+后缀
                    ]
                    
                    # 特殊处理：如果是 node.xxxxx.cc 格式，优先使用中间部分作为用户名
                    if len(domain_parts) >= 2:
                        # 对于二级域名，检查第一部分是否为常见前缀
                        if len(domain_parts) == 3 and first_part in ['node', 'api', 'cdn', 'sub', 'www']:
                            middle_part = domain_parts[1]
                            # 将完整的中间部分放在最前面（优先级最高）
                            candidates.insert(0, middle_part)
                            
                        # 对于所有情况，也尝试使用二级域名的第一部分
                        if len(domain_parts) >= 2:
                            second_level = domain_parts[-2] if len(domain_parts) >= 2 else domain_parts[0]
                            if second_level != first_part:  # 避免重复
                                candidates.insert(0, second_level)
                    
                    # 选择最佳候选用户名（按优先级顺序）
                    for candidate in candidates:
                        if candidate and len(candidate) >= 3 and re.match(r'^[a-zA-Z0-9][a-zA-Z0-9_-]*[a-zA-Z0-9]$', candidate):
                            return candidate, f"{candidate}.github.io", "main", path
        
        return None, None, None, None
    except Exception:
        return None, None, None, None


def _convert_github_pages_to_raw(url: str) -> str:
    """
    智能转换各种 GitHub Pages 和 CDN 地址为 raw.githubusercontent.com 地址
    支持：
    1. *.github.io
    2. cdn.jsdelivr.net/gh/user/repo  
    3. 自定义域名的 GitHub Pages（通过路径模式识别）
    """
    username, repo, branch, path = _detect_github_info_from_url(url)
    
    if username and repo and path:
        converted_url = f"https://raw.githubusercontent.com/{username}/{repo}/{branch}{path}"
        print(f"[智能GitHub转换] {url} -> {converted_url}")
        return converted_url
    
    return url


def sample_last_modified(urls, concurrency=8, timeout=6):
    """并发对一组 URL 做 HEAD（回退 GET）请求，提取 Last-Modified header 的时间戳。
    返回 dict: url -> unix_ts 或 None
    """
    import concurrent.futures

    import requests

    sess = requests.Session()
    sess.headers.update({"User-Agent": "sub-hunter/lastmod/1.0"})

    def _one(u: str):
        try:
            r = sess.head(u, allow_redirects=True, timeout=timeout)
        except Exception:
            try:
                r = sess.get(u, allow_redirects=True, stream=True, timeout=timeout)
            except Exception:
                return u, None
        lm = r.headers.get("Last-Modified") or r.headers.get("last-modified")
        if lm:
            ts = _parse_last_modified(lm)
            return u, ts
        return u, None

    out = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as ex:
        futs = {ex.submit(_one, u): u for u in urls}
        for fut in concurrent.futures.as_completed(futs):
            try:
                u, ts = fut.result()
            except Exception:
                u, ts = futs.get(fut, "<unknown>"), None
            out[u] = ts
    return out


# Ensure script entrypoint exists so running the file executes main()
if __name__ == "__main__":
    main()
