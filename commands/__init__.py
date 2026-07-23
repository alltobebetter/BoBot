"""构建路由：注册中间件与所有命令。"""
from __future__ import annotations

from config import config
from core.router import Router

from commands import admin, ai, game, help as help_cmd, misc, user
from commands.registry import build_middleware


def build_router(app) -> Router:
    router = Router(prefix=config.bot.prefix)
    for mw in build_middleware(app):
        router.use(mw)
    user.register(router)
    game.register(router)
    misc.register(router)
    admin.register(router)
    ai.register(router)  # 同时设置 fallback
    help_cmd.register(router)
    return router
