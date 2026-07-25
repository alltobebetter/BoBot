"""AIBoB 入口。

HackChat 多功能机器人：经济、游戏、AI 对话。
统一后端存储（SQLite）、统一命令路由、统一 Result 返回。

部署到服务器时，可同时启动内嵌 HTTP API Server（端口 8300），
供 Vercel 前端代理调用，实现数据实时展示而不暴露后端地址。
"""
from __future__ import annotations

from commands import build_router
from core.bot import Bot
from services.api_server import ApiServer
from services.app import App
from utils.logger import log


def main() -> None:
    app = App()
    router = build_router(app)
    bot = Bot(router, app)
    log.info("AIBoB 启动中...")

    # 每日总结定时器
    app.digest.start_scheduler(bot)

    # 内嵌 HTTP API Server
    api_server = None
    if app.config.api_server.enabled:
        api_server = ApiServer(
            app=app,
            host=app.config.api_server.host,
            port=app.config.api_server.port,
            api_key=app.config.api_server.api_key,
        )
        api_server.start()

    try:
        bot.run()
    except KeyboardInterrupt:
        log.info("收到退出信号，正在关闭...")
    finally:
        app.digest.stop_scheduler()
        if api_server:
            api_server.stop()
        bot.stop()
        app.close()


if __name__ == "__main__":
    main()
