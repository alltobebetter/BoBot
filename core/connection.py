"""HackChat WebSocket 连接（自动重连 + ping 存活检测）。"""
from __future__ import annotations

import json
import threading
import time
from typing import Callable, Optional

import websocket  # websocket-client

from utils.logger import log


class Connection:
    def __init__(
        self,
        url: str,
        on_message: Callable[[dict], None],
        on_open: Optional[Callable[[], None]] = None,
        on_disconnect: Optional[Callable[[], None]] = None,
        ping_interval: int = 30,
    ):
        self.url = url
        self.on_message = on_message
        self.on_open = on_open
        self.on_disconnect = on_disconnect
        self.ping_interval = ping_interval
        self.ws: Optional[websocket.WebSocket] = None
        self._running = False
        self._connected = False
        self._send_lock = threading.Lock()
        self._reconnect_count = 0

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> None:
        self.ws = websocket.create_connection(self.url, timeout=30)
        self.ws.settimeout(None)  # recv 不超时，由 ping 检测连接存活
        self._connected = True
        self._reconnect_count = 0
        log.info("已连接服务器", url=self.url)
        if self.on_open:
            self.on_open()

    def send(self, payload: dict) -> None:
        with self._send_lock:
            if self.ws is not None and self._connected:
                try:
                    raw = json.dumps(payload, ensure_ascii=False)
                    log.info("发送", data=raw)
                    self.ws.send(raw)
                except Exception as e:
                    log.warning("发送失败", error=str(e))

    def update_message(self, custom_id: str, text: str) -> None:
        """更新已发送消息的内容（需要发送时带 customId）。"""
        self.send({"cmd": "updateMessage", "customId": custom_id, "text": text})

    def force_reconnect(self) -> None:
        """强制关闭当前连接，触发 run() 循环重连。"""
        log.info("强制重连：关闭当前连接")
        self._connected = False
        self._safe_close()

    def _keepalive(self) -> None:
        """定期 ping 检测连接存活。

        ping 失败说明连接已断（TCP 断开或半开），
        关闭 ws 使 run() 的 recv() 抛异常从而触发重连。
        """
        while self._running:
            time.sleep(self.ping_interval)
            if not self._running:
                break
            try:
                if self.ws is not None and self._connected:
                    self.ws.ping()
            except Exception as e:
                log.warning("ping 失败，连接可能已断", error=str(e))
                self._connected = False
                self._safe_close()  # 触发 recv() 异常 → run() 重连

    def run(self) -> None:
        self._running = True
        threading.Thread(target=self._keepalive, daemon=True).start()
        while self._running:
            try:
                if self.ws is None:
                    self.connect()
                data = self.ws.recv()
                if not data:
                    continue
                msg = json.loads(data)
                log.info("收到", data=json.dumps(msg, ensure_ascii=False))
                self.on_message(msg)
            except Exception as e:
                if not self._running:
                    break
                was_connected = self._connected
                self._connected = False
                # 仅在之前已连接的情况下通知 on_disconnect（避免初始化时误触发）
                if was_connected and self.on_disconnect:
                    try:
                        self.on_disconnect()
                    except Exception as cb_err:
                        log.error("on_disconnect 回调异常", exc=cb_err)
                self._reconnect_count += 1
                # 退避策略：前 3 次固定 5s，之后递增到最大 30s
                if self._reconnect_count <= 3:
                    delay = 5
                else:
                    delay = min(5 * (self._reconnect_count - 2), 30)
                log.warning(
                    "连接中断，重连中",
                    error=str(e),
                    attempt=self._reconnect_count,
                    delay=delay,
                )
                self._safe_close()
                time.sleep(delay)

    def _safe_close(self) -> None:
        self._connected = False
        try:
            if self.ws is not None:
                self.ws.close()
        except Exception:
            pass
        self.ws = None

    def stop(self) -> None:
        self._running = False
        self._safe_close()
