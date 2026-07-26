"""经济系统：金币、背包、商店、签到。

重要：所有金币流动都经过 CoinService；游戏不直接操作金币，
而是由命令层在游戏接受操作后再扣/发金币，避免“扣了钱却没加成”的 bug。
"""
from __future__ import annotations

import random
from typing import Dict, List, Optional

from config import config
from constants import ITEMS, item_name
from core.result import Result
from storage.db import Database
from utils.text import now, user_key


class CoinService:
    def __init__(self, db: Database, users):
        self.db = db
        self.users = users

    def balance(self, nick: str, trip: str) -> int:
        return self.users.get_or_create(nick, trip)["coins"]

    def _log(self, key: str, amount: int, balance: int, reason: str) -> None:
        self.db.execute(
            "INSERT INTO transactions(user_key,amount,balance,reason,ts) VALUES(?,?,?,?,?)",
            (key, amount, balance, reason, now().isoformat()),
        )

    def add(self, nick: str, trip: str, amount: int, reason: str = "") -> Result:
        if amount == 0:
            return Result.ok(data={"balance": self.balance(nick, trip)})
        u = self.users.get_or_create(nick, trip)
        key = u["user_key"]
        # 原子自增，避免多线程读-改-写丢更新
        self.db.execute(
            "UPDATE users SET coins=coins+?, updated_at=? WHERE user_key=?",
            (amount, now().isoformat(), key),
        )
        row = self.db.query_one("SELECT coins FROM users WHERE user_key=?", (key,))
        new_bal = row["coins"] if row else u["coins"] + amount
        self._log(key, amount, new_bal, reason)
        return Result.ok(data={"balance": new_bal})

    def spend(self, nick: str, trip: str, amount: int, reason: str = "") -> Result:
        if amount <= 0:
            return Result.fail("金额无效")
        u = self.users.get_or_create(nick, trip)
        key = u["user_key"]
        # 带余额条件的原子扣减：余额不足时 rowcount 为 0
        cur = self.db.execute(
            "UPDATE users SET coins=coins-?, updated_at=? WHERE user_key=? AND coins>=?",
            (amount, now().isoformat(), key, amount),
        )
        if cur.rowcount == 0:
            row = self.db.query_one("SELECT coins FROM users WHERE user_key=?", (key,))
            have = row["coins"] if row else 0
            return Result.fail(f"金币不足（需要 {amount}，你有 {have}）")
        row = self.db.query_one("SELECT coins FROM users WHERE user_key=?", (key,))
        new_bal = row["coins"] if row else 0
        self._log(key, -amount, new_bal, reason)
        return Result.ok(data={"balance": new_bal})

    def transfer(self, nick: str, trip: str, to_key: str, amount: int) -> Result:
        if amount <= 0:
            return Result.fail("转账金额需大于 0")
        from_key = user_key(nick, trip)
        if from_key == to_key:
            return Result.fail("不能给自己转账")
        target = self.users.get(to_key)
        if not target:
            return Result.fail("对方还没有账户（需对方先发过言）")
        spend = self.spend(nick, trip, amount, reason=f"转账给 {to_key}")
        if not spend:
            return spend
        self.add(target["nick"], target["trip"], amount, reason=f"来自 {from_key} 的转账")
        return Result.ok(
            f"[OK] 已转账 {amount} 金币给 {target['nick']}，余额 {spend.data['balance']}",
            data={"balance": spend.data["balance"]},
        )

    def rankings(self, limit: int = 10) -> List[Dict]:
        return self.db.query(
            "SELECT user_key, nick, coins FROM users ORDER BY coins DESC, updated_at ASC LIMIT ?",
            (limit,),
        )

    def rank_of(self, key: str) -> Optional[int]:
        row = self.db.query_one(
            "SELECT COUNT(*)+1 AS r FROM users WHERE coins > "
            "(SELECT coins FROM users WHERE user_key=?)",
            (key,),
        )
        return row["r"] if row else None


class InventoryService:
    def __init__(self, db: Database, users):
        self.db = db
        self.users = users

    def get_all(self, key: str) -> Dict[str, int]:
        rows = self.db.query(
            "SELECT item_id, qty FROM inventory WHERE user_key=? AND qty>0", (key,)
        )
        return {r["item_id"]: r["qty"] for r in rows}

    def count(self, key: str, item_id: str) -> int:
        r = self.db.query_one(
            "SELECT qty FROM inventory WHERE user_key=? AND item_id=?", (key, item_id)
        )
        return r["qty"] if r else 0

    def add(self, key: str, item_id: str, qty: int = 1) -> Result:
        self.db.execute(
            "INSERT INTO inventory(user_key,item_id,qty) VALUES(?,?,?) "
            "ON CONFLICT(user_key,item_id) DO UPDATE SET qty=qty+excluded.qty",
            (key, item_id, qty),
        )
        return Result.ok()

    def use(self, key: str, item_id: str, qty: int = 1) -> Result:
        have = self.count(key, item_id)
        if have < qty:
            return Result.fail(f"你没有 {item_name(item_id)}")
        self.db.execute(
            "UPDATE inventory SET qty=qty-? WHERE user_key=? AND item_id=?",
            (qty, key, item_id),
        )
        return Result.ok()


