import requests

def sanitize_header(v: str) -> str:
    """清理掉 Token 里的不可见字符，确保能作为 HTTP Header"""
    return ''.join(ch for ch in v if ord(ch) < 128)

def update_gist(gist_id, gist_token, filename, content):
    api = f"https://api.github.com/gists/{gist_id}"
    payload = {"files": {filename: {"content": content}}}
    headers = {
        "Authorization": "token " + sanitize_header(gist_token),
        "Accept": "application/vnd.github+json"
    }
    r = requests.patch(api, headers=headers, json=payload, timeout=30)
    return r.status_code
