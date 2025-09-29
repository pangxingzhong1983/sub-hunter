import random
import threading
import time
from collections import defaultdict
from typing import Dict

from config.rate_limits import DEFAULT, PLANS


class _TokenBucket:
    def __init__(self, rate_per_minute: int, burst: int):
        self.capacity = max(1, burst)
        self.tokens = self.capacity
        self.refill_rate = max(0.1, rate_per_minute / 60.0)  # tokens/s
        self.last = time.monotonic()
        self.lock = threading.Lock()

    def _refill(self):
        now = time.monotonic()
        delta = now - self.last
        self.last = now
        self.tokens = min(self.capacity, self.tokens + delta * self.refill_rate)

    def take(self, n=1):
        with self.lock:
            self._refill()
            if self.tokens >= n:
                self.tokens -= n
                return 0.0
            need = n - self.tokens
            wait = need / self.refill_rate
            self.tokens = 0.0
            return max(0.0, wait)


class RateLimiter:
    def __init__(self):
        self.buckets: Dict[str, _TokenBucket] = {}
        self.min_interval: Dict[str, float] = defaultdict(float)
        self._last_ts: Dict[str, float] = defaultdict(lambda: 0.0)
        self._glock = threading.Lock()

    def _bucket_for(self, host: str) -> _TokenBucket:
        plan = PLANS.get(host, DEFAULT)
        with self._glock:
            if host not in self.buckets:
                self.buckets[host] = _TokenBucket(plan.per_minute, plan.burst)
                self.min_interval[host] = plan.min_interval
        return self.buckets[host]

    def acquire(self, host: str):
        b = self._bucket_for(host)
        wait = b.take(1)
        mi = self.min_interval[host]
        gap = time.monotonic() - self._last_ts[host]
        extra = max(0.0, mi - gap)
        jitter = random.uniform(0, mi * 0.2) if mi > 0 else 0.0
        sleep_s = max(wait, extra) + jitter
        if sleep_s > 0:
            time.sleep(sleep_s)
        self._last_ts[host] = time.monotonic()


limiter = RateLimiter()
