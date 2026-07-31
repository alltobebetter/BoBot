"""广告栏：发布需花金币，观看获随机奖励（每日限频）。

数据全部存于 SQLite 的 kv 表：
- namespace='ads'  key='pool'          -> 广告列表
- namespace='ads'  key='views:<key>:<date>' -> 当日观看次数
"""
from __future__ import annotations

import random
from typing import List

from config import config
from core.result import Result
from storage.kv import KVStore
from utils.text import now, today_str, truncate

_NS = "ads"
_POOL = "pool"
_MAX_POOL = 50


class AdsService:
    def __init__(self, kv: KVStore, coins):
        self.kv = kv
        self.coins = coins

    def _pool(self) -> List[dict]:
        return self.kv.get(_NS, _POOL, []) or []

    def _save_pool(self, pool: List[dict]) -> None:
        self.kv.set(_NS, _POOL, pool[-_MAX_POOL:])

    def post(self, nick: str, trip: str, text: str) -> Result:
        text = (text or "").strip()
        if not text:
            return Result.fail("广告内容不能为空")
        cost = config.ads.post_cost
        spend = self.coins.spend(nick, trip, cost, reason="发布广告")
        if not spend:
            return spend
        pool = self._pool()
        pool.append({"nick": nick, "text": truncate(text, 200), "ts": now().isoformat(), "views": 0})
        self._save_pool(pool)
        return Result.ok(f"[OK] 广告已发布（花费 {cost} 金币）")

    def view(self, nick: str, trip: str) -> Result:
        from utils.text import user_key

        pool = self._pool()
        if not pool:
            return Result.fail(f"目前没有广告，发送 {config.bot.prefix}ad <内容> 来发布")
        key = user_key(nick, trip)
        vkey = f"views:{key}:{today_str()}"
        views = self.kv.get(_NS, vkey, 0)
        limit = config.ads.daily_view_limit
        if views >= limit:
            return Result.fail(f"今日观看已达上限（{limit} 次），明天再来")
        ad = random.choice(pool)
        reward = random.randint(config.ads.view_reward_min, config.ads.view_reward_max)
        self.coins.add(nick, trip, reward, reason="观看广告")
        self.kv.set(_NS, vkey, views + 1)
        # 单条广告观看计数，达到上限自动下架
        ad["views"] = ad.get("views", 0) + 1
        cap = config.ads.ad_view_cap
        cap_info = f"（{ad['views']}/{cap}）"
        if ad["views"] >= cap:
            pool = [a for a in pool if a is not ad]
            self._save_pool(pool)
            cap_info = "（已达上限，已下架）"
        else:
            self._save_pool(pool)
        return Result.ok(
            f"[INFO] {ad['nick']} 的广告：\n{ad['text']}\n\n[OK] 获得 {reward} 金币（今日 {views + 1}/{limit}）{cap_info}"
        )
