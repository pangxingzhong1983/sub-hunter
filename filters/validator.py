import base64, yaml, re

def looks_like_clash_yaml(text:str) -> bool:
    try:
        data = yaml.safe_load(text)
        if not isinstance(data, dict): return False
        return any(k in data for k in ("proxies","proxy-groups","proxy-providers"))
    except Exception:
        return False

def looks_like_v2_text(text:str) -> bool:
    return bool(re.search(r"(vmess://|vless://|trojan://|ss://)", text, re.I))

def looks_like_b64_subscription(text:str) -> bool:
    try:
        raw = base64.b64decode(text.strip(), validate=False)
        return looks_like_v2_text(raw.decode(errors="ignore"))
    except Exception:
        return False

def is_valid_subscription(url:str, body:str) -> bool:
    u = url.lower()
    if u.endswith((".yaml",".yml")): return looks_like_clash_yaml(body)
    if u.endswith(".txt"):           return looks_like_v2_text(body) or looks_like_b64_subscription(body)
    if u.endswith("/sub") or u.endswith("=sub"):
        # 可能是YAML/文本/Base64，综合判断
        return looks_like_clash_yaml(body) or looks_like_v2_text(body) or looks_like_b64_subscription(body)
    return False
