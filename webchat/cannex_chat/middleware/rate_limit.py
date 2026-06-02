"""IP 级内存限流（社区 demo 用，进程重启即清空）。"""
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, max_per_window: int = 30, window_seconds: float = 60.0):
        self._max = max_per_window
        self._window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        q = self._hits[key]
        while q and now - q[0] > self._window:
            q.popleft()
        if len(q) >= self._max:
            return False
        q.append(now)
        return True
