"""用户信息查询服务（seen/look）。

seen  — 查看用户最后发言时间和内容（持久化）
look  — 查看在线用户的加入时间和发言频率（内存）

数据存储：KV 持久化 + 内存缓存。
"""
from __future__ import annotations

import time
from typing import Dict, Optional

from core.result import Result
from storage.kv import KVStore


class SeenService:
    """记录用户最后发言时间和内容。"""

    def __init__(self, kv: KVStore):
        self.kv = kv

    def record(self, nick: str, trip: str, text: str) -> None:
        """记录用户发言（由 Bot._handle_chat 调用）。"""
        now = time.time()
        # 按 nick 和 trip 分别记录
        nick_data = self.kv.get("seen", "nick") or {}
        nick_data[nick] = {"time": now, "text": text[:100], "trip": trip}
        self.kv.set("seen", "nick", nick_data)

        if trip:
            trip_data = self.kv.get("seen", "trip") or {}
            trip_data[trip] = {"time": now, "text": text[:100], "nick": nick}
            self.kv.set("seen", "trip", trip_data)

    def get_by_nick(self, nick: str) -> Result:
        """按昵称查询。"""
        nick_data = self.kv.get("seen", "nick") or {}
        info = nick_data.get(nick)
        if not info:
            return Result.fail(f"没有找到 {nick} 的记录")
        ts = info["time"]
        elapsed = int(time.time() - ts)
        text = info.get("text", "")
        trip = info.get("trip", "")
        trip_str = f"#{trip}" if trip else ""
        return Result.ok(
            f"[INFO] {nick}{trip_str}\n"
            f"最后发言：{_format_time(ts)}（{_elapsed(elapsed)}前）\n"
            f"内容：{text}"
        )

    def get_by_trip(self, trip: str) -> Result:
        """按识别码查询。"""
        trip_data = self.kv.get("seen", "trip") or {}
        info = trip_data.get(trip)
        if not info:
            return Result.fail(f"没有找到 #{trip} 的记录")
        ts = info["time"]
        elapsed = int(time.time() - ts)
        text = info.get("text", "")
        nick = info.get("nick", "?")
        return Result.ok(
            f"[INFO] {nick}#{trip}\n"
            f"最后发言：{_format_time(ts)}（{_elapsed(elapsed)}前）\n"
            f"内容：{text}"
        )


class LookService:
    """查看在线用户信息（加入时间 + 发言频率）。"""

    def __init__(self):
        self.users: Dict[str, dict] = {}  # {nick: {joined, words}}

    def on_join(self, nick: str) -> None:
        """用户加入时调用。"""
        self.users[nick] = {"joined": time.time(), "words": 0}

    def on_leave(self, nick: str) -> None:
        """用户离开时调用。"""
        self.users.pop(nick, None)

    def on_chat(self, nick: str) -> None:
        """用户发言时调用。"""
        if nick in self.users:
            self.users[nick]["words"] += 1

    def on_clear(self) -> None:
        """清空（重连时）。"""
        self.users.clear()

    def get(self, nick: str) -> Result:
        """查看在线用户信息。"""
        info = self.users.get(nick)
        if not info:
            return Result.fail(f"{nick} 当前不在线 😢")
        now = time.time()
        joined_elapsed = int(now - info["joined"])
        words = info["words"]
        if words > 0:
            minutes = joined_elapsed / 60
            freq = minutes / words if words > 0 else 0
            freq_str = f"每 {freq:.1f} 分钟发言一次"
        else:
            freq_str = "暂无发言记录"
        return Result.ok(
            f"[INFO] {nick}\n"
            f"加入时间：{_format_time(info['joined'])}（{_elapsed(joined_elapsed)}前）\n"
            f"发言次数：{words}\n"
            f"发言频率：{freq_str}"
        )


def _format_time(ts: float) -> str:
    """格式化时间戳为可读字符串。"""
    import time as _t
    return _t.strftime("%Y-%m-%d %H:%M:%S", _t.localtime(ts))


def _elapsed(seconds: int) -> str:
    """格式化时间差。"""
    if seconds >= 86400:
        d = seconds // 86400
        return f"{d}天{seconds % 86400 // 3600}时"
    if seconds >= 3600:
        h = seconds // 3600
        return f"{h}时{seconds % 3600 // 60}分"
    if seconds >= 60:
        return f"{seconds // 60}分"
    return f"{seconds}秒"
