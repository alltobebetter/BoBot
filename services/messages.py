"""留言系统：给离线用户留言，下次进入聊天室时投递。

数据存于 SQLite messages 表。
- 在线用户留言：直接私聊通知对方，不存库
- 离线用户留言：存库，等对方 join 时投递
"""
from __future__ import annotations

from typing import Dict, List

from core.result import Result
from storage.db import Database
from utils.text import now, truncate


class MessageService:
    """离线留言的存储与投递。"""

    def __init__(self, db: Database):
        self.db = db

    def leave(self, from_nick: str, from_trip: str,
              to_nick: str, text: str) -> Result:
        """存一条留言（调用方负责判断对方是否在线）。"""
        text = truncate((text or "").strip(), 500)
        if not text:
            return Result.fail("留言内容不能为空")
        if from_nick.lower() == to_nick.lower():
            return Result.fail("不能给自己留言")
        self.db.execute(
            "INSERT INTO messages(from_nick, from_trip, to_nick, text, ts) "
            "VALUES(?,?,?,?,?)",
            (from_nick, from_trip or "", to_nick, text, now().isoformat()),
        )
        return Result.ok(f"[OK] 留言已保存，{to_nick} 下次进入时将收到")

    def pending(self, nick: str) -> List[Dict]:
        """获取未投递的留言（昵称大小写不敏感）。"""
        return self.db.query(
            "SELECT id, from_nick, text, ts FROM messages "
            "WHERE to_nick=? COLLATE NOCASE AND delivered=0 ORDER BY id",
            (nick,),
        )

    def mark_delivered(self, nick: str) -> int:
        """将某用户的所有未投递留言标记为已投递，返回数量。"""
        cur = self.db.execute(
            "UPDATE messages SET delivered=1 "
            "WHERE to_nick=? COLLATE NOCASE AND delivered=0",
            (nick,),
        )
        return cur.rowcount

    def format_for_delivery(self, msgs: List[Dict]) -> str:
        """格式化待投递留言为通知文本。"""
        lines = [f"[INFO] 你有 {len(msgs)} 条留言："]
        for m in msgs:
            ts = m["ts"][:16].replace("T", " ")
            lines.append(f"• {m['from_nick']}（{ts}）：{m['text']}")
        return "\n".join(lines)
