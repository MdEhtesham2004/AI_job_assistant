import time
from collections import defaultdict, deque
from threading import Lock

from app.core.errors import LimitExceededError


class SlidingWindowRateLimiter:
    """In-process sliding-window limiter for auth endpoints (Phase 1 §6).

    Per process only — moves to Redis when Redis is introduced (Phase 6/14).
    """

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str, *, limit: int, window_seconds: int) -> None:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - window_seconds:
                hits.popleft()
            if len(hits) >= limit:
                retry_after = max(1, int(window_seconds - (now - hits[0])) + 1)
                raise LimitExceededError(
                    "Too many attempts. Please wait and try again.",
                    details={"retry_after": retry_after},
                )
            hits.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
