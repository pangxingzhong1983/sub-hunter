import os
import keyring

def get_secret(service:str, key:str) -> str|None:
    # 先钥匙串，再环境变量
    val = keyring.get_password(service, key)
    if val: return val
    return os.environ.get(key)

def set_secret(service:str, key:str, value:str):
    keyring.set_password(service, key, value)
