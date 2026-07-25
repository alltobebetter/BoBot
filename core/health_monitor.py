"""健康监控器 — 监控连接状态、不活跃超时、自动重连。"""
from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING, Optional

from utils.logger import log

if TYPE_CHECKING:
    from core.bot import Bot


class HealthMonitor:
    """后台线程，定期检查连接健康状态。

    - 连接断开 → 通知 Connection 重连
    - 长时间无活动 → 强制重连（避免静默断连）
    - 连续失败退避 → 5 次后额外等待 30s
    """

    def __init__(self, bot: "Bot", check_interval: int = 10, inactive_timeout: int = 300):
        self.bot = bot
        self.check_interval = check_interval
        self.inactive_timeout = inactive_timeout

        self.running = False
        self._thread: Optional[threading.Thread] = None
        self._last_activity = time.time()
        self._consecutive_failures = 0

        # 统计
        self.stats = {
            "checks": 0,
            "reconnects": 0,
            "failures": 0,
            "uptime_start": None,
        }

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.stats["uptime_start"] = time.time()
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        log.info("健康监控器已启动", interval=self.check_interval, timeout=self.inactive_timeout)

    def stop(self) -> None:
        self.running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        log.info("健康监控器已停止")

    def record_activity(self) -> None:
        """收到消息时调用，重置不活跃计时器。"""
        self._last_activity = time.time()
        self._consecutive_failures = 0

    def _monitor_loop(self) -> None:
        while self.running:
            try:
                time.sleep(self.check_interval)
                self._check_health()
            except Exception as e:
                log.error("健康检查异常", exc=e)

    def _check_health(self) -> None:
        self.stats["checks"] += 1

        # 检查连接状态
        if not self.bot.conn.is_connected:
            self._handle_disconnection()
            return

        # 检查活动超时
        inactive = time.time() - self._last_activity
        if inactive > self.inactive_timeout:
            log.warning("连接不活跃超时，强制重连", inactive=int(inactive), threshold=self.inactive_timeout)
            self._handle_disconnection()

    def _handle_disconnection(self) -> None:
        self._consecutive_failures += 1
        self.stats["failures"] += 1

        # 退避：连续失败超过 5 次，额外等待 30s
        if self._consecutive_failures > 5:
            log.warning("连续失败次数过多，额外等待", count=self._consecutive_failures)
            time.sleep(30)

        log.info("尝试重新连接...", attempt=self._consecutive_failures)
        try:
            self.bot.conn.force_reconnect()
            self.stats["reconnects"] += 1
            self._last_activity = time.time()
        except Exception as e:
            log.error("重连失败", exc=e)
