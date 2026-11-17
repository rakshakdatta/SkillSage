"""A small sliding-window rate limiter, so one visitor cannot burn the free AI quota."""
from __future__ import annotations

import threading
import time
from collections import deque


class RateLimiter:
    def __init__(self, limit: int, window_seconds: int = 60, clock=time.monotonic):
        self.limit = limit
        self.window = window_seconds
        self._clock = clock
        self._hits: dict[str, deque] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        if self.limit <= 0:
            return True
        now = self._clock()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            if len(self._hits) > 5000:  # forget idle visitors
                for k in [k for k, v in self._hits.items() if not v or now - v[-1] > self.window]:
                    self._hits.pop(k, None)
            return True