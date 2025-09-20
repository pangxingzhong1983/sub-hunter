import time, urllib.parse, os
import requests, urllib3, certifi
from typing import Optional, Dict, Any
from utils.rate_limiter import limiter
from config.rate_limits import MAX_BACKOFF, MAX_RETRIES

urllib3.disable_warnings()
UA = "sub-hunter/1.0"
CA_BUNDLE = certifi.where()

def _host(url: str) -> str:
    return urllib.parse.urlsplit(url).hostname or ""

def _sleep_from_headers(resp: requests.Response):
    ra = resp.headers.get("Retry-After")
    if ra:
        try: return float(ra)
        except ValueError: pass
    xr = resp.headers.get("X-RateLimit-Reset")
    if xr:
        try:
            import time as _t
            return max(0.0, int(xr) - _t.time())
        except ValueError:
            pass
    return None

def _build_http_proxies() -> Dict[str,str]:
    # 默认不设置代理，完全走系统环境
    hp = os.environ.get("HTTP_PROXY")  or os.environ.get("http_proxy")
    sp = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    proxies = {}
    if hp: proxies["http"] = hp
    if sp: proxies["https"] = sp
    return proxies

def request(method: str, url: str, *, headers: Dict[str,str]=None,
            params: Dict[str,Any]=None, data: Any=None, json: Any=None,
            timeout: float=20, token: Optional[str]=None, retries: int=MAX_RETRIES) -> requests.Response:
    headers = dict(headers or {})
    headers.setdefault("User-Agent", UA)
    if token and "Authorization" not in headers:
        headers["Authorization"] = f"Bearer {token}"

    proxies = _build_http_proxies()
    host = _host(url)
    backoff = 1.0
    last_resp = None
    tried_insecure = False

    for attempt in range(retries+1):
        limiter.acquire(host)
        try:
            resp = requests.request(
                method.upper(), url,
                headers=headers, params=params, data=data, json=json,
                timeout=timeout, verify=CA_BUNDLE, proxies=proxies
            )
        except requests.exceptions.SSLError:
            if not tried_insecure:
                tried_insecure = True
                resp = requests.request(
                    method.upper(), url,
                    headers=headers, params=params, data=data, json=json,
                    timeout=timeout, verify=False, proxies=proxies
                )
            else:
                raise

        last_resp = resp
        if resp.status_code < 400:
            return resp

        if resp.status_code in (403, 429):
            wait = _sleep_from_headers(resp)
            if wait is None:
                wait = min(backoff, MAX_BACKOFF); backoff *= 2
            time.sleep(wait); continue

        if 500 <= resp.status_code < 600 and attempt < retries:
            wait = min(backoff, MAX_BACKOFF); backoff *= 2
            time.sleep(wait); continue

        return resp
    return last_resp
