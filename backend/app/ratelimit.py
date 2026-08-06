"""Small in-process rate limiter for the unauthenticated endpoints.

Public signup means anyone can create rows in a 0.5 GB database, so login and
register need *some* brake. This is deliberately the cheapest thing that works:
a sliding window in a dict, no Redis, no extra service.

Its limitation is real and worth stating — the counters live in one process, so
they reset on deploy and would not be shared if this ever ran on more than one
instance. On Render's free tier there is exactly one instance and it restarts
whenever it wakes, so the tradeoff is fine here and nowhere else.
"""

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status


class RateLimiter:
    def __init__(self, max_hits: int, window_seconds: int, message: str):
        self.max_hits = max_hits
        self.window = window_seconds
        self.message = message
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, bucket: deque[float], now: float) -> None:
        cutoff = now - self.window
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            bucket = self._hits[key]
            self._prune(bucket, now)
            if len(bucket) >= self.max_hits:
                retry_after = int(self.window - (now - bucket[0])) + 1
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=self.message,
                    headers={"Retry-After": str(retry_after)},
                )
            bucket.append(now)

            # Keep the dict from growing without bound on a long-lived process.
            if len(self._hits) > 2048:
                for k in [k for k, v in self._hits.items() if not v][:1024]:
                    del self._hits[k]


def client_key(request: Request) -> str:
    """Render sits behind a proxy, so the real client is in X-Forwarded-For."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


login_limiter = RateLimiter(
    max_hits=10,
    window_seconds=300,
    message="ลองเข้าสู่ระบบบ่อยเกินไป รอสักครู่แล้วลองใหม่",
)

register_limiter = RateLimiter(
    max_hits=5,
    window_seconds=3600,
    message="สมัครบ่อยเกินไป ลองใหม่ในอีกสักพัก",
)
