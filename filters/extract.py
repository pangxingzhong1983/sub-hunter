import re

from utils.http_client import request

_HEAD_TRIM = "([\"'`《〈「『【（“”"
_TAIL_TRIM = ")>\"'`，。、；：！？》〉」』】）“”"


def normalize_url(url: str) -> str:
    if not url:
        return ""
    u = url.strip()
    u = u.lstrip(_HEAD_TRIM)
    u = u.rstrip(_TAIL_TRIM)
    return u


URL_RE = re.compile(r'https?://[^\s"\'<>]+', re.IGNORECASE)
KEYS = ("clash", "mihomo", "v2ray", "sub", "subscribe", "subconverter")

EXT_KEYS = [
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
]
# 后缀白名单：只要后缀为这些，直接保留，无需关键词
SUFFIX_WHITELIST = ["yaml", "yml", "txt"]

# 超时/限流
FETCH_TIMEOUT = 10  # 单文件最大10s
MAX_BYTES = 256 * 1024  # 最多读取256KB，防止大文件卡住


def fetch_text(url: str, timeout: int = FETCH_TIMEOUT) -> str:
    r = request("GET", url, timeout=timeout)
    r.raise_for_status()
    ct = (r.headers.get("content-type") or "").lower()
    # 仅处理文本类
    if any(k in ct for k in ("text", "yaml", "json")):
        text = r.text
        # 截断超长
        return text[:MAX_BYTES]
    # 二进制兜底尝试
    try:
        return r.content[:MAX_BYTES].decode("utf-8", "ignore")
    except Exception:
        return ""


def extract_candidate_urls(text: str):
    # 放宽规则：只要包含 clash/v2ray/ss/trojan/subscribe/sub/节点/机场/分流/规则/配置/免费/订阅/链接/地址/源/转换/分享/分组
    for raw in URL_RE.findall(text or ""):
        u = normalize_url(raw)
        if not u:
            continue
        lu = u.lower()
        last = lu.split("/")[-1].split("?")[0].split("#")[0]
        # 后缀白名单，yaml/yml/txt直接保留
        if "." in last:
            suf = last.split(".")[-1]
            if suf in SUFFIX_WHITELIST:
                yield u
                continue
        if any(k in lu for k in EXT_KEYS):
            yield u
