"""21点 Blackjack（多人，纯逻辑，金币由命令层处理）。

命令风格（BoB 无前缀）：
- bj <bet>     下注加入
- bj start     开始发牌
- bj hit       要牌
- bj stand     停牌
- bj double    双倍下注（仅首回合两张牌时）
- bj check     查看当前局面
- bj quit      退出（未开始时）

Result.data 约定：
- 加入：{"charge": bet}
- 双倍：{"charge": bet}（额外扣同等注注）
- 结算：{"payouts": [{"nick","trip","amount"}]}
"""
from __future__ import annotations

import random
from typing import Dict, List, Optional

from config import config
from core.result import Result
from games.base import BaseGame
from utils.text import user_key

# 牌面定义
SUITS = ["♠", "♥", "♦", "♣"]
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]


def _card_value(rank: str) -> int:
    """返回牌面基础点数（A 按 11 算，后续在 Hand 里动态调整）。"""
    if rank in ("J", "Q", "K"):
        return 10
    if rank == "A":
        return 11
    return int(rank)


class Card:
    __slots__ = ("suit", "rank", "value")

    def __init__(self, suit: str, rank: str):
        self.suit = suit
        self.rank = rank
        self.value = _card_value(rank)

    def __str__(self) -> str:
        return f"{self.suit}{self.rank}"


class Deck:
    """标准 52 张牌堆，自动洗牌。"""

    def __init__(self):
        self.cards: List[Card] = []
        self.reset()

    def reset(self) -> None:
        self.cards = [Card(s, r) for s in SUITS for r in RANKS]
        random.shuffle(self.cards)

    def draw(self) -> Card:
        if not self.cards:
            self.reset()
        return self.cards.pop()


class Hand:
    """手牌：自动处理 A 的 1/11 切换。"""

    def __init__(self, bet: int = 0):
        self.cards: List[Card] = []
        self.bet = bet

    def add(self, card: Card) -> None:
        self.cards.append(card)

    @property
    def total(self) -> int:
        """计算总点数，A 自动在 1 和 11 之间切换避免爆牌。"""
        total = sum(c.value for c in self.cards)
        aces = sum(1 for c in self.cards if c.rank == "A")
        while total > 21 and aces > 0:
            total -= 10
            aces -= 1
        return total

    @property
    def is_blackjack(self) -> bool:
        """天然 21 点（首两张牌 = 21）。"""
        return len(self.cards) == 2 and self.total == 21

    @property
    def is_bust(self) -> bool:
        """爆牌。"""
        return self.total > 21

    @property
    def can_double(self) -> bool:
        """可双倍：仅首两张牌。"""
        return len(self.cards) == 2

    def format(self, hide_second: bool = False) -> str:
        """格式化手牌显示。hide_second=True 时隐藏第二张（庄家暗牌）。"""
        if hide_second and len(self.cards) >= 2:
            shown = " ".join(str(c) for c in self.cards[:1])
            return f"{shown} ??"
        shown = " ".join(str(c) for c in self.cards)
        suffix = ""
        if self.is_bust:
            suffix = " 💥爆牌"
        elif self.is_blackjack:
            suffix = " 🃏Blackjack!"
        return f"{shown} (点数 {self.total}){suffix}"


class Player:
    __slots__ = ("nick", "trip", "hand", "stood", "doubled", "settled")

    def __init__(self, nick: str, trip: str, bet: int):
        self.nick = nick
        self.trip = trip
        self.hand = Hand(bet)
        self.stood = False
        self.doubled = False
        self.settled = False  # 是否已结算（赢/输/平）

    @property
    def is_done(self) -> bool:
        """玩家回合结束（停牌/爆牌/双倍后）。"""
        return self.stood or self.hand.is_bust or self.doubled

    def format(self, is_current: bool = False) -> str:
        prefix = "==>> " if is_current else ""
        return f"{prefix}{self.nick}: {self.hand.format()}"


