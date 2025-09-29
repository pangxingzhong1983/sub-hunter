import base64, yaml, re, json, os, socket

# 可调阈值（环境变量覆盖）
MIN_V2_LINKS = int(os.environ.get("MIN_V2_LINKS", "1"))
MIN_CLASH_PROXIES = int(os.environ.get("MIN_CLASH_PROXIES", "1"))
MIN_BODY_LENGTH = int(os.environ.get("MIN_BODY_LENGTH", "30"))

# 协议前缀列表，用于快速计数
_PROTOCOL_PREFIXES = [r"vmess://", r"vless://", r"trojan://", r"ss://", r"ssr://"]
_HTML_TAG_RE = re.compile(r"<\s*html|<\s*doctype|<\s*head|<\s*body", re.I)
_ERROR_SIGNS = re.compile(r"(404\s+not\s+found|page\s+not\s+found|access\s+denied|403\s+forbidden|captcha|sign\s*in|required\s*login|permission\s+denied)", re.I)

# 样本连通性检测开关与参数（环境变量控制）
ENABLE_SAMPLE_NODE_CHECK = os.environ.get("ENABLE_SAMPLE_NODE_CHECK", "0") in ("1", "true", "True")
SAMPLE_NODE_CHECK_COUNT = int(os.environ.get("SAMPLE_NODE_CHECK_COUNT", "1"))
SAMPLE_NODE_CHECK_TIMEOUT = int(os.environ.get("SAMPLE_NODE_CHECK_TIMEOUT", "2"))


def _count_protocol_links(text: str) -> int:
    """统计文本中常见代理协议前缀出现的次数。"""
    cnt = 0
    # 先处理 vmess：逐条匹配并解析验证
    for m in re.finditer(r"vmess://[A-Za-z0-9+/=]{8,}", text, re.I):
        seg = m.group(0)
        if _is_valid_vmess_link_segment(seg):
            cnt += 1
    # 其它协议使用普通计数
    for p in (r"vless://", r"trojan://", r"ss://", r"ssr://"):
        cnt += len(re.findall(p, text, re.I))
    return cnt


def _is_html_page(text: str) -> bool:
    """简单判断是否为 HTML 页面（而非订阅内容）。"""
    if _HTML_TAG_RE.search(text):
        # 进一步排除包含真实协议的页面（有时候 HTML 页面内嵌订阅链接）
        return _count_protocol_links(text) == 0
    return False


def _contains_error_message(text: str) -> bool:
    """检测页面是否包含明显的错误/登录/限制提示。"""
    return bool(_ERROR_SIGNS.search(text))


def looks_like_clash_yaml(text: str) -> bool:
    """更严格地判断是否为有效的 Clash YAML 订阅。
    要求：解析为 dict，包含 proxies/proxy-groups/proxy-providers 其中之一，且 proxies 数量 >= MIN_CLASH_PROXIES。
    """
    try:
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            return False

        # 直接含 proxies 的情况
        if "proxies" in data and isinstance(data["proxies"], list):
            return len(data["proxies"]) >= MIN_CLASH_PROXIES

        # proxy-providers 可能是 dict，每个 provider 里可能定义 proxies 或者 provider 会包含 url/proxies 字段
        if "proxy-providers" in data and isinstance(data["proxy-providers"], dict):
            # 如果任意 provider 的 proxies 字段为非空 list，则视为有效
            for prov in data["proxy-providers"].values():
                if isinstance(prov, dict):
                    if "proxies" in prov and isinstance(prov["proxies"], list) and len(prov["proxies"]) >= MIN_CLASH_PROXIES:
                        return True
            # 不能保证内嵌 proxies 的情况下，仍可被认为是 clash-yaml，但更谨慎返回 False
            return False

        # proxy-groups 存在但不含 proxies 列表时不算有效订阅
        return False
    except Exception:
        return False


def looks_like_v2_text(text: str) -> bool:
    """判断文本中是否包含足够数量的 v2 协议链接。
    - 排除明显的 HTML 页面或错误页面
    - 要求协议前缀出现次数 >= MIN_V2_LINKS
    """
    if not text or len(text) < MIN_BODY_LENGTH:
        return False
    if _is_html_page(text):
        return False
    if _contains_error_message(text):
        return False
    return _count_protocol_links(text) >= MIN_V2_LINKS


def looks_like_b64_subscription(text: str) -> bool:
    """尝试解码 Base64 订阅，并在解码后以更严格的方式判断其是否包含代理链接或 Clash YAML。
    对于解码后的纯文本订阅，不再严格依赖 MIN_BODY_LENGTH（Base64 经常只包含少量节点），而是直接统计协议前缀。
    """
    try:
        raw = base64.b64decode(text.strip(), validate=False)
        decoded = raw.decode(errors="ignore")
        # 如果解码后是 YAML，优先使用 YAML 检查
        if decoded.strip().startswith("{") or decoded.strip().startswith("-") or "proxies" in decoded:
            if looks_like_clash_yaml(decoded):
                return True
        # 排除明显的 HTML 或错误页面
        if _is_html_page(decoded) or _contains_error_message(decoded):
            return False
        # 对解码后的纯文本，直接统计协议前缀数，允许较短文本
        return _count_protocol_links(decoded) >= 1
    except Exception:
        return False


