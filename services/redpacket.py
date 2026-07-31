"""红包系统（发红包 / 抢红包 / 查看红包）。

命令风格（BoB 无前缀）：
- packet <金额> <人数>   发红包
- packet <id>            抢红包
- packet                 查看当前红包列表

数据存储：内存 + KV 持久化，24 小时自动过期退还。
"""
from __future__ import annotations

import random
import string
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from config import config
from core.result import Result
from storage.kv import KVStore
from utils.logger import log


@dataclass
class RedPacket:
    """单个红包的数据结构。"""
    packet_id: str
    sender_nick: str
    sender_trip: str
    total_amount: int
    remaining_amount: int
    total_people: int
    remaining_people: int
    grabbed: Dict[str, int] = field(default_factory=dict)  # {user_key: amount}
    created_at: float = 0.0
    expire_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "packet_id": self.packet_id,
            "sender_nick": self.sender_nick,
            "sender_trip": self.sender_trip,
            "total_amount": self.total_amount,
            "remaining_amount": self.remaining_amount,
            "total_people": self.total_people,
            "remaining_people": self.remaining_people,
            "grabbed": self.grabbed,
            "created_at": self.created_at,
            "expire_at": self.expire_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RedPacket":
        return cls(
            packet_id=d["packet_id"],
            sender_nick=d["sender_nick"],
            sender_trip=d.get("sender_trip", ""),
            total_amount=d["total_amount"],
            remaining_amount=d["remaining_amount"],
            total_people=d["total_people"],
            remaining_people=d["remaining_people"],
            grabbed=d.get("grabbed", {}),
            created_at=d.get("created_at", 0),
            expire_at=d.get("expire_at", 0),
        )

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expire_at

    @property
    def is_empty(self) -> bool:
        return self.remaining_people <= 0 or self.remaining_amount <= 0


DAY = 24 * 3600


class RedPacketService:
    """红包服务：发红包、抢红包、过期退还。"""

    def __init__(self, kv: KVStore, coins):
        self.kv = kv
        self.coins = coins

    def _load_all(self) -> Dict[str, RedPacket]:
        """从 KV 加载所有红包。"""
        raw = self.kv.get("redpacket", "all") or {}
        if not isinstance(raw, dict):
            return {}
        return {k: RedPacket.from_dict(v) for k, v in raw.items()}

    def _save_all(self, packets: Dict[str, RedPacket]) -> None:
        self.kv.set("redpacket", "all", {k: v.to_dict() for k, v in packets.items()})

    def _gen_id(self) -> str:
        """生成 6 位红包 ID。"""
        chars = string.ascii_letters + string.digits
        existing = set(self._load_all().keys())
        while True:
            pid = "".join(random.choices(chars, k=6))
            if pid not in existing:
                return pid

    def create(self, nick: str, trip: str, amount: int, people: int) -> Result:
        """发红包。"""
        if amount < 1:
            return Result.fail("红包金额至少 1 金币")
        if people < 2:
            return Result.fail("红包至少 2 人抢")
        if amount < people:
            return Result.fail("金额太小，每人至少 1 金币")
        if amount > 100000:
            return Result.fail("红包金额过大")

        pid = self._gen_id()
        now = time.time()
        packet = RedPacket(
            packet_id=pid,
            sender_nick=nick,
            sender_trip=trip,
            total_amount=amount,
            remaining_amount=amount,
            total_people=people,
            remaining_people=people,
            created_at=now,
            expire_at=now + DAY,
        )
        packets = self._load_all()
        packets[pid] = packet
        self._save_all(packets)

        return Result.ok(
            f"[OK] {nick} 发了 {amount} 金币红包，{people} 人可抢\n"
            f"红包 ID：{pid}\n"
            f"发送 {config.bot.prefix}packet {pid} 抢红包\n"
            f"24 小时内未抢完自动退还",
            data={"charge": amount},
        )

    def grab(self, nick: str, trip: str, packet_id: str) -> Result:
        """抢红包。"""
        packets = self._load_all()
        packet = packets.get(packet_id)
        if not packet:
            return Result.fail("红包 ID 不存在")
        if packet.is_expired:
            self._cleanup(packets, packet_id)
            return Result.fail("红包已过期")

        user_key = f"{nick}#{trip}" if trip else nick
        if user_key in packet.grabbed:
            return Result.fail("你已经抢过了")

        if packet.is_empty:
            return Result.fail("红包已被抢完")

        # 随机金额：0.01 ~ 平均值的 2 倍
        if packet.remaining_people == 1:
            # 最后一人拿剩余全部
            amount = packet.remaining_amount
        else:
            max_share = int(packet.remaining_amount / packet.remaining_people * 2)
            max_share = max(max_share, 1)
            amount = random.randint(1, max(max_share, 1))
            amount = min(amount, packet.remaining_amount)

        packet.grabbed[user_key] = amount
        packet.remaining_amount -= amount
        packet.remaining_people -= 1
        self._save_all(packets)

        suffix = ""
        if packet.is_empty:
            suffix = "\n红包已被抢完！"
        else:
            suffix = f"\n剩余 {packet.remaining_amount} 金币，{packet.remaining_people} 人可抢"

        return Result.ok(
            f"[OK] {nick} 抢到了 {amount} 金币{suffix}",
            data={"grant": amount, "to_nick": nick, "to_trip": trip},
        )

    def list_packets(self) -> Result:
        """查看当前红包列表。"""
        packets = self._load_all()
        # 清理过期的
        expired = [pid for pid, p in packets.items() if p.is_expired]
        for pid in expired:
            self._cleanup(packets, pid)

        active = [p for p in packets.values() if not p.is_empty]
        if not active:
            return Result.ok("[INFO] 当前没有红包")

        lines = ["[INFO] 当前红包："]
        for p in active:
            lines.append(
                f"ID: {p.packet_id} | {p.sender_nick} 发 | "
                f"剩余 {p.remaining_amount}/{p.total_amount} 金币 | "
                f"{p.remaining_people}/{p.total_people} 人"
            )
        return Result.ok("\n".join(lines))

    def check_expired(self) -> Result:
        """检查过期红包并退还（由定时线程调用）。"""
        packets = self._load_all()
        expired = [pid for pid, p in packets.items() if p.is_expired]
        if not expired:
            return Result.ok("")

        lines = []
        for pid in expired:
            p = packets[pid]
            if p.remaining_amount > 0:
                # 退还剩余金额
                self.coins.add(p.sender_nick, p.sender_trip, p.remaining_amount, reason="红包过期退还")
                lines.append(f"红包 {pid} 已过期，退还 {p.remaining_amount} 金币给 {p.sender_nick}")
            del packets[pid]

        self._save_all(packets)
        return Result.ok("\n".join(lines))

    def _cleanup(self, packets: Dict[str, RedPacket], packet_id: str) -> None:
        """清理过期红包并退还。"""
        p = packets.get(packet_id)
        if p and p.remaining_amount > 0:
            self.coins.add(p.sender_nick, p.sender_trip, p.remaining_amount, reason="红包过期退还")
        packets.pop(packet_id, None)
        self._save_all(packets)
