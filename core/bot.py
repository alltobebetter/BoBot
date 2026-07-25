"""机器人主体：连接、解析消息、构造上下文、分发。

特性：
- 昵称后缀：BoB_Cat / BoB_Nova 等随机后缀，重连时换名避免冲突
- Join 超时检测：4 秒未收到 onlineSet 则判定 join 失败并重连
- 频道验证：定期 leave+join 检测被静默踢出
"""
from __future__ import annotations

import random
import threading
import time
from typing import Optional

from config import config
from core.connection import Connection
from core.context import Context
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
        self._running = False
        self._channel_check_state: Optional[str] = None  # None | "waiting"
        self._last_activity = time.time()

        # 连接（ping 检测连接存活，不活跃不重连）
        self.conn = Connection(
            config.bot.server_url,
            self._on_message,
            self._on_open,
            self._on_disconnect,
            ping_interval=config.bot.ping_interval,
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
            try:
                self.app.history.record(
                    self.config.bot.room, self.nick, "", str(text),
                )
            except Exception:
                pass

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
    def _send_join(self) -> None:
        """发送 join 命令并设置超时检测。"""
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
                log.warning("join 超时，未收到 onlineSet，重连")
                self.conn.force_reconnect()

        threading.Thread(target=_check_join, daemon=True).start()

    def _on_open(self) -> None:
        """连接建立后发送 join。"""
        self._send_join()

        # 进场自我介绍（只发一次，重连不发）
        if not self._intro_sent:
            intro = (
                f"我是 {self.config.bot.name}，版本 {self.VERSION}，已上线！"
                f"输入 help 查看功能～ 开源地址：https://github.com/alltobebetter/BoBot"
            )
            self.say(intro)
            self._intro_sent = True

    def _on_disconnect(self) -> None:
        """连接断开回调：重新生成昵称，避免重复昵称被限制。"""
        log.warning("与聊天室断开连接", old_nick=self.nick)
        self.nick = self._generate_nick()
        log.info("重连将使用新昵称", new_nick=self.nick)
        self.online_users.clear()
        self._channel_check_state = None

    # ---- 消息处理 ----
    def _on_message(self, msg: dict) -> None:
        cmd = msg.get("cmd")
        self._last_activity = time.time()

        # 频道验证响应处理
        if self._channel_check_state == "waiting":
            if cmd == "session":
                # leave 成功，仍在原频道，立即 join 回来
                log.info("频道验证：leave 成功，重新 join")
                self._channel_check_state = None
                self._send_join()
                return
            elif cmd == "warn" and "not in that channel" in (msg.get("text") or "").lower():
                # 被 kick 了，不在原频道
                log.warning("频道验证：不在原频道（被踢），强制重连")
                self._channel_check_state = None
                self.conn.force_reconnect()
                return

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
        web = self.config.bot.web_url
        lines = [
            "[INFO] 此消息仅出现一次。",
            "",
            "@我 + 消息 → AI 聊天",
            "wordle / guess / dice / idiom → 小游戏",
            "checkin → 每日签到领金币",
            "help → 查看全部功能",
            f"网页版：{web}",
            "开源：https://github.com/alltobebetter/BoBot",
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

    # ---- 频道验证 ----
    def _channel_check_loop(self) -> None:
        """后台线程：定期验证 bot 是否仍在正确频道。

        hack.chat 的 kick 是静默的——不关闭连接，只把用户移到随机频道。
        被踢的客户端完全收不到通知，ping 照通，但已经不在原频道了。
        通过 leave + join 主动验证：leave 成功说明还在，立即 join 回来；
        leave 失败说明被踢了，force_reconnect 重新连接。

        仅在长时间无活动时触发（聊天室热闹时肯定没被踢）。
        """
        while self._running:
            time.sleep(60)
            if not self._running:
                break
            quiet = time.time() - self._last_activity
            if (self.conn.is_connected and self._join_confirmed
                    and quiet >= self.config.bot.channel_check_interval):
                self._verify_channel()

    def _verify_channel(self) -> None:
        """发送 leave 验证是否在正确频道，等待响应后 join 回来或重连。"""
        log.info("频道验证：发送 leave", channel=self.config.bot.room)
        self._channel_check_state = "waiting"
        self.conn.send({"cmd": "leave", "channel": self.config.bot.room})

        # 5 秒超时
        def _timeout():
            time.sleep(5)
            if self._channel_check_state == "waiting":
                log.warning("频道验证超时，强制重连")
                self._channel_check_state = None
                self.conn.force_reconnect()

        threading.Thread(target=_timeout, daemon=True).start()

    # ---- 启动/停止 ----
    def run(self) -> None:
        log.info("机器人启动中...", name=self.config.bot.name, nick=self.nick, version=self.VERSION)
        self._running = True
        threading.Thread(target=self._channel_check_loop, daemon=True).start()
        self.conn.run()

    def stop(self) -> None:
        log.info("机器人停止中...")
        self._running = False
        self.conn.stop()
