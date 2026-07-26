"""成语接龙。

词库文件：data/games/idiom.json（默认不随仓附带，需自行下载）。
加载器兼容常见的 GitHub 成语数据集格式：
  1. 字符串数组：["一鸣惊人", ...]
  2. 对象数组：[{"word": "一鸣惊人", ...}, ...]（pwxcoo / crazywhalecc / cqqqM 等）
  3. 对象：{"idioms": [...]} 或 {"一鸣惊人": {...}, ...}
若无词库则自动降级为“宽松模式”（只校验 4 个汉字 + 首尾接龙）。
赢家奖励由命令层发放。
"""
from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Set

from config import config
from core.result import Result
from games.base import BaseGame
from utils.logger import log

_HAN = re.compile(r"^[\u4e00-\u9fff]{4}$")
_WORD_KEYS = ("word", "idiom", "成语", "name", "title")
# 发奖里程碑：连接数达到该值时发一档奖励（同一局内每档只发一次）
_MILESTONES = (3, 6, 10)


class IdiomGame(BaseGame):
    name = "idiom"

    def __init__(self):
        super().__init__()
        self.timeout = config.game.idiom_timeout
        self.dictionary: Set[str] = self._load_dict()
        if self.dictionary:
            log.info(f"成语词库已加载：{len(self.dictionary)} 条")
        else:
            log.info("成语词库缺失，成语接龙运行于宽松模式")
        self.current = ""
        self.used: Set[str] = set()
        self.chain = 0
        self.rewarded = 0

    @staticmethod
    def _collect(item, words: Set[str]) -> None:
        if isinstance(item, str):
            if _HAN.match(item):
                words.add(item)
        elif isinstance(item, dict):
            for k in _WORD_KEYS:
                v = item.get(k)
                if isinstance(v, str) and _HAN.match(v):
                    words.add(v)
                    return

    @classmethod
    def _load_dict(cls) -> Set[str]:
        path = Path(config.data_dir) / "idiom.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return set()
        words: Set[str] = set()
        if isinstance(data, list):
            for item in data:
                cls._collect(item, words)
        elif isinstance(data, dict):
            if isinstance(data.get("idioms"), list):
                for item in data["idioms"]:
                    cls._collect(item, words)
            else:
                for key, value in data.items():
                    if isinstance(key, str) and _HAN.match(key):
                        words.add(key)
                    else:
                        cls._collect(value, words)
        return words

    @property
    def strict(self) -> bool:
        return bool(self.dictionary)

    def start(self) -> Result:
        if self.active and not self.expired():
            return Result.fail(f"已有一局成语接龙，接“{self.current}”的末字：{self.current[-1]}")
        if self.strict:
            self.current = random.choice(list(self.dictionary))
        else:
            self.current = "一鸣惊人"
        self.used = {self.current}
        self.chain = 0
        self.rewarded = 0
        self._start_clock()
        mode = "" if self.strict else "（宽松模式：未加载词典）"
        return Result.ok(f"[INFO] 成语接龙开始{mode}，首成语：{self.current}\n接“{self.current[-1]}”字开头的成语")

    def submit(self, idiom: str) -> Result:
        if not self.active or self.expired():
            return Result.fail("没有进行中的成语接龙，/idiom 开始")
        idiom = idiom.strip()
        if not _HAN.match(idiom):
            return Result.fail("请输入 4 个汉字的成语")
        if idiom in self.used:
            return Result.fail("这个成语已经用过了")
        if idiom[0] != self.current[-1]:
            return Result.fail(f"需要以“{self.current[-1]}”开头")
        if self.strict and idiom not in self.dictionary:
            return Result.fail("词典里没有这个成语")
        self.current = idiom
        self.used.add(idiom)
        self.chain += 1
        self._start_clock()  # 刷新计时
        # 只在跨过新里程碑时才告知命令层发奖，tier 为 -1 表示不发奖
        tier = -1
        if self.rewarded < len(_MILESTONES) and self.chain >= _MILESTONES[self.rewarded]:
            tier = self.rewarded
            self.rewarded += 1
        return Result.ok(
            f"[OK] {idiom}，连接 {self.chain} 个，接“{idiom[-1]}”字",
            data={"chain": self.chain, "tier": tier},
        )

    def reset(self) -> None:
        super().reset()
        self.current = ""
        self.used = set()
        self.chain = 0
        self.rewarded = 0

    def skip(self) -> Result:
        """使用成语跳过卡：换一个首成语。"""
        if not self.active:
            return Result.fail("没有进行中的成语接龙")
        if self.strict:
            candidates = [w for w in self.dictionary if w not in self.used]
            self.current = random.choice(candidates) if candidates else self.current
        self.used.add(self.current)
        return Result.ok(f"[INFO] 已跳过，新成语：{self.current}\n接“{self.current[-1]}”字")

    def stop(self) -> Result:
        if not self.active:
            return Result.fail("没有进行中的成语接龙")
        chain = self.chain
        self.reset()
        return Result.ok(f"[INFO] 成语接龙结束，共连接 {chain} 个")
