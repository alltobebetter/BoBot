"""猜数字（GuessGame 1-100）与 1A2B（NumberGame）。

赢家奖励由命令层发放（Result.data["win"]）。
"""
from __future__ import annotations

import random

from core.result import Result
from games.base import BaseGame


class GuessGame(BaseGame):
    name = "guess"

    def __init__(self):
        super().__init__()
        self.answer = 0
        self.low = 1
        self.high = 100
        self.tries = 0

    def start(self) -> Result:
        if self.active:
            return Result.fail(f"已有一局猜数字（范围 {self.low}-{self.high}），直接 /g <数字>")
        self.answer = random.randint(1, 100)
        self.low, self.high, self.tries = 1, 100, 0
        self._start_clock()
        return Result.ok("[INFO] 猜数字开始，1-100，发送 /g <数字>")

    def guess(self, n: int) -> Result:
        if not self.active:
            return Result.fail("没有进行中的猜数字，/guess 开始")
        if n < 1 or n > 100:
            return Result.fail("请猜 1-100 之间的数字")
        self.tries += 1
        if n == self.answer:
            tries = self.tries
            self.reset()
            return Result.ok(f"[OK] 猜对了，答案就是 {n}，共用 {tries} 次", data={"win": True, "tries": tries})
        if n < self.answer:
            self.low = max(self.low, n + 1)
            hint = "大一点"
        else:
            self.high = min(self.high, n - 1)
            hint = "小一点"
        return Result.ok(f"{hint}（范围 {self.low}-{self.high}）", data={"win": False})


class NumberGame(BaseGame):
    name = "number"

    def __init__(self):
        super().__init__()
        self.answer = ""
        self.tries = 0

    def start(self) -> Result:
        if self.active:
            return Result.fail("已有一局 1A2B，直接 /n <4位不重复数字>")
        digits = random.sample("0123456789", 4)
        self.answer = "".join(digits)
        self.tries = 0
        self._start_clock()
        return Result.ok("[INFO] 1A2B 开始，猜 4 位不重复数字，发送 /n <数字>\nA=位置正确 B=数字对位置错")

    def guess(self, s: str) -> Result:
        if not self.active:
            return Result.fail("没有进行中的 1A2B，/number 开始")
        s = s.strip()
        if len(s) != 4 or not s.isdigit() or len(set(s)) != 4:
            return Result.fail("请输入 4 位不重复的数字")
        a = sum(1 for i in range(4) if s[i] == self.answer[i])
        b = sum(1 for c in s if c in self.answer) - a
        self.tries += 1
        if a == 4:
            tries = self.tries
            self.reset()
            return Result.ok(f"[OK] 猜对了，答案 {self.answer}（上局），共 {tries} 次", data={"win": True, "tries": tries})
        return Result.ok(f"{s} → {a}A{b}B（第 {self.tries} 次）", data={"win": False})
