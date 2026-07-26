"""身份查询服务（aka）：基于 hash 记录用户历史昵称。

hack.chat 的 hash 基于 IP 地址生成，比 trip（基于密码）更稳定。
用户换密码 trip 会变，但 IP 不变 hash 就不变。

数据存储：KV 持久化，结构为 {hash: {nicks: [...], first_seen, last_seen}}。
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional

from core.result import Result
from storage.kv import KVStore


class IdentityService:
    """记录 hash → [历史昵称] 昵称列表，支持反查。"""

    def __init__(self, kv: KVStore):
        self.kv = kv

    def record(self, nick: str, hash_code: str) -> None:
        """记录用户的 hash 和昵称（在 on_join/on_set 时调用）。"""
        if not hash_code or not nick:
            return
        data = self.kv.get("identity", "hashes") or {}
        entry = data.get(hash_code)
        now_ts = time.time()
        if entry is None:
            data[hash_code] = {
                "nicks": [nick],
                "first_seen": now_ts,
                "last_seen": now_ts,
            }
        else:
            if nick not in entry["nicks"]:
                entry["nicks"].append(nick)
                # 最多保留 50 个昵称
                if len(entry["nicks"]) > 50:
                    entry["nicks"] = entry["nicks"][-50:]
            entry["last_seen"] = now_ts
            data[hash_code] = entry
        self.kv.set("identity", "hashes", data)

    def lookup_by_nick(self, nick: str) -> Result:
        """通过昵称反查身份记录。"""
        data = self.kv.get("identity", "hashes") or {}
        results = []
        for hash_code, entry in data.items():
            if nick in entry.get("nicks", []):
                results.append((hash_code, entry))
        if not results:
            return Result.fail(f"没有找到 {nick} 的身份记录")
        lines = [f"[INFO] {nick} 的身份记录"]
        for i, (hash_code, entry) in enumerate(results, 1):
            nicks = entry.get("nicks", [])
            first = _format_ts(entry.get("first_seen", 0))
            last = _format_ts(entry.get("last_seen", 0))
            # 标记当前昵称
            nick_list = []
            for n in nicks:
                if n == nick:
                    nick_list.append(f"**{n}**")
                else:
                    nick_list.append(n)
            lines.append(
                f"\n{i}. Hash: {hash_code}\n"
                f"   历史昵称: {', '.join(nick_list)}\n"
                f"   首次出现: {first}\n"
                f"   最后出现: {last}"
            )
        return Result.ok("\n".join(lines))

    def lookup_by_hash(self, hash_code: str) -> Result:
        """直接通过 hash 查询历史昵称。"""
        data = self.kv.get("identity", "hashes") or {}
        entry = data.get(hash_code)
        if not entry:
            return Result.fail(f"没有找到 hash {hash_code} 的记录")
        nicks = entry.get("nicks", [])
        first = _format_ts(entry.get("first_seen", 0))
        last = _format_ts(entry.get("last_seen", 0))
        return Result.ok(
            f"[INFO] Hash: {hash_code}\n"
            f"历史昵称: {', '.join(nicks)}\n"
            f"首次出现: {first}\n"
            f"最后出现: {last}"
        )


class MottoService:
    """个人签名服务：用 KV Store 存储 user_key → motto。"""

    def __init__(self, kv: KVStore):
        self.kv = kv

    def set(self, user_key: str, motto: str) -> Result:
        """设置个人签名。"""
        if not motto:
            return Result.fail("签名不能为空")
        if len(motto) > 100:
            return Result.fail("签名太长了（最多 100 字符）")
        data = self.kv.get("motto", "all") or {}
        data[user_key] = motto
        self.kv.set("motto", "all", data)
        return Result.ok(f"[OK] 签名已设置：{motto}")

    def get(self, user_key: str) -> Optional[str]:
        """获取个人签名。"""
        data = self.kv.get("motto", "all") or {}
        return data.get(user_key)

    def clear(self, user_key: str) -> Result:
        """清除签名。"""
        data = self.kv.get("motto", "all") or {}
        if user_key in data:
            del data[user_key]
            self.kv.set("motto", "all", data)
            return Result.ok("[OK] 签名已清除")
        return Result.fail("你没有设置签名")


def _format_ts(ts: float) -> str:
    """格式化时间戳。"""
    if not ts:
        return "未知"
    import time as _t
    return _t.strftime("%Y-%m-%d %H:%M:%S", _t.gmtime(ts + 8 * 3600))  # UTC+8
