"""机器人主体：连接、解析消息、构造上下文、分发。

特性：
- isBot 标记：join 时声明 Bot 身份，客户端显示机器人图标
- 昵称后缀：BoB_Cat / BoB_Nova 等随机后缀，重连时换名避免冲突
- Join 超时检测：4 秒未收到 onlineSet 则判定 join 失败并重连
- 频道验证：定期 leave+join 检测被静默踢出
- 完整用户信息：online_users 存储 level/isBot/color 等完整字段
- updateUser 事件：跟踪用户改名/改色，保持 online_users 同步
- emote 动作描述：发送 * BoB <动作> 风格的消息
- warn 精确处理：根据服务器 error id 区分限流/权限/找不到用户
- 长消息截断：超过服务器限流阈值时自动分条发送
"""
from __future__ import annotations

import random
import threading
import time
from typing import Any, Dict, Optional

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
        self.online_users: Dict[str, Dict[str, Any]] = {}  # {nick: {trip, level, isBot, color, ...}}
        self._join_confirmed = False
        self._intro_sent = False  # 进场自我介绍只发一次
        self._running = False
        self._channel_check_state: Optional[str] = None  # None | "waiting"
        self._last_activity = time.time()
        # 服务器返回的统计信息（morestats 响应）
        self._last_server_stats: Optional[dict] = None
        # session 会话恢复：保存服务器返回的 JWT token，重连时优先尝试恢复
        self._session_token: Optional[str] = None
        self._session_pending = False  # True = 正在等待 session 恢复响应

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

    # ---- 服务器端限流阈值（text.length / 83 / 4，超过 ~8 分触发）----
    # hack.chat 服务器对 chat 消息按文本长度计算 spam score
    # 为安全起见，单条消息超过 300 字符时分条发送
    MAX_MSG_LEN = 300

    # ---- 外发 ----
    def say(self, text: str) -> None:
        if not text:
            return
        text = str(text)
        # 长消息分条发送，避免触发服务器端限流
        if len(text) <= self.MAX_MSG_LEN:
            self._send_chat(text)
        else:
            for chunk in self._split_message(text, self.MAX_MSG_LEN):
                self._send_chat(chunk)

    def _send_chat(self, text: str) -> None:
        """发送单条 chat 消息并记录历史。"""
        self.conn.send({"cmd": "chat", "text": text})
        try:
            self.app.history.record(
                self.config.bot.room, self.nick, "", text,
            )
        except Exception:
            pass

    @staticmethod
    def _split_message(text: str, max_len: int):
        """按换行符智能分条，避免在词中间截断。"""
        lines = text.split("\n")
        chunk = ""
        for line in lines:
            if len(chunk) + len(line) + 1 > max_len:
                if chunk:
                    yield chunk
                # 单行超长也硬截断
                while len(line) > max_len:
                    yield line[:max_len]
                    line = line[max_len:]
                chunk = line
            else:
                chunk = chunk + "\n" + line if chunk else line
        if chunk:
            yield chunk

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

    def update_message(self, custom_id: str, text: str, mode: str = "overwrite") -> None:
        """更新已发送消息的内容，并同步到聊天历史。

        服务器对活跃消息保留 5 分钟（ACTIVE_TIMEOUT），超时后静默失败。
        """
        self.conn.update_message(custom_id, str(text), mode=mode)
        if mode == "overwrite":
            try:
                self.app.history.update_by_custom_id(
                    self.config.bot.room, custom_id, str(text)
                )
            except Exception:
                pass

    def emote(self, text: str) -> None:
        """发送动作描述（emote），客户端显示为 * BoB <动作>。

        适用于游戏动作、状态变化等非正式消息，与 chat 视觉上区分。
        """
        if text:
            self.conn.emote(str(text))
            try:
                self.app.history.record(
                    self.config.bot.room, self.nick, "", f"* {str(text)}",
                )
            except Exception:
                pass

    # ---- 生命周期回调 ----
    def _send_join(self) -> None:
        """发送 join 命令并设置超时检测。

        设置 isBot: true，服务器会将级别设为 99（bot），
        客户端显示机器人图标。
        """
        self._join_confirmed = False
        nick = self.nick
        if self.config.bot.password:
            nick = f"{nick}#{self.config.bot.password}"
        self.conn.send({
            "cmd": "join",
            "channel": self.config.bot.room,
            "nick": nick,
            "isBot": True,
        })
        log.info("加入频道", room=self.config.bot.room, nick=self.nick)

        # join 超时检测：4 秒未收到 onlineSet 则重连
        def _check_join():
            time.sleep(4)
            if not self._join_confirmed:
                log.warning("join 超时，未收到 onlineSet，重连")
                self.conn.force_reconnect()

        threading.Thread(target=_check_join, daemon=True).start()

    def _on_open(self) -> None:
        """连接建立后优先尝试 session 恢复，失败则 join。

        session 恢复可保持昵称不变，避免每次重连换名。
        服务器 JWT token 有效期 7 天，重连时复用即可。
        """
        if self._session_token:
            log.info("尝试 session 恢复", nick=self.nick)
            self._session_pending = True
            self._join_confirmed = False
            self.conn.send({"cmd": "session", "token": self._session_token})

            # 超时检测：4 秒未收到 session 响应则 fallback 到 join
            def _check_session():
                time.sleep(4)
                if self._session_pending:
                    log.warning("session 恢复超时，fallback 到 join")
                    self._session_pending = False
                    self.nick = self._generate_nick()
                    self._send_join()

            threading.Thread(target=_check_session, daemon=True).start()
        else:
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
        """连接断开回调。

        如果有 session token，重连时优先尝试恢复（保持昵称不变）；
        没有 token 或恢复失败时才重新生成昵称。
        """
        log.warning("与聊天室断开连接", old_nick=self.nick)
        if not self._session_token:
            self.nick = self._generate_nick()
            log.info("重连将使用新昵称", new_nick=self.nick)
        else:
            log.info("有 session token，重连将尝试恢复昵称", nick=self.nick)
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

        # session 命令处理（会话恢复 + join 后的 token 保存）
        if cmd == "session":
            token = msg.get("token", "")
            restored = msg.get("restored", False)
            if self._session_pending:
                # 正在等待 session 恢复响应
                self._session_pending = False
                if restored and token:
                    log.info("session 恢复成功，保持昵称", nick=self.nick)
                    self._session_token = token
                    # 恢复成功后服务器会自动发送 onlineSet，等待即可
                else:
                    log.warning("session 恢复失败，fallback 到 join")
                    self._session_token = None
                    self.nick = self._generate_nick()
                    self._send_join()
            elif token:
                # join 成功后服务器返回的 session token，保存供下次重连用
                self._session_token = token
                log.info("已保存 session token")
            return

        if cmd == "chat":
            self._handle_chat(msg, is_whisper=False)
        elif cmd == "whisper":
            self._handle_chat(msg, is_whisper=True)
        elif cmd == "info":
            self._handle_info(msg)
        elif cmd == "emote":
            # 别人的 emote 动作也记录到聊天历史
            nick = msg.get("nick", "")
            if nick and nick != self.nick:
                try:
                    self.app.history.record(
                        self.config.bot.room, nick, msg.get("trip", ""),
                        msg.get("text", ""),
                    )
                except Exception:
                    pass
        elif cmd == "onlineAdd":
            self._on_join(msg)
        elif cmd == "onlineSet":
            self._join_confirmed = True
            self.online_users.clear()
            for u in msg.get("users", []) or []:
                self._add_online_user(u)
            log.info("当前在线", count=len(self.online_users))
        elif cmd == "onlineRemove":
            nick = msg.get("nick", "")
            self.online_users.pop(nick, None)
        elif cmd == "updateUser":
            self._on_update_user(msg)
        elif cmd == "warn":
            self._handle_warn(msg)

    def _add_online_user(self, u: dict) -> None:
        """将服务器返回的用户信息存入 online_users。"""
        nick = u.get("nick", "")
        if not nick:
            return
        self.online_users[nick] = {
            "trip": u.get("trip", ""),
            "level": u.get("level", 100),
            "isBot": u.get("isBot", False),
            "color": u.get("color"),
            "flair": u.get("flair"),
            "hash": u.get("hash", ""),
            "userid": u.get("userid"),
        }
        self.app.afk.seen(nick, u.get("trip", ""))

    def _on_update_user(self, msg: dict) -> None:
        """处理 updateUser 事件（用户改名/改色/改flair）。

        服务器在 changecolor/changenick/forcecolor/forceflair 时广播此事件。
        """
        new_nick = msg.get("nick", "")
        # 通过 userid 找到旧昵称
        userid = msg.get("userid")
        old_nick = None
        for n, info in self.online_users.items():
            if info.get("userid") == userid:
                old_nick = n
                break
        if old_nick and new_nick and old_nick != new_nick:
            # 用户改名了
            self.online_users[new_nick] = self.online_users.pop(old_nick)
            log.info("用户改名", old=old_nick, new=new_nick)
        # 更新颜色/flair/level
        if new_nick and new_nick in self.online_users:
            if "color" in msg:
                self.online_users[new_nick]["color"] = msg.get("color")
            if "flair" in msg:
                self.online_users[new_nick]["flair"] = msg.get("flair")
            if "level" in msg:
                self.online_users[new_nick]["level"] = msg.get("level")

    def _handle_info(self, msg: dict) -> None:
        """处理服务器 info 消息。

        根据 id 字段区分不同类型：
        - STATS_FULL (1005): morestats 返回的统计信息
        - NICK_CHANGED (1001): 用户改名通知
        - MOTD (1004): 每日消息
        """
        text = msg.get("text", "")
        info_id = msg.get("id")
        if info_id == 1005:
            # morestats 响应，保存完整数据
            self._last_server_stats = {
                "users": msg.get("users", 0),
                "channels": msg.get("chans", 0),
                "joins": msg.get("joins", 0),
                "messages": msg.get("messages", 0),
                "banned": msg.get("banned", 0),
                "kicked": msg.get("kicked", 0),
                "uptime": msg.get("uptime", ""),
                "text": text,
            }
            log.info("收到服务器统计", users=msg.get("users"), channels=msg.get("chans"))
        elif text:
            log.info("服务器信息", text=text[:100])

    def _handle_warn(self, msg: dict) -> None:
        """根据 warn id 精确处理服务器警告。

        hack.chat 服务器 error id 对照（_Constants.js）：
        - 11: RATELIMIT（发送太快）
        - 12: UNKNOWN_USER（找不到用户）
        - 13: PERMISSION（权限不足）
        - 16: UNKNOWN_CMD（未知命令）
        - 17: INVALID_PAYLOAD（无效数据）
        """
        text = msg.get("text", "")
        warn_id = msg.get("id")
        if warn_id == 11:
            log.warning("服务器限流", text=text)
        elif warn_id == 12:
            log.warning("服务器：找不到用户", text=text)
        else:
            log.warning("服务器警告", text=text, id=warn_id)

    def _on_join(self, msg: dict) -> None:
        nick = msg.get("nick", "")
        if not nick:
            return
        self._add_online_user(msg)

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
