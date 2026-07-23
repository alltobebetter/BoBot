"""轻量 HTTP API Server（内嵌于 Bot 进程，守护线程运行）。

绑定 :: (IPv6) + 端口 8300~8499，随 Bot 进程运行。
通过 Bearer Token 鉴权，Vercel 服务端代理调用，前端不暴露地址与密钥。

零额外依赖：仅用 Python 内置 http.server + json。
"""
from __future__ import annotations

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from utils.logger import log


class ApiServer:
    """HTTP API 服务器，在守护线程中运行，共享 App 的 SQLite 数据库。"""

    def __init__(self, app, host: str = "::", port: int = 8300, api_key: str = ""):
        self.app = app
        self.host = host
        self.port = port
        self.api_key = api_key
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if not self.api_key:
            log.warning("API_KEY 未设置，API Server 不会启动（安全考虑）")
            return

        # 依次尝试绑定地址：:: (IPv6) → 0.0.0.0 (IPv4) → "" (all)
        bind_candidates = []
        configured = self.host
        if configured == "::":
            bind_candidates = ["::", "0.0.0.0", ""]
        elif configured == "0.0.0.0":
            bind_candidates = ["0.0.0.0", "", "::"]
        else:
            bind_candidates = [configured, "0.0.0.0", ""]

        for host in bind_candidates:
            try:
                # IPv6 需要设置 address_family
                addr_family = socket.AF_INET6 if ":" in host else socket.AF_INET
                cls = type(
                    "DualStackServer",
                    (ThreadingHTTPServer,),
                    {"address_family": addr_family},
                )
                self._server = cls(
                    (host, self.port),
                    self._make_handler(),
                )
                self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
                self._thread.start()
                log.info("API Server 已启动", host=host, port=self.port)
                return
            except OSError as e:
                log.warning("绑定失败，尝试下一个地址", host=host, error=str(e))
                continue

        log.error("API Server 启动失败：所有绑定地址均不可用")

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            log.info("API Server 已停止")

    # ---- Handler 工厂 ----

    def _make_handler(self):
        app_ref = self.app
        api_key = self.api_key

        class Handler(BaseHTTPRequestHandler):
            # 静默日志（避免刷屏）
            def log_message(self, fmt, *args):
                pass

            def _json(self, data: Any, status: int = 200) -> None:
                body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
                self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
                self.end_headers()
                self.wfile.write(body)

            def _check_auth(self) -> bool:
                auth = self.headers.get("Authorization", "")
                if auth.startswith("Bearer "):
                    token = auth[7:]
                    return token == api_key
                # 也支持 query param ?key=xxx（方便调试）
                parsed = urlparse(self.path)
                qs = parse_qs(parsed.query)
                return qs.get("key", [""])[0] == api_key

            def do_OPTIONS(self) -> None:
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
                self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
                self.end_headers()

            def do_GET(self) -> None:
                if not self._check_auth():
                    self._json({"error": "Unauthorized"}, 401)
                    return

                parsed = urlparse(self.path)
                path = parsed.path.rstrip("/") or "/"
                qs = parse_qs(parsed.query)

                try:
                    data = self._route(path, qs)
                    self._json(data)
                except Exception as e:
                    log.error("API 异常", path=path, exc=e)
                    self._json({"error": str(e)}, 500)

            # ---- 路由 ----

            def _route(self, path: str, qs: Dict[str, List[str]]) -> Any:
                a = app_ref

                # ---- 健康检查 ----
                if path == "/health":
                    return {
                        "ok": True,
                        "bot_nick": a.bot.nick if a.bot else None,
                        "connected": a.bot.conn.is_connected if a.bot else False,
                        "online_count": len(a.bot.online_users) if a.bot else 0,
                        "version": "4.0",
                    }

                # ---- 在线用户 ----
                if path == "/online":
                    users = a.bot.online_users if a.bot else {}
                    return {
                        "count": len(users),
                        "users": [{"nick": n, "trip": t} for n, t in users.items()],
                    }

                # ---- 聊天统计 ----
                if path == "/stats/top":
                    limit = int(qs.get("limit", ["10"])[0])
                    return a.stats.top_chatters(limit)

                if path == "/stats/weekly":
                    limit = int(qs.get("limit", ["10"])[0])
                    return a.stats.top_weekly(limit)

                if path == "/stats/today":
                    return {
                        "messages": a.history.count_today(a.config.bot.room),
                    }

                # ---- 游戏排行 ----
                if path == "/stats/game":
                    game = qs.get("game", [""])[0]
                    if not game:
                        return {"error": "Missing param: game"}
                    limit = int(qs.get("limit", ["10"])[0])
                    return a.stats.game_ranking(game, limit)

                # ---- 最近消息 ----
                if path == "/messages/recent":
                    limit = min(int(qs.get("limit", ["20"])[0]), 100)
                    return a.history.recent(limit=limit, channel=a.config.bot.room)

                # ---- 搜索消息 ----
                if path == "/messages/search":
                    q = qs.get("q", [""])[0]
                    if not q:
                        return {"error": "Missing param: q"}
                    limit = min(int(qs.get("limit", ["20"])[0]), 50)
                    return a.history.search(q, limit=limit, channel=a.config.bot.room)

                # ---- 按日期查询 ----
                if path == "/messages/by_date":
                    date = qs.get("date", [""])[0]
                    if not date:
                        return {"error": "Missing param: date"}
                    limit = min(int(qs.get("limit", ["500"])[0]), 2000)
                    return a.history.by_date(date, channel=a.config.bot.room, limit=limit)

                # ---- 可用日期列表 ----
                if path == "/messages/dates":
                    return {"dates": a.history.available_dates(channel=a.config.bot.room)}

                # ---- 金币排行 ----
                if path == "/economy/top":
                    limit = int(qs.get("limit", ["10"])[0])
                    return a.coins.rankings(limit)

                # ---- 今日签到 ----
                if path == "/checkin/today":
                    return a.checkin.today_list()

                # ---- 金句 ----
                if path == "/quotes/recent":
                    limit = int(qs.get("limit", ["20"])[0])
                    return a.quotes.recent(channel=a.config.bot.room, limit=limit)

                if path == "/quotes/random":
                    return a.quotes.random(channel=a.config.bot.room, limit=1)

                if path == "/quotes/count":
                    return {"count": a.quotes.count(channel=a.config.bot.room)}

                # ---- 每日总结 ----
                if path == "/digest/today":
                    content = a.digest.get_today(a.config.bot.room)
                    return {"content": content} if content else {"content": None}

                if path == "/digest/by_date":
                    date = qs.get("date", [""])[0]
                    if not date:
                        return {"error": "Missing param: date"}
                    content = a.digest.get_by_date(date, a.config.bot.room)
                    return {"content": content} if content else {"content": None}

                # ---- 系统信息 ----
                if path == "/sys":
                    import platform
                    try:
                        import psutil
                        mem = psutil.virtual_memory()
                        cpu = psutil.cpu_percent(interval=0.5)
                        sysinfo = {
                            "memory_used_mb": round(mem.used / 1048576, 1),
                            "memory_total_mb": round(mem.total / 1048576, 1),
                            "memory_percent": mem.percent,
                            "cpu_percent": cpu,
                        }
                    except ImportError:
                        sysinfo = {"error": "psutil not installed"}
                    return {
                        "platform": platform.platform(),
                        "python": platform.python_version(),
                        "db_path": a.config.db_path,
                        **sysinfo,
                    }

                # ---- 404 ----
                return {"error": "Not Found", "path": path}

        return Handler
