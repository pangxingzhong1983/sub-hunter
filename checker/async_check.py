import asyncio, aiohttp

async def _check_one(session: aiohttp.ClientSession, url: str, timeout: int = 8) -> bool:
    try:
        async with session.get(url, timeout=timeout, allow_redirects=True) as r:
            if r.status == 200:
                # 读一点点，确认不是空洞 200
                _ = await r.content.read(1024)
                return True
            return False
    except Exception:
        return False

async def check_urls(urls, concurrency: int = 12, timeout: int = 8):
    """
    高并发连通性检测
    - concurrency: 并发量（建议 8~16 之间）
    - timeout: 单链接秒级超时
    - 读取系统代理(HTTP_PROXY/HTTPS_PROXY)，以穿透网络限制
    """
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
