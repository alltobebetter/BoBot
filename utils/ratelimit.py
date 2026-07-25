"""统一的滑动窗口限流器。"""
from __future__ import annotations

import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, max_calls: int, window: int):
        self.max_calls = max_calls
        self.window = window
        self._calls = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.time()
        dq = self._calls[key]
        while dq and dq[0] <= now - self.window:
            dq.popleft()
        if len(dq) >= self.max_calls:
            return False
        dq.append(now)
        return True
