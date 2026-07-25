"""用户管理：账户创建、自定义欢迎。"""
from __future__ import annotations

from typing import Dict, Optional

from core.result import Result
from storage.db import Database
from utils.text import now, user_key


class UserManager:
    def __init__(self, db: Database):
        self.db = db

    def get_or_create(self, nick: str, trip: str) -> Dict:
        key = user_key(nick, trip)
        row = self.db.query_one("SELECT * FROM users WHERE user_key=?", (key,))
        if row:
            return row
        ts = now().isoformat()
        self.db.execute(
            "INSERT INTO users(user_key,nick,trip,coins,created_at,updated_at) "
            "VALUES(?,?,?,0,?,?)",
            (key, nick, trip or "", ts, ts),
        )
        return self.db.query_one("SELECT * FROM users WHERE user_key=?", (key,))

    def get(self, key: str) -> Optional[Dict]:
        return self.db.query_one("SELECT * FROM users WHERE user_key=?", (key,))

    # ---- 自定义欢迎词 ----
    def set_welcome(self, nick: str, trip: str, text: Optional[str]) -> Result:
        u = self.get_or_create(nick, trip)
        self.db.execute(
            "UPDATE users SET custom_welcome=?, updated_at=? WHERE user_key=?",
            (text, now().isoformat(), u["user_key"]),
        )
        return Result.ok("欢迎词已更新" if text else "欢迎词已关闭")

    def welcome_for(self, nick: str) -> Optional[str]:
        """根据昵称查找自定义欢迎词（可能多 trip，取第一个）。"""
        row = self.db.query_one(
            "SELECT custom_welcome FROM users WHERE nick=? AND custom_welcome IS NOT NULL "
            "AND custom_welcome != '' LIMIT 1",
            (nick,),
        )
        if row and row.get("custom_welcome"):
            return row["custom_welcome"].replace("{nick}", nick)
        return None

    def is_known(self, nick: str) -> bool:
        """判断是否为已知用户（数据库中已存在）。"""
        row = self.db.query_one("SELECT 1 FROM users WHERE nick=? LIMIT 1", (nick,))
        return row is not None
