import asyncio
from typing import Any

try:
    import aiohttp  # type: ignore[reportMissingImports]
except Exception:
    aiohttp = None  # type: ignore


async def _check_one(session: Any, url: str, timeout: int = 8) -> bool:
    try:
        async with session.get(url, timeout=timeout, allow_redirects=True) as r:
            if r.status == 200:
                # 读一点点，确认不是空洞 200
                _ = await r.content.read(1024)
                return True
            return False
    except Exception:
        return False


def _sync_head_check(urls, concurrency: int = 12, timeout: int = 8):
    # Fallback when aiohttp is not available: use requests in threads
    import concurrent.futures

    import requests

    ok = []

    def _one(u: str):
        try:
            r = requests.get(u, timeout=timeout, stream=True)
            if r.status_code == 200:
                # read a bit
                _ = r.raw.read(1024)
                return u
        except Exception:
            return None
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as ex:
        futs = {ex.submit(_one, u): u for u in urls}
        for fut in concurrent.futures.as_completed(futs):
            try:
                r = fut.result()
            except Exception:
                r = None
            if r:
                ok.append(r)
    return ok


async def check_urls(urls, concurrency: int = 12, timeout: int = 8):
    """
    高并发连通性检测
    - concurrency: 并发量（建议 8~16 之间）
    - timeout: 单链接秒级超时
    - 读取系统代理(HTTP_PROXY/HTTPS_PROXY)，以穿透网络限制
    """
    # If aiohttp is not available, fall back to thread-based requests implementation
    if aiohttp is None:
        # run blocking sync check in executor to keep async API
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, _sync_head_check, urls, concurrency, timeout
        )

    ok = []
    sem = asyncio.Semaphore(concurrency)
    async with aiohttp.ClientSession(trust_env=True) as session:

        async def worker(u: str):
            async with sem:
                good = await _check_one(session, u, timeout=timeout)
                if good:
                    ok.append(u)

        await asyncio.gather(*[worker(u) for u in urls])
    return ok
