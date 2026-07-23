"""AFK（暂离）服务，纯内存。"""
from __future__ import annotations

from typing import Dict, Optional

from core.result import Result
from utils.logger import log
from utils.text import now, user_key


class AFKService:
    def __init__(self):
        self._afk: Dict[str, Dict] = {}

    def set(self, key: str, nick: str, reason: str) -> Result:
        self._afk[key] = {"nick": nick, "reason": reason or "暂时离开", "since": now()}
        return Result.ok(f"[OK] {nick} 已进入 AFK：{reason or '暂时离开'}")

    def is_afk(self, key: str) -> bool:
        return key in self._afk

    def clear(self, key: str) -> Optional[Dict]:
        return self._afk.pop(key, None)

    def seen(self, nick: str, trip: str = "") -> None:
        """用户上线时调用，自动清除该用户的 AFK 状态。

        场景：用户 AFK 后断线重连，onlineSet 到达时自动清除 AFK，
        而不是等用户再发消息才清除。
        """
        if not nick:
            return
        key = user_key(nick, trip)
        info = self._afk.pop(key, None)
        if info:
            log.info("上线自动清除 AFK", nick=nick)
