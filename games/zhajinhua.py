"""炸金花（纯逻辑，金币由命令层处理）。

Result.data 约定：
- 加入/跟注/加注：{"charge": n}
- 开牌：{"payout": {nick,trip,amount}}
"""
from __future__ import annotations

import random
from enum import IntEnum
from typing import Dict, List, Tuple

from config import config
from core.result import Result
from games.base import BaseGame
from utils.text import user_key

SUITS = ["♠", "♥", "♦", "♣"]
RANK_NAMES = {11: "J", 12: "Q", 13: "K", 14: "A"}


class HandRank(IntEnum):
    HIGH = 1        # 散牌
    PAIR = 2        # 对子
    FLUSH = 3       # 同花
    STRAIGHT = 4    # 顺子
    STRAIGHT_FLUSH = 5  # 同花顺
    LEOPARD = 6     # 豹子


def _rank_name(r: int) -> str:
    return RANK_NAMES.get(r, str(r))


def card_str(card: Tuple[int, int]) -> str:
    rank, suit = card
    return f"{SUITS[suit]}{_rank_name(rank)}"


def evaluate(cards: List[Tuple[int, int]]) -> Tuple[HandRank, List[int]]:
    ranks = sorted((c[0] for c in cards), reverse=True)
    suits = {c[1] for c in cards}
    is_flush = len(suits) == 1
    is_straight = (ranks[0] - ranks[1] == 1 and ranks[1] - ranks[2] == 1)
    # A-2-3
    if sorted(ranks) == [2, 3, 14]:
        is_straight = True
        ranks = [3, 2, 1]
    if ranks[0] == ranks[1] == ranks[2]:
        return HandRank.LEOPARD, ranks
    if is_flush and is_straight:
        return HandRank.STRAIGHT_FLUSH, ranks
    if is_straight:
        return HandRank.STRAIGHT, ranks
    if is_flush:
        return HandRank.FLUSH, ranks
    if ranks[0] == ranks[1] or ranks[1] == ranks[2]:
        pair = ranks[1]  # 中间那张必属于对子
        kicker = ranks[2] if ranks[0] == ranks[1] else ranks[0]
        return HandRank.PAIR, [pair, pair, kicker]
    return HandRank.HIGH, ranks


def compare_hands(a: List[Tuple[int, int]], b: List[Tuple[int, int]]) -> int:
    ra, ka = evaluate(a)
    rb, kb = evaluate(b)
    if ra != rb:
        return 1 if ra > rb else -1
    if ka != kb:
        return 1 if ka > kb else -1
    return 0


