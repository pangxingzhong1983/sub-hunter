import re
from utils.http_client import request

URL_RE = re.compile(r'https?://[^\s"\'<>]+', re.IGNORECASE)
KEYS   = ("clash","mihomo","v2ray","sub","subscribe","subconverter")

# 超时/限流
FETCH_TIMEOUT = 10      # 单文件最大10s
MAX_BYTES     = 256*1024  # 最多读取256KB，防止大文件卡住

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
        return r.content[:MAX_BYTES].decode("utf-8","ignore")
    except Exception:
        return ""

def extract_candidate_urls(text: str):
    for u in URL_RE.findall(text or ""):
        lu = u.lower()
        if any(k in lu for k in KEYS):
            yield u
