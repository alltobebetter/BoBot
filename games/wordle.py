"""Wordle（文本版 + 图片版，房间共享一局）。

Pillow + Gyazo 可用时输出彩色棋盘图片，否则降级为纯文本 emoji 反馈。
赢家奖励由命令层发放。
"""
from __future__ import annotations

import random
from pathlib import Path
from typing import Dict, List, Optional, Set

from config import config
from core.result import Result
from games.base import BaseGame

ANSWER_WORDS = [
    "apple", "beach", "brave", "bread", "brick", "chair", "charm", "chess",
    "cloud", "crane", "dance", "dream", "eagle", "earth", "flame", "fresh",
    "ghost", "grape", "green", "heart", "honey", "house", "input", "jolly",
    "knife", "lemon", "light", "lucky", "magic", "money", "mouse", "music",
    "night", "ocean", "paint", "party", "peace", "piano", "pizza", "plant",
    "pride", "queen", "quiet", "radio", "river", "robot", "round", "salad",
    "sheep", "shine", "smile", "snake", "space", "spice", "stone", "storm",
    "sugar", "sweet", "table", "tiger", "toast", "train", "tulip", "unity",
    "vivid", "water", "whale", "wheat", "world", "youth", "zebra",
]

# emoji 映射
_EMOJI = {"correct": "🟩", "present": "🟨", "absent": "⬜"}


class WordleGame(BaseGame):
    name = "wordle"
    MAX_GUESSES = 6

    def __init__(self):
        super().__init__()
        self.timeout = config.game.wordle_timeout
        self.answer = ""
        self.guesses: List[Dict] = []  # [{"nick","word","result":["correct",...],"emoji":"🟩🟨⬜🟩⬜"}]
        self.valid: Set[str] = self._load_valid()

    @staticmethod
    def _load_valid() -> Set[str]:
        path = Path(config.data_dir) / "wordle_valid_guesses.txt"
        try:
            words = {w.strip().lower() for w in path.read_text(encoding="utf-8").splitlines() if len(w.strip()) == 5}
        except Exception:
            words = set()
        words.update(ANSWER_WORDS)
        return words

    def start(self) -> Result:
        if self.active and not self.expired():
            return Result.fail(f"已有一局 Wordle 进行中，直接 {config.bot.prefix}w <单词> 猜")
        self.answer = random.choice(ANSWER_WORDS)
        self.guesses = []
        self._start_clock()
        return Result.ok(f"[INFO] Wordle 开始，5 个字母，6 次机会，发送 {config.bot.prefix}w <单词>")

    def _evaluate(self, word: str) -> List[str]:
        """返回每位的判定结果列表：correct / present / absent。"""
        answer = self.answer
        result = ["absent"] * 5
        counts: Dict[str, int] = {}
        for c in answer:
            counts[c] = counts.get(c, 0) + 1
        # 第一遍：标记位置正确
        for i in range(5):
            if word[i] == answer[i]:
                result[i] = "correct"
                counts[word[i]] -= 1
        # 第二遍：标记存在但位置错
        for i in range(5):
            if result[i] == "correct":
                continue
            c = word[i]
            if counts.get(c, 0) > 0:
                result[i] = "present"
                counts[c] -= 1
        return result

    def _emoji(self, result: List[str]) -> str:
        return "".join(_EMOJI.get(r, "⬜") for r in result)

    def guess(self, nick: str, word: str) -> Result:
        if not self.active or self.expired():
            return Result.fail("没有进行中的 Wordle，wordle 开始")
        word = word.strip().lower()
        if len(word) != 5 or not word.isalpha():
            return Result.fail("请输入 5 个字母的单词")
        if self.valid and word not in self.valid:
            return Result.fail(f'"{word}" 不在词典里')

        result = self._evaluate(word)
        emoji = self._emoji(result)
        self.guesses.append({
            "nick": nick,
            "word": word.upper(),
            "result": result,       # 结构化结果，供图片生成用
            "emoji": emoji,
        })

        # 文本棋盘
        board = "\n".join(
            f"{g['emoji']}  {g['word']}  ({g['nick']})" for g in self.guesses
        )

        if word == self.answer:
            tries = len(self.guesses)
            self.reset()
            return Result.ok(
                f"{board}\n[OK] {nick} 猜对了，答案 {word.upper()}，共 {tries} 次",
                data={"win": True, "tries": tries},
            )
        if len(self.guesses) >= self.MAX_GUESSES:
            answer = self.answer
            self.reset()
            return Result.ok(
                f"{board}\n[ERR] 次数用完了，答案是 {answer.upper()}",
                data={"win": False},
            )
        left = self.MAX_GUESSES - len(self.guesses)
        return Result.ok(f"{board}\n剩余 {left} 次", data={"win": False})

    def hint(self) -> Result:
        if not self.active:
            return Result.fail("没有进行中的 Wordle")
        revealed = set()
        for g in self.guesses:
            for i, mark in enumerate(g["result"]):
                if mark == "correct":
                    revealed.add(i)
        hidden = [i for i in range(5) if i not in revealed]
        if not hidden:
            return Result.fail("已经没有可提示的字母了")
        pos = random.choice(hidden)
        return Result.ok(f'[INFO] 提示：第 {pos + 1} 个字母是 "{self.answer[pos].upper()}"')

    def status(self) -> Result:
        if not self.active or self.expired():
            return Result.fail("没有进行中的 Wordle")
        if not self.guesses:
            return Result.ok("[INFO] Wordle 进行中，还没有人猜")
        board = "\n".join(
            f"{g['emoji']}  {g['word']}  ({g['nick']})" for g in self.guesses
        )
        return Result.ok(board)

    # ---- 图片生成 ----
    def generate_image(self) -> Optional[bytes]:
        """生成当前棋盘的 PNG 图片（Pillow 不可用时返回 None）。"""
        from games.wordle_image import generate_wordle_image

        if not self.guesses:
            return None
        guesses_data = [
            {"word": g["word"], "result": g["result"]}
            for g in self.guesses
        ]
        show_answer = not self.active and self.guesses and self.guesses[-1]["word"].lower() != self.answer
        return generate_wordle_image(
            guesses_data,
            max_guesses=self.MAX_GUESSES,
            show_answer=show_answer,
            answer=self.answer.upper() if self.answer else "",
        )
