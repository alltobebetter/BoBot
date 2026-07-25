"""统一的 SQLite 存储（取代所有 JSON 文件与多个 repository）。

所有持久化数据都在这一个库里：
- users：金币、签到、自定义欢迎
- inventory：背包
- stats：聊天统计
- checkins：每日签到
- transactions：金币流水
- kv：通用键值（广告池、加密货持仓、AI 历史等）
"""
from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_key TEXT PRIMARY KEY,
    nick TEXT,
    trip TEXT,
    coins INTEGER NOT NULL DEFAULT 0,
    last_checkin TEXT,
    streak INTEGER NOT NULL DEFAULT 0,
    custom_welcome TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS inventory (
    user_key TEXT,
    item_id TEXT,
    qty INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_key, item_id)
);
CREATE TABLE IF NOT EXISTS stats (
    user_key TEXT PRIMARY KEY,
    nick TEXT,
    trip TEXT,
    messages INTEGER NOT NULL DEFAULT 0,
    chars INTEGER NOT NULL DEFAULT 0,
    first_seen TEXT,
    last_seen TEXT
);
CREATE TABLE IF NOT EXISTS checkins (
    user_key TEXT,
    date TEXT,
    rank INTEGER,
    ts TEXT,
    PRIMARY KEY (user_key, date)
);
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_key TEXT,
    amount INTEGER,
    balance INTEGER,
    reason TEXT,
    ts TEXT
);
CREATE TABLE IF NOT EXISTS kv (
    namespace TEXT,
    key TEXT,
    value TEXT,
    PRIMARY KEY (namespace, key)
);
CREATE TABLE IF NOT EXISTS chat_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT,
    nick TEXT,
    trip TEXT,
    text TEXT,
    ts TEXT,
    custom_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_chat_channel_ts ON chat_log(channel, ts);
CREATE INDEX IF NOT EXISTS idx_chat_nick ON chat_log(nick);
CREATE INDEX IF NOT EXISTS idx_chat_custom_id ON chat_log(custom_id);
CREATE TABLE IF NOT EXISTS stats_daily (
    user_key TEXT,
    date TEXT,
    nick TEXT,
    messages INTEGER NOT NULL DEFAULT 0,
    chars INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_key, date)
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_nick TEXT,
    from_trip TEXT,
    to_nick TEXT,
    text TEXT,
    ts TEXT,
    delivered INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_msg_to ON messages(to_nick, delivered);
CREATE INDEX IF NOT EXISTS idx_tx_user ON transactions(user_key);
CREATE INDEX IF NOT EXISTS idx_checkins_date ON checkins(date);
CREATE INDEX IF NOT EXISTS idx_users_coins ON users(coins);
CREATE INDEX IF NOT EXISTS idx_stats_daily_date ON stats_daily(date);
CREATE TABLE IF NOT EXISTS game_stats (
    user_key TEXT,
    game TEXT,
    nick TEXT,
    wins INTEGER NOT NULL DEFAULT 0,
    plays INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_key, game)
);
CREATE INDEX IF NOT EXISTS idx_game_stats_game ON game_stats(game, wins DESC);
CREATE TABLE IF NOT EXISTS quotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT,
    nick TEXT,
    trip TEXT,
    text TEXT,
    ts TEXT,
    starred_by TEXT,
    starred_ts TEXT
);
CREATE INDEX IF NOT EXISTS idx_quotes_channel ON quotes(channel);
CREATE TABLE IF NOT EXISTS digests (
    date TEXT,
    channel TEXT,
    content TEXT,
    msg_count INTEGER NOT NULL DEFAULT 0,
    created_ts TEXT,
    PRIMARY KEY (date, channel)
);
"""


class Database:
    def __init__(self, path: str):
        self.path = path
        parent = os.path.dirname(path)
        if parent:
            Path(parent).mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def query(self, sql: str, params: Sequence[Any] = ()) -> List[Dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]

    def query_one(self, sql: str, params: Sequence[Any] = ()) -> Optional[Dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute(sql, params)
            row = cur.fetchone()
            return dict(row) if row else None

    def close(self) -> None:
        with self._lock:
            self._conn.close()
