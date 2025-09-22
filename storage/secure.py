import os
import keyring
from dotenv import load_dotenv

# 加载 /root/.config/sub-hunter/.env
load_dotenv(dotenv_path="/root/.config/sub-hunter/.env")

def get_secret(service: str, key: str) -> str | None:
    # ① 优先钥匙串
    val = keyring.get_password(service, key)
    if val:
        return val
    # ② 再看环境变量（含 .env）
    return os.environ.get(key)

def set_secret(service: str, key: str, value: str):
    keyring.set_password(service, key, value)