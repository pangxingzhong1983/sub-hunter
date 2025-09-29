import os

# ===== 基本配置 =====
KEYWORDS = [
    "free v2ray",
    "free clash",
    "free vpn",
    "free nodes",
    "免费 订阅",
    "clash subscribe",
]

MAX_WORKERS = int(os.environ.get("MAX_WORKERS", "20"))
DAILY_INCREMENT = int(
    os.environ.get("DAILY_INCREMENT", "0")
)  # default 0 = unlimited daily additions
FAIL_THRESHOLD = int(os.environ.get("FAIL_THRESHOLD", "3"))

OUT_DIR = os.path.abspath(os.environ.get("OUT_DIR", "./data"))
OUT_FILE = os.path.join(OUT_DIR, "zhuquejisu.txt")
HIST_PATH = os.path.join(OUT_DIR, "history.json")

FILENAME_IN_GIST = "zhuquejisu.txt"


# 令牌读取：优先钥匙串，其次环境变量
def get_github_token():
    try:
        from storage.secure import get_secret

        return get_secret("sub-hunter", "GH_TOKEN") or os.environ.get("GH_TOKEN", "")
    except Exception:
        return os.environ.get("GH_TOKEN", "")


def get_gist_id():
    try:
        from storage.secure import get_secret

        return get_secret("sub-hunter", "GIST_ID") or os.environ.get("GIST_ID", "")
    except Exception:
        return os.environ.get("GIST_ID", "")


def get_gist_token():
    try:
        from storage.secure import get_secret

        return get_secret("sub-hunter", "GIST_TOKEN") or os.environ.get(
            "GIST_TOKEN", ""
        )
    except Exception:
        return os.environ.get("GIST_TOKEN", "")


# ===== 受信任源的二次 GET 校验设置 =====
# 是否启用对受信任 host 在被初步剔除前做一次 GET 验证（可通过环境变量覆盖）
TRUSTED_GET_VERIFY = os.environ.get("TRUSTED_GET_VERIFY", "1") in ("1", "true", "True")
# 受信任的 host 列表（以逗号分隔），默认包含常见的 raw CDN/托管域
_TRUSTED_HOSTS_ENV = os.environ.get("TRUSTED_GET_HOSTS", "raw.githubusercontent.com,cdn.jsdelivr.net,raw.fastgit.org")
TRUSTED_GET_HOSTS = set(h.strip().lower() for h in _TRUSTED_HOSTS_ENV.split(",") if h.strip())
# 并发与超时配置
TRUSTED_GET_CONCURRENCY = int(os.environ.get("TRUSTED_GET_CONCURRENCY", "6"))
TRUSTED_GET_TIMEOUT = int(os.environ.get("TRUSTED_GET_TIMEOUT", "10"))