class ZhaJinHuaGame(BaseGame):
    name = "zhajinhua"

    def __init__(self):
        super().__init__()
        self.timeout = config.game.zjh_timeout
        self.players: Dict[str, Dict] = {}
        self.order: List[str] = []
        self.pot = 0
        self.current_bet = 0
        self.started = False

    def start(self, nick: str, trip: str, ante: int) -> Result:
        if self.active and not self.expired():
            return Result.fail("已有一局炸金花，/zjh join 加入")
        if ante <= 0:
            return Result.fail("底注需大于 0")
        self.reset()
        self.players = {}
        self.order = []
        self.pot = 0
        self.current_bet = ante
        self.started = False
        self._start_clock()
        self._add_player(nick, trip)
        self.pot += ante
        return Result.ok(
            f"[INFO] 炸金花开局，底注 {ante}\n其他人 /zjh join 加入，/zjh deal 发牌",
            data={"charge": ante},
        )

    def _add_player(self, nick: str, trip: str) -> str:
        key = user_key(nick, trip)
        self.players[key] = {
            "nick": nick, "trip": trip, "cards": [], "folded": False,
            "seen": False, "bet": self.current_bet,
        }
        self.order.append(key)
        return key

    def join(self, nick: str, trip: str) -> Result:
        if not self.active or self.expired():
            return Result.fail("现在没有炸金花局，/zjh start <底注> 开局")
        if self.started:
            return Result.fail("已开始发牌，无法加入")
        key = user_key(nick, trip)
        if key in self.players:
            return Result.fail("你已在局中")
        self._add_player(nick, trip)
        self.pot += self.current_bet
        return Result.ok(f"[OK] {nick} 加入（底注 {self.current_bet}），奖池 {self.pot}", data={"charge": self.current_bet})

    def deal(self) -> Result:
        if not self.active:
            return Result.fail("没有进行中的炸金花")
        if self.started:
            return Result.fail("已经发过牌了")
        if len(self.players) < 2:
            return Result.fail("至少需要 2 人")
        deck = [(r, s) for r in range(2, 15) for s in range(4)]
        random.shuffle(deck)
        for p in self.players.values():
            p["cards"] = [deck.pop(), deck.pop(), deck.pop()]
        self.started = True
        self._start_clock()
        return Result.ok(
            "[INFO] 已发牌，私聊 /zjh look 看牌，/zjh call 跟注，/zjh raise <n> 加注，/zjh fold 弃牌，/zjh open 开牌"
        )

    def look(self, nick: str, trip: str) -> Result:
        key = user_key(nick, trip)
        p = self.players.get(key)
        if not p or not p["cards"]:
            return Result.fail("你不在局中或还未发牌")
        p["seen"] = True
        rank, _ = evaluate(p["cards"])
        cards = " ".join(card_str(c) for c in p["cards"])
        return Result.ok(f"[INFO] 你的牌：{cards}（{rank.name}）")

    def call(self, nick: str, trip: str) -> Result:
        return self._bet(nick, trip, self.current_bet, is_raise=False)

    def raise_bet(self, nick: str, trip: str, amount: int) -> Result:
        if amount <= self.current_bet:
            return Result.fail(f"加注需大于当前注 {self.current_bet}")
        return self._bet(nick, trip, amount, is_raise=True)

    def _bet(self, nick: str, trip: str, amount: int, is_raise: bool) -> Result:
        if not self.started:
            return Result.fail("还未发牌")
        key = user_key(nick, trip)
        p = self.players.get(key)
        if not p or p["folded"]:
            return Result.fail("你不在局中或已弃牌")
        self.pot += amount
        if is_raise:
            self.current_bet = amount
        self._start_clock()
        verb = "加注到" if is_raise else "跟注"
        return Result.ok(f"[OK] {nick} {verb} {amount}，奖池 {self.pot}", data={"charge": amount})

    def fold(self, nick: str, trip: str) -> Result:
        key = user_key(nick, trip)
        p = self.players.get(key)
        if not p or p["folded"]:
            return Result.fail("你不在局中或已弃牌")
        p["folded"] = True
        alive = [k for k, v in self.players.items() if not v["folded"]]
        if len(alive) == 1:
            return self._settle(alive)
        return Result.ok(f"[INFO] {nick} 弃牌")

    def open(self) -> Result:
        if not self.started:
            return Result.fail("还未发牌")
        alive = [k for k, v in self.players.items() if not v["folded"]]
        if not alive:
            return Result.fail("没有存活玩家")
        return self._settle(alive, reveal=True)

    def _settle(self, alive: List[str], reveal: bool = False) -> Result:
        best_key = alive[0]
        for k in alive[1:]:
            if compare_hands(self.players[k]["cards"], self.players[best_key]["cards"]) > 0:
                best_key = k
        winner = self.players[best_key]
        pot = self.pot
        lines = ["[INFO] 开牌："] if reveal else []
        if reveal:
            for k in alive:
                p = self.players[k]
                rank, _ = evaluate(p["cards"])
                lines.append(f"{p['nick']}: {' '.join(card_str(c) for c in p['cards'])} ({rank.name})")
        lines.append(f"[OK] 赢家：{winner['nick']}，得奖池 {pot} 金币")
        payout = {"nick": winner["nick"], "trip": winner["trip"], "amount": pot}
        self.reset()
        self.players = {}
        self.order = []
        self.pot = 0
        self.current_bet = 0
        self.started = False
        return Result.ok("\n".join(lines), data={"payout": payout})
