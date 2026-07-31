"""多人比大小骰子（纯逻辑，金币由命令层处理）。

Result.data 约定：
- 加入/开局：{"charge": bet}    → 命令层扣 bet
- 结算：{"payouts": [{nick,trip,amount}]} → 命令层发放
"""
from __future__ import annotations

import random
from typing import Dict

from config import config
from core.result import Result
from games.base import BaseGame
from utils.text import dice_emoji, user_key


class DiceGame(BaseGame):
    name = "dice"

    def __init__(self):
        super().__init__()
        self.timeout = config.game.dice_timeout
        self.players: Dict[str, Dict] = {}
        self.pot = 0

    def start(self, nick: str, trip: str, bet: int) -> Result:
        if self.active and not self.expired():
            return Result.fail(f"已有一局骰子进行中，发送 {config.bot.prefix}dice join <注注> 加入")
        if bet <= 0:
            return Result.fail("注注需大于 0")
        self.reset()
        self.players = {}
        self.pot = 0
        self._start_clock()
        key = user_key(nick, trip)
        self.players[key] = {"nick": nick, "trip": trip, "bet": bet, "roll": 0}
        self.pot += bet
        return Result.ok(
            f"[OK] {nick} 开局，注注 {bet} 金币\n其他人发送 {config.bot.prefix}dice join <注注> 加入，{config.bot.prefix}dice roll 开骰",
            data={"charge": bet},
        )

    def join(self, nick: str, trip: str, bet: int) -> Result:
        if not self.active or self.expired():
            return Result.fail(f"现在没有骰子局，发送 {config.bot.prefix}dice <注注> 开局")
        if bet <= 0:
            return Result.fail("注注需大于 0")
        key = user_key(nick, trip)
        if key in self.players:
            return Result.fail("你已经在局中了")
        self.players[key] = {"nick": nick, "trip": trip, "bet": bet, "roll": 0}
        self.pot += bet
        return Result.ok(f"[OK] {nick} 加入，注注 {bet}，当前奖池 {self.pot}", data={"charge": bet})

    def roll(self) -> Result:
        if not self.active:
            return Result.fail("没有进行中的骰子局")
        if len(self.players) < 2:
            return Result.fail("至少需要 2 人才能开骰")
        lines = ["[INFO] 开骰结果："]
        best = -1
        for p in self.players.values():
            p["roll"] = random.randint(1, 6)
            lines.append(f"{p['nick']}: {dice_emoji(p['roll'])} ({p['roll']})")
            best = max(best, p["roll"])
        winners = [p for p in self.players.values() if p["roll"] == best]
        share = self.pot // len(winners)
        payouts = [
            {"nick": w["nick"], "trip": w["trip"], "amount": share} for w in winners
        ]
        names = "、".join(w["nick"] for w in winners)
        lines.append(f"[OK] 赢家：{names}，各得 {share} 金币（奖池 {self.pot}）")
        pot = self.pot
        self.reset()
        self.players = {}
        self.pot = 0
        return Result.ok("\n".join(lines), data={"payouts": payouts, "pot": pot})

    def status(self) -> Result:
        if not self.active or self.expired():
            return Result.fail("没有进行中的骰子局")
        names = "、".join(f"{p['nick']}({p['bet']})" for p in self.players.values())
        return Result.ok(f"[INFO] 当前骰子局：{names}\n奖池 {self.pot}")
