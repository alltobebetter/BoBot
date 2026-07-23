"""每条消息的上下文，统一回复/私聊入口。"""
from __future__ import annotations

from typing import List, Optional

from constants import WHISPER_THRESHOLD
from utils.text import user_key


class Context:
    def __init__(
        self,
        bot,
        *,
        nick: str,
        trip: str,
        text: str,
        command: Optional[str] = None,
        args: Optional[List[str]] = None,
        is_whisper: bool = False,
    ):
        self.bot = bot
        self.nick = nick
        self.trip = trip or ""
        self.text = text
        self.command = command
        self.args = args or []
        self.is_whisper = is_whisper

    # ---- 便捷属性 ----
    @property
    def app(self):
        return self.bot.app

    @property
    def user_key(self) -> str:
        return user_key(self.nick, self.trip)

    @property
    def arg_str(self) -> str:
        return " ".join(self.args)

    @property
    def is_admin(self) -> bool:
        return self.bot.config.bot.is_admin(self.nick, self.trip)

    # ---- 回复 ----
    def reply(self, message: str) -> None:
        if not message:
            return
        if self.is_whisper:
            self.bot.whisper(self.nick, message)
        else:
            self.bot.say(message)

    def whisper(self, message: str) -> None:
        if message:
            self.bot.whisper(self.nick, message)

    def reply_smart(self, message: str) -> None:
        """长文本（帮助/排行榜）自动改为私聊，减少刷屏。"""
        if not message:
            return
        if not self.is_whisper and len(message) > WHISPER_THRESHOLD:
            self.bot.whisper(self.nick, message)
            self.bot.say(f"@{self.nick} 已私聊发送")
        else:
            self.reply(message)
