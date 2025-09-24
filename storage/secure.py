import os
from typing import Optional
from dotenv import load_dotenv, find_dotenv

# -- 1) dotenv 加载顺序：显式环境变量 → 项目根 → /root/.config/sub-hunter/.env
#    不覆盖已存在环境变量（override=False）
def _load_env_once() -> None:
    # 显式路径（可通过 DOTENV_PATH 指定）
    dotenv_path = os.environ.get("DOTENV_PATH")
    if dotenv_path:
        load_dotenv(dotenv_path=dotenv_path, override=False)

    # 项目根 .env（向上搜索）
    prj_env = find_dotenv(usecwd=True)
    if prj_env:
        load_dotenv(dotenv_path=prj_env, override=False)

    # 指定配置路径（与你当前部署一致）
    cfg_env = "/root/.config/sub-hunter/.env"
    if os.path.exists(cfg_env):
        load_dotenv(dotenv_path=cfg_env, override=False)

_LOAD_FLAG = False
def _ensure_env_loaded():
    global _LOAD_FLAG
    if not _LOAD_FLAG:
        _load_env_once()
        _LOAD_FLAG = True

# -- 2) keyring（可选依赖）：无后端/异常 → 回落到环境变量
try:
    import keyring  # type: ignore
except Exception:  # ImportError 或其他
    keyring = None  # noqa: N816

def get_secret(service: str, key: str) -> Optional[str]:
    """
    读取顺序：
    ① keyring（如可用，且无异常）
    ② 环境变量（含 .env 加载）
    """
    _ensure_env_loaded()

    # keyring 尝试
    if keyring is not None:
        try:
            val = keyring.get_password(service, key)  # 可能抛 NoKeyringError
            if val:
                return val
        except Exception:
            # 无后端/出错 → 静默回落
            pass

    # 环境变量兜底
    return os.environ.get(key)

def set_secret(service: str, key: str, value: str) -> None:
    """
    设置顺序：
    ① 能用 keyring 则写入
    ② 否则静默忽略（或按需写入 os.environ，仅对当前进程有效，不持久）
    """
    if keyring is not None:
        try:
            keyring.set_password(service, key, value)
            return
        except Exception:
            pass
    # 不使用 os.environ 持久化（不可靠），仅保底给当前进程
    os.environ[key] = value
