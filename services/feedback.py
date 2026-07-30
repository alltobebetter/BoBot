"""反馈与奖励系统。

FeedbackService：用户反馈存库（取代旧版只写日志的实现）。
RewardService：管理员挂奖励到昵称上，用户进入聊天室时自动发放。

奖励数据存于 KV 表（namespace='rewards'），key=昵称。
与 feedback 解耦：reward 可给任何人，不限于提过反馈的用户。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.result import Result
from storage.db import Database
from storage.kv import KVStore
from utils.text import now, user_key

_NS = "rewards"


class FeedbackService:
    """用户反馈的存储与查询。"""

    def __init__(self, db: Database):
        self.db = db

    def submit(self, nick: str, trip: str, content: str) -> Result:
        """存一条用户反馈。"""
        content = (content or "").strip()
        if not content:
            return Result.fail("反馈内容不能为空")
        if len(content) > 1000:
            content = content[:1000]
        key = user_key(nick, trip)
        self.db.execute(
            "INSERT INTO feedbacks(user_key, nick, trip, content, ts) "
            "VALUES(?,?,?,?,?)",
            (key, nick, trip or "", content, now().isoformat()),
        )
        return Result.ok("[OK] 感谢反馈")

    def list_pending(self, limit: int = 20) -> List[Dict]:
        """查看待处理反馈（管理员）。"""
        return self.db.query(
            "SELECT id, nick, trip, content, ts, status FROM feedbacks "
            "WHERE status='pending' ORDER BY id DESC LIMIT ?",
            (limit,),
        )

    def list_all(self, limit: int = 20) -> List[Dict]:
        """查看全部反馈（管理员）。"""
        return self.db.query(
            "SELECT id, nick, trip, content, ts, status FROM feedbacks "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        )

    def mark_reviewed(self, feedback_id: int) -> Result:
        """标记反馈为已处理。"""
        cur = self.db.execute(
            "UPDATE feedbacks SET status='reviewed' WHERE id=? AND status='pending'",
            (feedback_id,),
        )
        if cur.rowcount == 0:
            return Result.fail("反馈不存在或已处理")
        return Result.ok(f"[OK] 反馈 #{feedback_id} 已标记为已处理")


class RewardService:
    """管理员挂奖励，用户进入聊天室时自动发放。

    数据存于 KV（namespace='rewards'），key=昵称（大小写不敏感）。
    """

    def __init__(self, kv: KVStore):
        self.kv = kv

    def _load_all(self) -> Dict[str, dict]:
        """加载全部待发放奖励。"""
        raw = self.kv.get(_NS, "pending") or []
        if not isinstance(raw, list):
            return {}
        # 按昵称小写索引，支持大小写不敏感匹配
        return {r["nick"].lower(): r for r in raw if r.get("nick")}

    def _save_all(self, rewards: Dict[str, dict]) -> None:
        self.kv.set(_NS, "pending", list(rewards.values()))

    def create(
        self,
        nick: str,
        coins: int,
        *,
        item: str = "",
        item_qty: int = 0,
        reason: str = "",
        admin: str = "",
    ) -> Result:
        """挂一条奖励到指定昵称。"""
        if not nick.strip():
            return Result.fail("昵称不能为空")
        if coins < 0:
            return Result.fail("金币不能为负")
        if coins == 0 and not item:
            return Result.fail("金币和道具至少指定一项")
        rewards = self._load_all()
        key = nick.lower()
        rewards[key] = {
            "nick": nick,
            "coins": coins,
            "item": item,
            "item_qty": item_qty,
            "reason": reason or "奖励",
            "admin": admin,
            "ts": now().isoformat(),
            "delivered": False,
        }
        self._save_all(rewards)
        parts = [f"{coins} 金币"] if coins else []
        if item and item_qty:
            parts.append(f"{item} x{item_qty}")
        desc = " + ".join(parts)
        return Result.ok(
            f"[OK] 已为 {nick} 挂载奖励：{desc}"
            f"{'（理由：' + reason + '）' if reason else ''}"
            f"\n对方进入聊天室时自动发放"
        )

    def pending_for(self, nick: str) -> Optional[dict]:
        """查找指定昵称的待发放奖励（大小写不敏感）。"""
        rewards = self._load_all()
        return rewards.get(nick.lower())

    def mark_delivered(self, nick: str) -> None:
        """发放后从待发列表移除。"""
        rewards = self._load_all()
        rewards.pop(nick.lower(), None)
        self._save_all(rewards)

    def list_pending(self) -> List[Dict]:
        """列出全部待发放奖励。"""
        return list(self._load_all().values())

    def cancel(self, nick: str) -> Result:
        """取消未发放的奖励。"""
        rewards = self._load_all()
        if nick.lower() not in rewards:
            return Result.fail(f"没有 {nick} 的待发放奖励")
        rewards.pop(nick.lower())
        self._save_all(rewards)
        return Result.ok(f"[OK] 已取消 {nick} 的奖励")
