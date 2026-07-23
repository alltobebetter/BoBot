"""聊天统计：消息数、字符数、每日明细、周/总排行。"""
from __future__ import annotations

from typing import Dict, List, Optional

from storage.db import Database
from utils.text import now, today_str, user_key


class StatsService:
    def __init__(self, db: Database):
        self.db = db

    def record(self, nick: str, trip: str, text: str) -> None:
        """记录一条消息：更新总统计 + 每日统计。"""
        key = user_key(nick, trip)
        ts = now().isoformat()
        today = today_str()
        chars = len(text or "")

        # 总统计（upsert）
        self.db.execute(
            "INSERT INTO stats(user_key,nick,trip,messages,chars,first_seen,last_seen) "
            "VALUES(?,?,?,1,?,?,?) "
            "ON CONFLICT(user_key) DO UPDATE SET "
            "messages=messages+1, chars=chars+excluded.chars, last_seen=excluded.last_seen, "
            "nick=excluded.nick, trip=excluded.trip",
            (key, nick, trip or "", chars, ts, ts),
        )

        # 每日统计（upsert）
        self.db.execute(
            "INSERT INTO stats_daily(user_key,date,nick,messages,chars) "
            "VALUES(?,?,?,1,?) "
            "ON CONFLICT(user_key,date) DO UPDATE SET "
            "messages=messages+1, chars=chars+excluded.chars, nick=excluded.nick",
            (key, today, nick, chars),
        )

    def get(self, key: str) -> Optional[Dict]:
        return self.db.query_one("SELECT * FROM stats WHERE user_key=?", (key,))

    def top_chatters(self, limit: int = 10) -> List[Dict]:
        """总发言排行。"""
        return self.db.query(
            "SELECT nick, trip, messages, chars FROM stats ORDER BY messages DESC LIMIT ?",
            (limit,),
        )

    def top_weekly(self, limit: int = 10) -> List[Dict]:
        """本周（最近 7 天）发言排行。"""
        from datetime import timedelta
        start = (now() - timedelta(days=7)).strftime("%Y-%m-%d")
        return self.db.query(
            "SELECT MAX(nick) as nick, SUM(messages) as messages, SUM(chars) as chars "
            "FROM stats_daily WHERE date >= ? "
            "GROUP BY user_key ORDER BY messages DESC LIMIT ?",
            (start, limit),
        )

    def user_weekly(self, key: str) -> int:
        """用户本周消息数。"""
        from datetime import timedelta
        start = (now() - timedelta(days=7)).strftime("%Y-%m-%d")
        row = self.db.query_one(
            "SELECT COALESCE(SUM(messages),0) as c FROM stats_daily WHERE user_key=? AND date>=?",
            (key, start),
        )
        return row["c"] if row else 0

    # ---- 游戏统计 ----

    def record_game(self, nick: str, trip: str, game: str, won: bool) -> None:
        """记录一局游戏结果。"""
        key = user_key(nick, trip)
        self.db.execute(
            "INSERT INTO game_stats(user_key,game,nick,wins,plays) "
            "VALUES(?,?,?,?,1) "
            "ON CONFLICT(user_key,game) DO UPDATE SET "
            "plays=plays+1, wins=wins+?, nick=excluded.nick",
            (key, game, nick, 1 if won else 0, 1 if won else 0),
        )

    def game_ranking(self, game: str, limit: int = 10) -> List[Dict]:
        """某游戏胜场排行。"""
        return self.db.query(
            "SELECT nick, wins, plays FROM game_stats WHERE game=? AND wins>0 "
            "ORDER BY wins DESC LIMIT ?",
            (game, limit),
        )
