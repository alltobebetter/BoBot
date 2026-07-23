"""机器人主体：连接、解析消息、构造上下文、分发。

特性：
- 昵称后缀：BoB_Cat / BoB_Nova 等随机后缀，重连时换名避免冲突
- Join 超时检测：4 秒未收到 onlineSet 则判定 join 失败并重连
- 健康监控：不活跃超时自动重连、退避策略、统计追踪
"""
from __future__ import annotations

import random
import threading
import time

from config import config
from core.connection import Connection
from core.context import Context
from core.health_monitor import HealthMonitor
from utils.logger import log


class Bot:
    VERSION = "4.0"

    # 默认欢迎模板（已知用户未设置自定义欢迎词时随机选一条）
    DEFAULT_WELCOME_TEMPLATES = [
        "又见面了，{nick}。",
        "{nick}，欢迎回来。",
        "{nick} 来了。",
        "欢迎回来，{nick}。",
        "{nick}，好久不见。",
        "{nick} 回到聊天室。",
        "{nick} 上线了。",
        "{nick}，最近怎么样？",
    ]

    def __init__(self, router, app):
        self.config = config
        self.router = router
        self.app = app
        app.bot = self  # 反向引用，供 service/工具主动推送

        # 当前昵称（带随机后缀），重连时会重新生成
        self.nick = self._generate_nick()
        self.online_users: dict[str, str] = {}  # {nick: trip}
        self._join_confirmed = False
        self._intro_sent = False  # 进场自我介绍只发一次

        # 连接 & 健康监控
        self.conn = Connection(
            config.bot.server_url,
            self._on_message,
            self._on_open,
            self._on_disconnect,
        )
        self.health = HealthMonitor(
            self,
            check_interval=config.bot.health_check_interval,
            inactive_timeout=config.bot.health_inactive_timeout,
        )

    # ---- 昵称生成 ----
    def _generate_nick(self) -> str:
        """生成带随机后缀的昵称，如 BoB_Cat、BoB_Nova。"""
        suffix = random.choice(self.config.bot.nick_suffixes)
        return f"{self.config.bot.name}_{suffix}"

    # ---- 外发 ----
    def say(self, text: str) -> None:
        if text:
            self.conn.send({"cmd": "chat", "text": str(text)})

    def whisper(self, nick: str, text: str) -> None:
        if text:
            self.conn.send({"cmd": "whisper", "nick": nick, "text": str(text)})

    def say_with_id(self, text: str, custom_id: str) -> None:
        """发送带 customId 的消息，后续可用 update_message 更新。

        同时记入聊天历史（占位），update_message 时会更新为最终内容。
        """
        if not text:
            return
        self.conn.send({"cmd": "chat", "text": str(text), "customId": custom_id})
        try:
            self.app.history.record(
                self.config.bot.room, self.nick, "", str(text),
                custom_id=custom_id,
            )
        except Exception:
            pass

    def whisper_with_id(self, nick: str, text: str, custom_id: str) -> None:
        """发送带 customId 的私聊消息。"""
        if not text:
            return
        self.conn.send({"cmd": "whisper", "nick": nick, "text": str(text), "customId": custom_id})

    def update_message(self, custom_id: str, text: str) -> None:
        """更新已发送消息的内容，并同步到聊天历史。"""
        self.conn.update_message(custom_id, str(text))
        try:
            self.app.history.update_by_custom_id(
                self.config.bot.room, custom_id, str(text)
            )
        except Exception:
            pass

    # ---- 生命周期回调 ----
    def _on_open(self) -> None:
        """连接建立后发送 join。"""
        self._join_confirmed = False
        nick = self.nick
        if self.config.bot.password:
            nick = f"{nick}#{self.config.bot.password}"
        self.conn.send({"cmd": "join", "channel": self.config.bot.room, "nick": nick})
        log.info("加入频道", room=self.config.bot.room, nick=self.nick)

        # join 超时检测：4 秒未收到 onlineSet 则重连
        def _check_join():
            time.sleep(4)
            if not self._join_confirmed:
                log.warning("连接后 4 秒未收到 onlineSet，判定 join 失败，重连")
                self.conn.force_reconnect()

        threading.Thread(target=_check_join, daemon=True).start()

        # 进场自我介绍（只发一次，重连不发）
        if not self._intro_sent:
            intro = f"我是 {self.config.bot.name}，版本 {self.VERSION}，已上线！输入 help 查看功能～"
            self.say(intro)
            self._intro_sent = True

    def _on_disconnect(self) -> None:
        """连接断开回调：重新生成昵称，避免重复昵称被限制。"""
        log.warning("与聊天室断开连接", old_nick=self.nick)
        self.nick = self._generate_nick()
        log.info("重连将使用新昵称", new_nick=self.nick)
        self.online_users.clear()

    # ---- 消息处理 ----
    def _on_message(self, msg: dict) -> None:
        cmd = msg.get("cmd")

        # 记录活动（健康监控）
        if cmd in ("chat", "whisper", "onlineAdd", "onlineRemove", "onlineSet", "info", "warn"):
            self.health.record_activity()

        if cmd == "chat":
            self._handle_chat(msg, is_whisper=False)
        elif cmd == "whisper":
            self._handle_chat(msg, is_whisper=True)
        elif cmd == "info":
            # info 是服务器信息（含自己发出 whisper 的回显），不当作消息处理
            text = msg.get("text", "")
            if text:
                log.info("服务器信息", text=text[:100])
        elif cmd == "onlineAdd":
            self._on_join(msg)
        elif cmd == "onlineSet":
            self._join_confirmed = True
            self.online_users.clear()
            for u in msg.get("users", []) or []:
                nick = u.get("nick", "")
                trip = u.get("trip", "")
                if nick:
                    self.online_users[nick] = trip
                    self.app.afk.seen(nick, trip)
            log.info("当前在线", count=len(self.online_users))
        elif cmd == "onlineRemove":
            nick = msg.get("nick", "")
            self.online_users.pop(nick, None)
        elif cmd == "warn":
            log.warning("服务器警告", text=msg.get("text", ""))

    def _on_join(self, msg: dict) -> None:
        nick = msg.get("nick", "")
        trip = msg.get("trip", "")
        if not nick:
            return
        self.online_users[nick] = trip
        self.app.afk.seen(nick, trip)

        # 三层欢迎逻辑（同 BoBot 原版）
        welcome = self.app.users.welcome_for(nick)
        if welcome:
            # 1. 用户设置了自定义欢迎词
            self.say(welcome)
        elif not self.app.users.is_known(nick):
            # 2. 新用户：创建账户 + 默认欢迎 + 私聊功能介绍
            self.app.users.get_or_create(nick, trip)
            self.say(f"欢迎 {nick} 加入聊天室！输入 help 查看帮助")
            self._whisper_intro(nick)
        else:
            # 3. 已知用户且未设自定义欢迎词：随机模板
            tpl = random.choice(self.DEFAULT_WELCOME_TEMPLATES)
            self.say(tpl.format(nick=nick))

        # 投递待领留言
        self._deliver_messages(nick)

    def _deliver_messages(self, nick: str) -> None:
        """检查并投递该用户的未领留言。"""
        try:
            msgs = self.app.messages.pending(nick)
            if not msgs:
                return
            text = self.app.messages.format_for_delivery(msgs)
            self.whisper(nick, text)
            self.app.messages.mark_delivered(nick)
        except Exception as e:
            log.error("留言投递失败", exc=e, nick=nick)

    def _whisper_intro(self, nick: str) -> None:
        """新用户一次性私聊功能介绍。"""
        lines = [
            "[INFO] 此消息仅出现一次。",
            "",
            "@我 + 消息 → AI 聊天",
            "wordle / guess / dice / idiom → 小游戏",
            "checkin → 每日签到领金币",
            "help → 查看全部功能",
        ]
        self.whisper(nick, "\n".join(lines))

    def _handle_chat(self, msg: dict, is_whisper: bool) -> None:
        nick = msg.get("nick") or msg.get("from")
        if not nick or nick == self.nick:
            return
        trip = msg.get("trip", "") or ""
        text = (msg.get("text") or "").strip()
        # 记录聊天历史
        channel = self.config.bot.room
        try:
            self.app.history.record(channel, nick, trip, text,
                                    custom_id=msg.get("customId"))
        except Exception:
            pass
        command, args = self._parse(text)
        ctx = Context(
            self,
            nick=nick,
            trip=trip,
            text=text,
            command=command,
            args=args,
            is_whisper=is_whisper,
        )
        self.router.dispatch(ctx)

    def _parse(self, text: str):
        prefix = self.config.bot.prefix
        if text.startswith(prefix):
            parts = text[len(prefix):].split()
            if parts:
                return parts[0].lower(), parts[1:]
        return None, []

    # ---- 启动/停止 ----
    def run(self) -> None:
        log.info("机器人启动中...", name=self.config.bot.name, nick=self.nick, version=self.VERSION)
        self.health.start()
        try:
            self.conn.run()
        finally:
            self.health.stop()

    def stop(self) -> None:
        log.info("机器人停止中...")
        self.health.stop()
        self.conn.stop()