class ShopService:
    def __init__(self, coins: CoinService, inventory: InventoryService, users):
        self.coins = coins
        self.inventory = inventory
        self.users = users

    def catalog(self) -> Dict[str, int]:
        s = config.shop
        return {
            "double_card": s.double_card_price,
            "skip_card": s.skip_card_price,
            "hint_card": s.hint_card_price,
            "color_card": s.color_card_price,
            "mystery_box": s.mystery_box_price,
        }

    def list_text(self) -> str:
        cat = self.catalog()
        lines = ["[INFO] 商店"]
        for item_id, price in cat.items():
            if item_id == "mystery_box":
                lines.append(f"• mystery_box 神秘盒子 - {price} 金币（随机奖励）")
            else:
                info = ITEMS.get(item_id, {})
                lines.append(
                    f"• {item_id} {info.get('name', item_id)} - {price} 金币（{info.get('desc', '')}）"
                )
        lines.append("购买：/buy <物品id> [数量]")
        return "\n".join(lines)

    def buy(self, nick: str, trip: str, item_id: str, qty: int = 1) -> Result:
        cat = self.catalog()
        price = cat.get(item_id)
        if price is None:
            return Result.fail("商品不存在，发送 /shop 查看")
        if qty <= 0:
            return Result.fail("数量无效")
        total = price * qty
        spend = self.coins.spend(nick, trip, total, reason=f"购买 {item_id} x{qty}")
        if not spend:
            return spend
        key = user_key(nick, trip)
        if item_id == "mystery_box":
            # 按数量逐个开盒，避免收了 qty 份钱只开一次
            reward = sum(random.randint(0, max(1, price * 2)) for _ in range(qty))
            add = self.coins.add(nick, trip, reward, reason="神秘盒子")
            return Result.ok(
                f"[OK] 打开神秘盒子 x{qty}，花费 {total} 金币，"
                f"获得 {reward} 金币，余额 {add.data['balance']}",
                data={"balance": add.data["balance"]},
            )
        self.inventory.add(key, item_id, qty)
        return Result.ok(
            f"[OK] 购买成功：{item_name(item_id)} x{qty}，花费 {total} 金币，余额 {spend.data['balance']}",
            data={"balance": spend.data["balance"]},
        )


class CheckinService:
    def __init__(self, db: Database, users, coins: CoinService, inventory: InventoryService):
        self.db = db
        self.users = users
        self.coins = coins
        self.inventory = inventory

    def checkin(self, nick: str, trip: str) -> Result:
        from utils.text import today_str, yesterday_str

        key = user_key(nick, trip)
        u = self.users.get_or_create(nick, trip)
        today = today_str()
        if u["last_checkin"] == today:
            return Result.fail("今天已签到，明天再来")
        streak = u["streak"] + 1 if u["last_checkin"] == yesterday_str() else 1
        count_today = self.db.query_one(
            "SELECT COUNT(*) AS c FROM checkins WHERE date=?", (today,)
        )["c"]
        rank = count_today + 1
        r = config.rewards
        base = r.checkin_base
        rank_bonus = r.checkin_rank_bonus[rank - 1] if rank - 1 < len(r.checkin_rank_bonus) else 0
        streak_bonus = r.checkin_streak_bonus.get(streak, 0)
        total = base + rank_bonus + streak_bonus
        doubled = False
        if self.inventory.count(key, "double_card") > 0:
            self.inventory.use(key, "double_card")
            total *= 2
            doubled = True
        self.db.execute(
            "INSERT INTO checkins(user_key,date,rank,ts) VALUES(?,?,?,?)",
            (key, today, rank, now().isoformat()),
        )
        self.db.execute(
            "UPDATE users SET last_checkin=?, streak=? WHERE user_key=?",
            (today, streak, key),
        )
        self.coins.add(nick, trip, total, reason="签到")
        msg = f"[OK] 签到成功，今日第 {rank} 位\n连续 {streak} 天 | 基础 {base}"
        if rank_bonus:
            msg += f" +排名 {rank_bonus}"
        if streak_bonus:
            msg += f" +连签 {streak_bonus}"
        if doubled:
            msg += " ×2(翻倍卡)"
        msg += f"\n共获得 {total} 金币"
        return Result.ok(msg, data={"total": total, "rank": rank, "streak": streak})

    def today_list(self) -> List[Dict]:
        from utils.text import today_str

        return self.db.query(
            "SELECT c.user_key, c.rank, u.nick FROM checkins c "
            "LEFT JOIN users u ON u.user_key=c.user_key "
            "WHERE c.date=? ORDER BY c.rank",
            (today_str(),),
        )