class BlackjackGame(BaseGame):
    name = "blackjack"
    timeout = config.game.zjh_timeout  # 复用超时配置

    def __init__(self):
        super().__init__()
        self.deck = Deck()
        self.players: Dict[str, Player] = {}  # key -> Player
        self.player_order: List[str] = []  # 加入顺序
        self.current_index = 0
        self.banker_hand: Optional[Hand] = None
        self.phase = "waiting"  # waiting -> playing -> settling -> done

    def reset(self) -> None:
        super().reset()
        self.deck.reset()
        self.players = {}
        self.player_order = []
        self.current_index = 0
        self.banker_hand = None
        self.phase = "waiting"

    @property
    def current_player(self) -> Optional[Player]:
        if not self.player_order or self.phase != "playing":
            return None
        idx = self.player_order[self.current_index]
        return self.players.get(idx)

    # ---- 命令入口 ----

    def join(self, nick: str, trip: str, bet: int) -> Result:
        """下注加入。"""
        if self.phase == "playing":
            return Result.fail("本局已开始，等下一局")
        if self.phase == "done":
            return Result.fail("上一局刚结束，请先重置")
        if bet <= 0:
            return Result.fail("下注需大于 0")

        key = user_key(nick, trip)
        if key in self.players:
            return Result.fail("你已经加入了")

        self.players[key] = Player(nick, trip, bet)
        self.player_order.append(key)
        if not self.active:
            self._start_clock()

        names = "、".join(p.nick for p in self.players.values())
        return Result.ok(
            f"[OK] {nick} 加入，下注 {bet} 金币\n当前玩家：{names}\n发送 bj start 开始",
            data={"charge": bet},
        )

    def quit(self, nick: str, trip: str) -> Result:
        """退出（未开始时）。"""
        if self.phase == "playing":
            return Result.fail("本局已开始，无法退出")
        key = user_key(nick, trip)
        if key not in self.players:
            return Result.fail("你没有加入")
        player = self.players.pop(key)
        self.player_order.remove(key)
        if not self.player_order:
            self.reset()
        return Result.ok(
            f"[OK] {nick} 已退出，退还 {player.hand.bet} 金币",
            data={"refund": player.hand.bet, "to_nick": nick, "to_trip": trip},
        )

    def start(self, nick: str, trip: str) -> Result:
        """开始发牌。"""
        if not self.active or self.expired():
            return Result.fail("没有进行中的21点局，发送 bj <下注> 加入")
        if self.phase != "waiting":
            return Result.fail("本局已开始")
        if len(self.players) < 1:
            return Result.fail("至少需要 1 人才能开始")
        key = user_key(nick, trip)
        if key not in self.players:
            return Result.fail("你还没有加入，发送 bj <下注> 加入")

        self.phase = "playing"
        self.deck.reset()

        # 发牌：每人 2 张，庄家 2 张
        self.banker_hand = Hand()
        for _ in range(2):
            for p in self.players.values():
                p.hand.add(self.deck.draw())
            self.banker_hand.add(self.deck.draw())

        lines = ["[INFO] 发牌完成！", ""]
        lines.append(f"庄家: {self.banker_hand.format(hide_second=True)}")
        lines.append("")
        for k in self.player_order:
            p = self.players[k]
            lines.append(p.format(is_current=(k == self.player_order[self.current_index])))
        lines.append("")
        lines.append(f"轮到 {self.current_player.nick} 操作：bj hit(要牌) / bj stand(停牌) / bj double(双倍)")

        return Result.ok("\n".join(lines))

    def hit(self, nick: str, trip: str) -> Result:
        """要牌。"""
        if self.phase != "playing":
            return Result.fail("没有进行中的21点局")
        player = self._get_current_player(nick, trip)
        if not player:
            return Result.fail("还没轮到你")

        card = self.deck.draw()
        player.hand.add(card)

        lines = [f"[INFO] {player.nick} 摸到 {card}"]
        lines.append(player.format())

        if player.hand.is_bust:
            lines.append(f"{player.nick} 爆牌了！💥")
            self._next_player()
        elif player.hand.total == 21:
            lines.append("正好 21 点，自动停牌")
            player.stood = True
            self._next_player()
        else:
            lines.append("继续：bj hit(要牌) / bj stand(停牌)")

        return Result.ok("\n".join(lines))

    def stand(self, nick: str, trip: str) -> Result:
        """停牌。"""
        if self.phase != "playing":
            return Result.fail("没有进行中的21点局")
        player = self._get_current_player(nick, trip)
        if not player:
            return Result.fail("还没轮到你")

        player.stood = True
        lines = [f"[INFO] {player.nick} 停牌，点数 {player.hand.total}"]
        self._next_player()
        return Result.ok("\n".join(lines))

    def double_cost(self, nick: str, trip: str) -> int:
        """双倍下注需要额外支付的金币（0 表示当前不可双倍）。"""
        if self.phase != "playing":
            return 0
        player = self._get_current_player(nick, trip)
        if not player or not player.hand.can_double:
            return 0
        return player.hand.bet

    def double(self, nick: str, trip: str) -> Result:
        """双倍下注（仅首两张牌）。"""
        if self.phase != "playing":
            return Result.fail("没有进行中的21点局")
        player = self._get_current_player(nick, trip)
        if not player:
            return Result.fail("还没轮到你")
        if not player.hand.can_double:
            return Result.fail("只能在首两张牌时双倍下注")

        # 摸一张牌后自动停牌
        card = self.deck.draw()
        player.hand.add(card)
        player.hand.bet *= 2
        player.doubled = True

        lines = [f"[INFO] {player.nick} 双倍下注！摸到 {card}"]
        lines.append(player.format())
        if player.hand.is_bust:
            lines.append(f"{player.nick} 爆牌了！💥")
        self._next_player()
        return Result.ok(
            "\n".join(lines),
            data={"charge": player.hand.bet // 2},  # 额外扣原注注
        )

    def check(self) -> Result:
        """查看当前局面。"""
        if self.phase == "waiting":
            if not self.players:
                return Result.fail("没有进行中的21点局，发送 bj <下注> 加入")
            names = "、".join(p.nick for p in self.players.values())
            return Result.ok(f"[INFO] 等待开始\n玩家：{names}\n发送 bj start 开始")
        if self.phase == "done":
            return Result.ok("[INFO] 本局已结束，发送 bj <下注> 开始新一局")

        lines = ["[INFO] 当前局面：", ""]
        if self.banker_hand:
            lines.append(f"庄家: {self.banker_hand.format(hide_second=True)}")
        lines.append("")
        for i, k in enumerate(self.player_order):
            p = self.players[k]
            lines.append(p.format(is_current=(i == self.current_index)))
        return Result.ok("\n".join(lines))

    # ---- 内部逻辑 ----

    def _get_current_player(self, nick: str, trip: str) -> Optional[Player]:
        """验证当前操作者是轮到的玩家。"""
        if not self.current_player:
            return None
        key = user_key(nick, trip)
        if key != self.player_order[self.current_index]:
            return None
        if self.current_player.is_done:
            return None
        return self.current_player

    def _next_player(self) -> None:
        """轮到下一位玩家，或进入庄家回合。"""
        self.current_index += 1
        if self.current_index >= len(self.player_order):
            self._banker_play()
        else:
            # 跳过已结束的玩家
            cp = self.current_player
            if cp and cp.is_done:
                self._next_player()

    def _banker_play(self) -> None:
        """庄家自动操作：<17 要牌，>=17 停牌。"""
        self.phase = "settling"
        lines = ["[INFO] 庄家亮牌：", f"庄家: {self.banker_hand.format()}", ""]

        # 检查是否所有玩家都爆了
        all_bust = all(p.hand.is_bust for p in self.players.values())
        if not all_bust:
            while self.banker_hand.total < 17:
                card = self.deck.draw()
                self.banker_hand.add(card)
                lines.append(f"庄家摸到 {card}，点数 {self.banker_hand.total}")
                if self.banker_hand.is_bust:
                    lines.append("庄家爆牌！💥")
                    break

        lines.append("")
        lines.append("---")
        lines.append("结算：")

        banker_total = self.banker_hand.total
        banker_bust = self.banker_hand.is_bust
        payouts = []

        for k in self.player_order:
            p = self.players[k]
            p_total = p.hand.total
            p_bust = p.hand.is_bust

            if p_bust:
                lines.append(f"{p.nick} 爆牌({p_total})，输 {p.hand.bet} 金币 😭")
            elif banker_bust or p_total > banker_total:
                # 玩家赢
                if p.hand.is_blackjack:
                    win = int(p.hand.bet * 1.5)
                    lines.append(f"{p.nick} Blackjack！赢 {win} 金币 🃏🍾")
                else:
                    win = p.hand.bet
                    lines.append(f"{p.nick} 赢({p_total} vs {banker_total})，得 {win} 金币 🍾")
                payouts.append({"nick": p.nick, "trip": p.trip, "amount": win + p.hand.bet})
            elif p_total == banker_total:
                lines.append(f"{p.nick} 平局({p_total})，退回 {p.hand.bet} 金币 🤔")
                payouts.append({"nick": p.nick, "trip": p.trip, "amount": p.hand.bet})
            else:
                lines.append(f"{p.nick} 输({p_total} vs {banker_total})，失去 {p.hand.bet} 金币 😭")

        self.phase = "done"
        self.active = False
        lines.append("")
        lines.append("本局结束，发送 bj <下注> 开始新一局")

        self._result_text = "\n".join(lines)
        self._result_payouts = payouts

    def get_result(self) -> Result:
        """获取结算结果（在 _banker_play 后调用）。"""
        if self.phase != "done":
            return Result.fail("本局尚未结束")
        return Result.ok(getattr(self, "_result_text", ""), data={"payouts": getattr(self, "_result_payouts", [])})
