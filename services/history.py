"""聊天历史服务：基于 SQLite 的消息记录、搜索。

取代旧项目的 JSON 文件方案，统一存入 chat_log 表。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from storage.db import Database
from utils.text import now, today_str


class HistoryService:
    """聊天消息的记录、检索。所有数据存 SQLite，不写文件。"""

    def __init__(self, db: Database):
        self.db = db

    # ---- 写入 ----

    def record(self, channel: str, nick: str, trip: str, text: str,
               custom_id: Optional[str] = None) -> None:
        """记录一条聊天消息。"""
        ts = now().isoformat()
        self.db.execute(
            "INSERT INTO chat_log(channel,nick,trip,text,ts,custom_id) "
            "VALUES(?,?,?,?,?,?)",
            (channel or "", nick, trip or "", text, ts, custom_id or ""),
        )

    def update_by_custom_id(self, channel: str, custom_id: str, text: str) -> bool:
        """根据 customId 更新消息内容（用于 AI 回复更新）。"""
        if not custom_id:
            return False
        # SQLite 不支持 UPDATE+ORDER BY+LIMIT，用子查询取最新一条 id
        row = self.db.query_one(
            "SELECT id FROM chat_log WHERE custom_id=? AND channel=? "
            "ORDER BY id DESC LIMIT 1",
            (custom_id, channel or ""),
        )
        if not row:
            return False
        self.db.execute(
            "UPDATE chat_log SET text=? WHERE id=?",
            (text, row["id"]),
        )
        return True

    # ---- 查询 ----

    def recent(self, limit: int = 20, channel: Optional[str] = None,
               nick: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取最近消息。"""
        sql = "SELECT nick, trip, text, ts FROM chat_log WHERE 1=1"
        params: list = []
        if channel:
            sql += " AND channel=?"
            params.append(channel)
        if nick:
            sql += " AND nick=?"
            params.append(nick)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        rows = self.db.query(sql, params)
        return list(reversed(rows))

    def search(self, keyword: str, limit: int = 20,
               channel: Optional[str] = None) -> List[Dict[str, Any]]:
        """搜索消息。"""
        sql = "SELECT nick, trip, text, ts FROM chat_log WHERE text LIKE ?"
        params: list = [f"%{keyword}%"]
        if channel:
            sql += " AND channel=?"
            params.append(channel)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        rows = self.db.query(sql, params)
        return list(reversed(rows))

    def by_date(self, date_str: str, channel: Optional[str] = None,
                limit: int = 500) -> List[Dict[str, Any]]:
        """获取指定日期的所有消息（按时间正序）。"""
        sql = "SELECT nick, trip, text, ts FROM chat_log WHERE ts LIKE ?"
        params: list = [f"{date_str}%"]
        if channel:
            sql += " AND channel=?"
            params.append(channel)
        sql += " ORDER BY id ASC LIMIT ?"
        params.append(limit)
        return self.db.query(sql, params)

    def available_dates(self, channel: Optional[str] = None) -> List[str]:
        """获取有消息记录的日期列表（降序）。"""
        sql = "SELECT DISTINCT substr(ts, 1, 10) as date FROM chat_log"
        params: list = []
        if channel:
            sql += " WHERE channel=?"
            params.append(channel)
        sql += " ORDER BY date DESC LIMIT 90"
        rows = self.db.query(sql, params)
        return [r["date"] for r in rows] if rows else []

    def user_messages(self, nick: str, limit: int = 50) -> List[Dict[str, Any]]:
        """获取指定用户的最近消息（用于用户画像）。"""
        rows = self.db.query(
            "SELECT text, ts FROM chat_log WHERE nick=? ORDER BY id DESC LIMIT ?",
            (nick, limit),
        )
        return list(reversed(rows))

    def random_message(self, channel: Optional[str] = None,
                       min_days_ago: int = 3) -> Optional[Dict[str, Any]]:
        """随机抽取一条至少 min_days_ago 天前的消息（用于考古）。"""
        from datetime import timedelta
        cutoff = (now() - timedelta(days=min_days_ago)).isoformat()
        sql = "SELECT nick, trip, text, ts FROM chat_log WHERE ts < ?"
        params: list = [cutoff]
        if channel:
            sql += " AND channel=?"
            params.append(channel)
        sql += " ORDER BY RANDOM() LIMIT 1"
        return self.db.query_one(sql, params)

    # ---- 统计 ----

    def count_today(self, channel: Optional[str] = None) -> int:
        """今日消息数。"""
        today = today_str()
        if channel:
            row = self.db.query_one(
                "SELECT COUNT(*) as c FROM chat_log WHERE channel=? AND ts LIKE ?",
                (channel, f"{today}%"),
            )
        else:
            row = self.db.query_one(
                "SELECT COUNT(*) as c FROM chat_log WHERE ts LIKE ?",
                (f"{today}%",),
            )
        return row["c"] if row else 0

    # ---- 清理 ----

    def cleanup_old(self, days: int = 90) -> int:
        """清理超过指定天数的旧记录，返回删除条数。"""
        from datetime import timedelta
        cutoff_str = (now() - timedelta(days=days)).isoformat()
        cur = self.db.execute("DELETE FROM chat_log WHERE ts < ?", (cutoff_str,))
        return cur.rowcount
