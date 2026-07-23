"""友情链接服务 - Supabase REST API。

用户可添加/删除自己的友情链接，每人限一条。
"""
from __future__ import annotations

import httpx

from config import config
from core.result import Result
from utils.logger import log
from utils.text import user_key


class FriendsService:
    """友情链接管理。"""

    def __init__(self):
        self.url = config.api.supabase_url
        self.key = config.api.supabase_key
        self._endpoint = f"{self.url}/rest/v1/friends"
        self._headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }

    @property
    def available(self) -> bool:
        return bool(self.url and self.key)

    def _author(self, nick: str, trip: str) -> str:
        return user_key(nick, trip)

    def add(self, nick: str, trip: str, link: str, name: str,
            description: str) -> Result:
        if not self.available:
            return Result.fail("友情链接服务未配置")
        author = self._author(nick, trip)
        try:
            # 检查是否已存在
            r = httpx.get(
                f"{self._endpoint}?author=eq.{author}&select=id",
                headers=self._headers, timeout=10.0,
            )
            if r.status_code == 200 and r.json():
                return Result.fail("你已经添加过友情链接了，请先 friend delete 再重新添加")

            r = httpx.post(
                self._endpoint,
                headers={**self._headers, "Prefer": "return=representation"},
                json={"name": name, "url": link, "description": description, "author": author},
                timeout=10.0,
            )
            if r.status_code in (200, 201):
                return Result.ok("[OK] 友情链接添加成功")
            return Result.fail(f"添加失败: {r.text[:200]}")
        except Exception as e:
            log.error("添加友情链接失败", author=author, exc=e)
            return Result.fail(f"添加失败: {e}")

    def delete(self, nick: str, trip: str) -> Result:
        if not self.available:
            return Result.fail("友情链接服务未配置")
        author = self._author(nick, trip)
        try:
            r = httpx.get(
                f"{self._endpoint}?author=eq.{author}&select=id",
                headers=self._headers, timeout=10.0,
            )
            if r.status_code != 200 or not r.json():
                return Result.fail("你还没有添加过友情链接")

            record_id = r.json()[0]["id"]
            r = httpx.delete(
                f"{self._endpoint}?id=eq.{record_id}",
                headers=self._headers, timeout=10.0,
            )
            if r.status_code in (200, 204):
                return Result.ok("[OK] 友情链接已删除")
            return Result.fail(f"删除失败: {r.text[:200]}")
        except Exception as e:
            log.error("删除友情链接失败", author=author, exc=e)
            return Result.fail(f"删除失败: {e}")
