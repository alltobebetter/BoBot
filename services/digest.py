"""每日总结服务：AI 驱动的聊天室日报。

- 定时触发：每天指定时间自动生成并发送
- 手动触发：用户发 today 时，若当天已有总结则展示，否则提示
- 总结存入 digests 表，避免重复生成
"""
from __future__ import annotations

import threading
import time
from datetime import timedelta
from typing import Optional

from core.result import Result
from utils.logger import log
from utils.text import now, today_str


class DigestService:
    """每日聊天总结。"""

    # 定时发送时间（CST 小时），默认 23:00
    SCHEDULE_HOUR = 23
    SCHEDULE_MINUTE = 0

    # 触发总结的最低消息数
    MIN_MESSAGES = 10

    SYSTEM_PROMPT = (
        "你是 HackChat 聊天室的日报编辑。根据今天的聊天记录，写一份简短的日报。"
        "要求：口语化、有趣味，不要罗列每条消息，而是提炼亮点。"
        "格式：先一句话概括，再分 2-3 个亮点。不要使用 emoji，不要用波浪号，语气平实。"
        "控制在 200 字以内。"
    )

    PROMPT_TEMPLATE = """以下是「{channel}」频道 {date} 的聊天记录（共 {count} 条）。
请生成一份日报：

{messages}
"""

    def __init__(self, app):
        self.app = app
        self._timer_thread: Optional[threading.Thread] = None
        self._running = False

    # ---- 查询 ----

    def get_today(self, channel: str) -> Optional[str]:
        """获取今天的总结（若已生成）。"""
        date = today_str()
        row = self.app.db.query_one(
            "SELECT content FROM digests WHERE date=? AND channel=?",
            (date, channel),
        )
        return row["content"] if row else None

    def get_by_date(self, date: str, channel: str) -> Optional[str]:
        """获取指定日期的总结。"""
        row = self.app.db.query_one(
            "SELECT content FROM digests WHERE date=? AND channel=?",
            (date, channel),
        )
        return row["content"] if row else None

    # ---- 生成 ----

    def generate(self, channel: str, date: Optional[str] = None) -> Result:
        """生成指定日期的总结并存库。"""
        date = date or today_str()
        # 已存在则不重复生成
        existing = self.get_by_date(date, channel)
        if existing:
            return Result.ok(existing)

        # 取当天消息
        msgs = self.app.history.by_date(date, channel=channel, limit=2000)
        if len(msgs) < self.MIN_MESSAGES:
            return Result.fail(f"当天消息不足 {self.MIN_MESSAGES} 条，暂不生成总结")

        # 拼接消息文本（最多取 500 条，避免 token 爆炸）
        sample = msgs[:500]
        lines = [f"[{m['ts'][11:16]}] {m['nick']}: {m['text'][:100]}" for m in sample]
        msg_text = "\n".join(lines)

        prompt = self.PROMPT_TEMPLATE.format(
            channel=channel, date=date, count=len(msgs), messages=msg_text,
        )

        if not self.app.ai.enabled:
            return Result.fail("AI 未启用，无法生成总结")

        result = self.app.ai.chat_oneshot(
            system_prompt=self.SYSTEM_PROMPT,
            prompt=prompt,
            max_tokens=1024,
        )
        if not result:
            return Result.fail("总结生成失败")

        content = result.message
        # 存库
        self.app.db.execute(
            "INSERT OR REPLACE INTO digests(date,channel,content,msg_count,created_ts) "
            "VALUES(?,?,?,?,?)",
            (date, channel, content, len(msgs), now().isoformat()),
        )
        return Result.ok(content)

    # ---- 定时触发 ----

    def start_scheduler(self, bot) -> None:
        """启动后台定时器，每天 SCHEDULE_HOUR:SCHEDULE_MINUTE 自动生成并发送。"""
        self._running = True
        self._timer_thread = threading.Thread(target=self._schedule_loop, args=(bot,), daemon=True)
        self._timer_thread.start()
        log.info("每日总结定时器已启动", hour=self.SCHEDULE_HOUR, minute=self.SCHEDULE_MINUTE)

    def stop_scheduler(self) -> None:
        self._running = False

    def _schedule_loop(self, bot) -> None:
        while self._running:
            try:
                now_dt = now()
                # 计算到今天 SCHEDULE_HOUR:SCHEDULE_MINUTE 的秒数
                target = now_dt.replace(
                    hour=self.SCHEDULE_HOUR, minute=self.SCHEDULE_MINUTE, second=0, microsecond=0
                )
                if now_dt >= target:
                    # 已过今天的目标时间，等明天
                    target = target + timedelta(days=1)
                wait_secs = (target - now_dt).total_seconds()
                # 最多等 1 小时检查一次（避免线程卡死）
                while wait_secs > 0 and self._running:
                    sleep_secs = min(wait_secs, 3600)
                    time.sleep(sleep_secs)
                    wait_secs -= sleep_secs

                if not self._running:
                    break

                # 生成并发送
                channel = bot.config.bot.room
                result = self.generate(channel)
                if result:
                    bot.say(f"[INFO] 今日总结\n\n{result.message}")
                else:
                    log.info("每日总结未生成", reason=result.message)
            except Exception as e:
                log.error("每日总结定时任务异常", exc=e)
                time.sleep(60)
