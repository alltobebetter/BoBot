"""简单的 TTL 内存缓存。"""
from __future__ import annotations

import time
from typing import Any, Optional


class TTLCache:
    def __init__(self, ttl: int = 300):
        self.ttl = ttl
        self._d: dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Optional[Any]:
        item = self._d.get(key)
        if not item:
            return None
        val, exp = item
        if time.time() > exp:
            self._d.pop(key, None)
            return None
        return val

    def set(self, key: str, val: Any, ttl: Optional[int] = None) -> None:
        self._d[key] = (val, time.time() + (ttl or self.ttl))

    def clear(self) -> None:
        self._d.clear()
