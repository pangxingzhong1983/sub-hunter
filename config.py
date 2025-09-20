import os

# ===== 基本配置 =====
KEYWORDS = [
    "free v2ray", "free clash", "free vpn",
    "free nodes", "免费 订阅", "clash subscribe"
]

MAX_WORKERS   = int(os.environ.get("MAX_WORKERS", "20"))
DAILY_INCREMENT = int(os.environ.get("DAILY_INCREMENT", "10"))
FAIL_THRESHOLD  = int(os.environ.get("FAIL_THRESHOLD", "3"))

OUT_DIR   = os.path.abspath(os.environ.get("OUT_DIR", "./data"))
OUT_FILE  = os.path.join(OUT_DIR, "zhuquejisu.txt")
HIST_PATH = os.path.join(OUT_DIR, "history.json")

FILENAME_IN_GIST = "zhuquejisu.txt"

# 令牌读取：优先钥匙串，其次环境变量
def get_github_token():
    try:
        from storage.secure import get_secret
        return get_secret("sub-hunter", "GH_TOKEN") or os.environ.get("GH_TOKEN","")
    except Exception:
        return os.environ.get("GH_TOKEN","")

def get_gist_id():
    try:
        from storage.secure import get_secret
        return get_secret("sub-hunter", "GIST_ID") or os.environ.get("GIST_ID","")
    except Exception:
        return os.environ.get("GIST_ID","")

def get_gist_token():
    try:
        from storage.secure import get_secret
        return get_secret("sub-hunter", "GIST_TOKEN") or os.environ.get("GIST_TOKEN","")
    except Exception:
        return os.environ.get("GIST_TOKEN","")
