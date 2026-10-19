"""Per-client fixed-window rate limiting for write endpoints.

In-memory, so the limit is per API process. That is enough for a single
instance demo; several replicas would need a shared store such as Redis
(INCR + EXPIRE on a per-window key).
"""

import time
from collections import defaultdict

from fastapi import HTTPException, Request, status


class RateLimiter:
    def __init__(self, window_s: float = 60.0) -> None:
        self.window_s = window_s
        self._counts: dict[tuple[str, str, int], int] = defaultdict(int)

    def check(self, bucket: str, client: str, limit: int, now: float | None = None) -> bool:
        """Count one request; return False if it exceeds ``limit`` this window."""
        if limit <= 0:
            return True
        window = int((now if now is not None else time.time()) // self.window_s)
        key = (bucket, client, window)
        self._counts[key] += 1
        if len(self._counts) > 10_000:  # drop old windows so memory stays bounded
            for k in [k for k in self._counts if k[2] < window]:
                del self._counts[k]
        return self._counts[key] <= limit


def client_id(request: Request) -> str:
    # Behind a proxy (Render, Vercel) the original client is the first
    # X-Forwarded-For entry. It can be spoofed, which is acceptable for
    # demo abuse protection but not for security decisions.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def limit(bucket: str, setting: str):
    """FastAPI dependency: 429 when this client exceeds the configured rate."""

    def dependency(request: Request) -> None:
        settings = request.app.state.settings
        limiter: RateLimiter = request.app.state.rate_limiter
        if not limiter.check(bucket, client_id(request), getattr(settings, setting)):
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests from this client; try again in a minute.",
                headers={"Retry-After": "60"},
            )

    return dependency
