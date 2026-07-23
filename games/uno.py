"""UNO（多人，纯逻辑）。赢家奖励由命令层发放。"""
from __future__ import annotations

import random
from typing import Dict, List, Optional

from core.result import Result
from games.base import BaseGame
from utils.text import user_key

COLORS = ["R", "G", "B", "Y"]
COLOR_NAME = {"R": "🔴红", "G": "🟢绿", "B": "🔵蓝", "Y": "🟡黄", "W": "⭐百搭"}


def _build_deck() -> List[Dict]:
    deck: List[Dict] = []
    for c in COLORS:
        deck.append({"color": c, "value": "0"})
        for v in list("123456789") + ["skip", "reverse", "+2"]:
            deck.append({"color": c, "value": v})
            deck.append({"color": c, "value": v})
    for _ in range(4):
        deck.append({"color": "W", "value": "wild"})
        deck.append({"color": "W", "value": "+4"})
    random.shuffle(deck)
    return deck


def card_label(card: Dict) -> str:
    if card["color"] == "W":
        return card["value"]
    return f"{card['color']}{card['value']}"


class UnoGame(BaseGame):
    name = "uno"

    def __init__(self):
        super().__init__()
        self.players: Dict[str, Dict] = {}
        self.order: List[str] = []
        self.hands: Dict[str, List[Dict]] = {}
        self.deck: List[Dict] = []
        self.discard: Optional[Dict] = None
        self.current_color = ""
        self.turn = 0
        self.direction = 1
        self.started = False

    # ---- 大厅 ----
    def start(self, nick: str, trip: str) -> Result:
        if self.active:
            return Result.fail("已有一局 UNO，/uno join 加入")
        self.reset()
        self.players = {}
        self.order = []
        self.hands = {}
        self.started = False
        self._start_clock()
        self._add(nick, trip)
        return Result.ok(f"[INFO] UNO 开局，{nick} 已加入\n其他人 /uno join，房主 /uno begin 开始")

    def _add(self, nick: str, trip: str) -> str:
        key = user_key(nick, trip)
        self.players[key] = {"nick": nick, "trip": trip}
        self.order.append(key)
        return key

    def join(self, nick: str, trip: str) -> Result:
        if not self.active:
            return Result.fail("现在没有 UNO 局，/uno start 开局")
        if self.started:
            return Result.fail("已开始，无法加入")
        key = user_key(nick, trip)
        if key in self.players:
            return Result.fail("你已在局中")
        self._add(nick, trip)
        return Result.ok(f"[OK] {nick} 加入（当前 {len(self.players)} 人）")

    def begin(self) -> Result:
        if not self.active:
            return Result.fail("没有 UNO 局")
        if self.started:
            return Result.fail("已经开始了")
        if len(self.players) < 2:
            return Result.fail("至少需要 2 人")
        self.deck = _build_deck()
        self.hands = {k: [self.deck.pop() for _ in range(7)] for k in self.order}
        first = self.deck.pop()
        while first["color"] == "W":
            self.deck.insert(0, first)
            first = self.deck.pop()
        self.discard = first
        self.current_color = first["color"]
        self.turn = 0
        self.direction = 1
        self.started = True
        self._start_clock()
        return Result.ok(
            f"[INFO] UNO 开始，首张：{card_label(first)}\n轮到：{self._current_nick()}\n"
            f"/uno hand 看手牌，/uno play <牌> 出牌，/uno draw 摸牌"
        )

    # ---- 辅助 ----
    def _current_key(self) -> str:
        return self.order[self.turn]

    def _current_nick(self) -> str:
        return self.players[self._current_key()]["nick"]

    def _advance(self, steps: int = 1) -> None:
        n = len(self.order)
        self.turn = (self.turn + self.direction * steps) % n

    def _draw_cards(self, key: str, count: int) -> None:
        for _ in range(count):
            if not self.deck:
                self.deck = _build_deck()
            self.hands[key].append(self.deck.pop())

    def hand(self, nick: str, trip: str) -> Result:
        key = user_key(nick, trip)
        if key not in self.hands:
            return Result.fail("你不在局中")
        cards = " ".join(card_label(c) for c in self.hands[key])
        return Result.ok(f"[INFO] 你的手牌：{cards}\n当前牌面：{card_label(self.discard)}（颜色 {COLOR_NAME.get(self.current_color, self.current_color)}）")

    def _playable(self, card: Dict) -> bool:
        if card["color"] == "W":
            return True
        return card["color"] == self.current_color or card["value"] == self.discard["value"]

    def play(self, nick: str, trip: str, card_text: str, color: Optional[str] = None) -> Result:
        if not self.started:
            return Result.fail("UNO 还未开始")
        key = user_key(nick, trip)
        if key != self._current_key():
            return Result.fail(f"还没轮到你（当前：{self._current_nick()}）")
        card_text = card_text.strip()
        card = self._find_card(key, card_text)
        if not card:
            return Result.fail("你没有这张牌（例：R5 / G+2 / wild / +4）")
        if not self._playable(card):
            return Result.fail(f"不能出这张牌，当前牌面 {card_label(self.discard)}")
        self.hands[key].remove(card)
        self.discard = card
        msg_extra = ""
        if card["color"] == "W":
            chosen = (color or "").upper()
            if chosen not in COLORS:
                chosen = random.choice(COLORS)
                msg_extra = f"（未指定颜色，随机为 {COLOR_NAME[chosen]}）"
            self.current_color = chosen
        else:
            self.current_color = card["color"]
        # 胜利判定
        if not self.hands[key]:
            winner = self.players[key]
            self.reset()
            self.started = False
            return Result.ok(f"[OK] {winner['nick']} 出完所有牌，胜利", data={"win": True, "nick": winner["nick"], "trip": winner["trip"]})
        # 功能牌效果
        value = card["value"]
        skip = False
        if value == "reverse":
            self.direction *= -1
            if len(self.order) == 2:
                skip = True
        elif value == "skip":
            skip = True
        elif value == "+2":
            self._advance(1)
            self._draw_cards(self._current_key(), 2)
            msg_extra += f" {self._current_nick()} 摸 2 张并跳过"
            skip = True
        elif value == "+4":
            self._advance(1)
            self._draw_cards(self._current_key(), 4)
            msg_extra += f" {self._current_nick()} 摸 4 张并跳过"
            skip = True
        self._advance(2 if skip else 1)
        remaining = len(self.hands[key])
        uno_warn = " [WARN] UNO!" if remaining == 1 else ""
        return Result.ok(
            f"[INFO] {nick} 出 {card_label(card)}{msg_extra}\n现在轮到：{self._current_nick()}（牌面 {card_label(self.discard)} / {COLOR_NAME.get(self.current_color, self.current_color)}）{uno_warn}",
            data={"win": False},
        )

    def draw(self, nick: str, trip: str) -> Result:
        if not self.started:
            return Result.fail("UNO 还未开始")
        key = user_key(nick, trip)
        if key != self._current_key():
            return Result.fail(f"还没轮到你（当前：{self._current_nick()}）")
        self._draw_cards(key, 1)
        drawn = self.hands[key][-1]
        self._advance(1)
        return Result.ok(f"[INFO] {nick} 摸了一张牌，轮到：{self._current_nick()}", data={"drawn": card_label(drawn)})

    def _find_card(self, key: str, text: str) -> Optional[Dict]:
        text = text.strip().lower()
        for c in self.hands[key]:
            if card_label(c).lower() == text:
                return c
        return None

    def status(self) -> Result:
        if not self.active:
            return Result.fail("没有进行中的 UNO")
        if not self.started:
            names = "、".join(p["nick"] for p in self.players.values())
            return Result.ok(f"[INFO] UNO 等待中：{names}\n房主 /uno begin 开始")
        counts = "、".join(f"{self.players[k]['nick']}({len(self.hands[k])})" for k in self.order)
        return Result.ok(f"[INFO] 牌面 {card_label(self.discard)} / {COLOR_NAME.get(self.current_color, self.current_color)}\n轮到：{self._current_nick()}\n手牌数：{counts}")