def is_valid_subscription(url: str, body: str) -> bool:
    """综合判断一个抓到的 URL 内容是否为真实的订阅。

    规则摘要：
    - 对以 .yaml/.yml 结尾的 URL：要求解析为 Clash YAML 且包含足够的 proxies
    - 对以 .txt 结尾的 URL：要求包含足够的 v2 协议链接或为 Base64 包裹的订阅
    - 对路径以 /sub 或以 =sub 结尾的 URL：进行综合检测，排除 HTML/登录/错误页面
    - 其他情况：谨慎拒绝（保持严格）
    """
    if not body or len(body.strip()) < MIN_BODY_LENGTH:
        return False

    u = url.lower()
    try:
        if u.endswith((".yaml", ".yml")):
            return looks_like_clash_yaml(body)

        if u.endswith(".txt"):
            # .txt 既可能是纯文本协议，也可能是 base64
            if looks_like_v2_text(body):
                return True
            return looks_like_b64_subscription(body)

        if u.endswith("/sub") or u.endswith("=sub"):
            # 可能返回 YAML、纯文本或 Base64，先排除常见的 HTML/错误提示页
            if _is_html_page(body) or _contains_error_message(body):
                return False
            # 再分别尝试各种检测方法
            if looks_like_clash_yaml(body):
                return True
            if looks_like_v2_text(body):
                return True
            if looks_like_b64_subscription(body):
                return True
            return False

        # 默认更严格：只有当 body 明显包含协议时才通过
        if looks_like_v2_text(body) or looks_like_b64_subscription(body) or looks_like_clash_yaml(body):
            if ENABLE_SAMPLE_NODE_CHECK:
                # 如果启用了样本检测，则要求至少有一个样本节点连通
                if _sample_node_check(body):
                    return True
                return False
            return True
    except Exception:
        return False

    return False


def _is_valid_vmess_link_segment(segment: str) -> bool:
    """判断一个 vmess:// 后面跟随的 segment 是否为合法的 vmess base64-json。
    返回 True 当且仅当能解析出 JSON，且包含必要字段（address/add, port, id/uuid）。
    """
    try:
        # 尝试从 segment 中截取连续的 base64 部分
        m = re.match(r"^vmess://([A-Za-z0-9+/=]+)$", segment.strip())
        if not m:
            # 有时候 vmess 在文本中后面跟着参数或换行，尝试查找 base64 子串
            m2 = re.search(r"vmess://([A-Za-z0-9+/=]{16,})", segment, re.I)
            if not m2:
                return False
            b64 = m2.group(1)
        else:
            b64 = m.group(1)

        raw = base64.b64decode(b64, validate=False)
        data = None
        try:
            data = json.loads(raw.decode(errors="ignore"))
        except Exception:
            # 有些 vmess 链接会直接以 URL 的 query 形式出现，不在 JSON 范式下
            return False

        if not isinstance(data, dict):
            return False
        # 常见字段： add (address), port, id (uuid) / ps (备注)
        addr = data.get("add") or data.get("host") or data.get("server")
        port = data.get("port")
        uid = data.get("id") or data.get("uuid")
        if addr and port and uid:
            return True
    except Exception:
        return False
    return False


def _extract_node_hosts(text: str) -> list[tuple]:
    """从文本中抽取若干 host, port tuples。
    支持：
    - vmess://<base64-json> 中的 add + port
    - vless://uuid@host:port 或 trojan://pass@host:port
    返回格式 [(host, port), ...]
    """
    hosts = []
    try:
        # vmess JSON 提取
        for m in re.finditer(r"vmess://([A-Za-z0-9+/=]{8,})", text, re.I):
            b64 = m.group(1)
            try:
                raw = base64.b64decode(b64, validate=False)
                data = json.loads(raw.decode(errors="ignore"))
                addr = data.get("add") or data.get("host") or data.get("server")
                port = data.get("port")
                if addr and port:
                    hosts.append((addr, int(port)))
            except Exception:
                continue

        # vless/trojan 的简单正则 host:port 提取
        for m in re.finditer(r"(?:vless|trojan)://[^@\s@]+@([^:/\s:?#]+):(\d+)", text, re.I):
            h = m.group(1)
            p = int(m.group(2))
            hosts.append((h, p))
    except Exception:
        pass
    return hosts


def _sample_node_check(text: str, count: int = SAMPLE_NODE_CHECK_COUNT, timeout: int = SAMPLE_NODE_CHECK_TIMEOUT) -> bool:
    """对抽取到的若干节点尝试建立短 TCP 连接，任意一个成功即认为订阅至少包含活节点。
    该检查可能会被防火墙拦截或触发更高的网络延迟，因此默认关闭（需通过环境变量显式开启）。
    """
    hosts = _extract_node_hosts(text)
    if not hosts:
        return False
    tried = 0
    for (h, p) in hosts:
        if tried >= count:
            break
        tried += 1
        try:
            # 尝试建立短连接
            with socket.create_connection((h, p), timeout=timeout):
                return True
        except Exception:
            continue
    return False
