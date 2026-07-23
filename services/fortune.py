"""每日运势（同一用户同一天结果固定）。"""
from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import List

from core.result import Result
from utils.text import today_str, user_key


class FortuneService:
    def __init__(self, data_dir: str = "data/games"):
        self.data = self._load(Path(data_dir) / "fortune.json")

    @staticmethod
    def _load(path: Path) -> dict:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    @property
    def available(self) -> bool:
        return bool(self.data.get("levels"))

    def daily(self, nick: str, trip: str) -> Result:
        if not self.available:
            return Result.fail("运势数据未加载")
        seed = f"{user_key(nick, trip)}:{today_str()}"
        rng = random.Random(int(hashlib.md5(seed.encode()).hexdigest(), 16))
        levels = self.data["levels"]
        level = rng.choices(levels, weights=[l.get("weight", 1) for l in levels])[0]
        name = level["name"]
        lo, hi = level.get("star_range", [3, 4])
        stars = rng.randint(lo, hi)
        tags = self.data.get("tags", [[]])
        tag = rng.choice(tags) if tags else []
        poem = self._pick(rng, self.data.get("poems", {}), name)
        summary = self._pick(rng, self.data.get("summaries", {}), name)
        star_str = "★" * stars + "☆" * (7 - stars)
        lines = [
            f"[INFO] {nick} 今日运势：{name}",
            f"星级：{star_str}",
        ]
        if tag:
            lines.append("宜：" + " - ".join(tag))
        if poem:
            lines.append(f"签诗：{poem}")
        if summary:
            lines.append(f"解读：{summary}")
        return Result.ok("\n".join(lines), data={"level": name, "stars": stars})

    @staticmethod
    def _pick(rng: random.Random, mapping: dict, name: str) -> str:
        pool: List = mapping.get(name) or []
        if not pool:
            return ""
        return rng.choice(pool)
