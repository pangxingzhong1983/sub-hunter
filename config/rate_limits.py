from dataclasses import dataclass


@dataclass
class RatePlan:
    per_minute: int
    burst: int = 5
    min_interval: float = 0.05


PLANS = {
    "api.github.com": RatePlan(
        per_minute=900, burst=10, min_interval=0.05
    ),  # 保守值，<5000/h
    "gitlab.com": RatePlan(per_minute=600, burst=8, min_interval=0.05),
    "gitee.com": RatePlan(per_minute=300, burst=6, min_interval=0.05),
}
DEFAULT = RatePlan(per_minute=120, burst=4, min_interval=0.05)

MAX_BACKOFF = 60
MAX_RETRIES = 5
