"""命令路由：注册、别名、中间件、回退处理、统一错误处理。"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional

from utils.logger import log

Handler = Callable[["Context"], None]
Middleware = Callable[["Context"], Optional[bool]]


class Router:
    def __init__(self, prefix: str = ""):
        self.prefix = prefix
        self._commands: Dict[str, Handler] = {}
        self._aliases: Dict[str, str] = {}
        self._help: Dict[str, str] = {}
        self._categories: Dict[str, str] = {}
        self._middleware: List[Middleware] = []
        self._fallback: Optional[Handler] = None

    def command(self, name: str, *aliases: str, help: str = "", category: str = "其他"):
        def deco(fn: Handler) -> Handler:
            self._commands[name] = fn
            self._help[name] = help
            self._categories[name] = category
            for a in aliases:
                self._aliases[a] = name
            return fn

        return deco

    def use(self, mw: Middleware) -> Middleware:
        self._middleware.append(mw)
        return mw

    def fallback(self, fn: Handler) -> Handler:
        self._fallback = fn
        return fn

    def resolve(self, name: str) -> Optional[Handler]:
        name = self._aliases.get(name, name)
        return self._commands.get(name)

    def help_entries(self) -> Dict[str, Dict[str, str]]:
        return {
            name: {"help": self._help.get(name, ""), "category": self._categories.get(name, "其他")}
            for name in self._commands
        }

    def dispatch(self, ctx) -> None:
        for mw in self._middleware:
            try:
                if mw(ctx) is False:
                    return
            except Exception as e:
                log.error("中间件异常", exc=e)
        handler: Optional[Handler] = None
        if ctx.command:
            handler = self.resolve(ctx.command)
        if handler is None:
            handler = self._fallback
        if handler is None:
            return
        # 命令限流：只对真正匹配的命令生效，不对 fallback（AI闲聊）生效
        if handler is not self._fallback:
            if not ctx.app.rate_global.allow(ctx.user_key):
                return
        try:
            handler(ctx)
        except Exception as e:
            log.error("命令处理异常", exc=e, command=ctx.command)
            ctx.reply("[ERR] 出错了，请稍后再试")
