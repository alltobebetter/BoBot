"""金句服务：收藏与展示聊天室金句。

任何人可以 star 一条消息（通过引用昵称+内容片段），
金句存入 quotes 表，网页端可展示金句墙。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.result import Result
from storage.db import Database
from utils.text import now


class QuoteService:
    """金句的收藏、查询。"""

    def __init__(self, db: Database):
        self.db = db

    def add(self, channel: str, nick: str, trip: str, text: str,
            starred_by: str) -> Result:
        """收藏一条金句。"""
        text = (text or "").strip()
        if not text:
            return Result.fail("内容不能为空")
        if len(text) > 500:
            text = text[:500]
        ts = now().isoformat()
        self.db.execute(
            "INSERT INTO quotes(channel,nick,trip,text,ts,starred_by,starred_ts) "
            "VALUES(?,?,?,?,?,?,?)",
            (channel or "", nick, trip or "", text, ts, starred_by, ts),
        )
        return Result.ok(f"已收藏 {nick} 的金句")

    def random(self, channel: Optional[str] = None, limit: int = 1) -> List[Dict[str, Any]]:
        """随机获取金句。"""
        sql = "SELECT nick, text, ts, starred_by FROM quotes"
        params: list = []
        if channel:
            sql += " WHERE channel=?"
            params.append(channel)
        sql += " ORDER BY RANDOM() LIMIT ?"
        params.append(limit)
        return self.db.query(sql, params)

    def recent(self, channel: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        """获取最近金句（按收藏时间倒序）。"""
        sql = "SELECT nick, text, ts, starred_by, starred_ts FROM quotes"
        params: list = []
        if channel:
            sql += " WHERE channel=?"
            params.append(channel)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        return self.db.query(sql, params)

    def count(self, channel: Optional[str] = None) -> int:
        """金句总数。"""
        sql = "SELECT COUNT(*) as c FROM quotes"
        params: list = []
        if channel:
            sql += " WHERE channel=?"
            params.append(channel)
        row = self.db.query_one(sql, params)
        return row["c"] if row else 0
