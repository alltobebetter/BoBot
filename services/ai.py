"""统一的 AI 服务：聊天 + function-calling 工具（合并了旧项目的 chat / tool_calling）。

- 多 Provider fallback（Kilo 主力 + NVIDIA 保底）
- 对话历史存于 SQLite 的 kv 表（namespace='ai_history'），不再写 JSON 文件
- 工具统一通过 App 容器访问各 service，避免循环引用
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, List, Optional

from config import Provider, config
from constants import AI_MAX_HISTORY, AI_MAX_TOOL_ROUNDS, MAX_AI_INPUT, MAX_AI_RESPONSE
from core.result import Result
from utils.logger import log
from utils.text import truncate, user_key

_NS_HISTORY = "ai_history"

SYSTEM_PROMPT = (
    "你是 HackChat 聊天室里的智能助手 BoB，回复简洁友好，使用中文。"
    "你可以调用工具查询金币、排行榜、统计、运势、网络搜索等。"
    "回复不要过长。不要使用 emoji 装饰回复，不要用波浪号 ~，语气平实。"
)


class AIService:
    def __init__(self, app):
        self.app = app
        self.enabled = config.api.ai_enabled
        self._providers: List[Provider] = config.api.providers
        self._client_cache: Dict[str, Any] = {}  # key: provider.name
        self.tools = build_tool_specs()
        # 动态并发控制：后台监测内存，紧张时自动降级，空闲时恢复
        self._hard_limit = config.api.ai_concurrency
        self._effective_limit = self._hard_limit
        self._active = 0
        self._lock = threading.Lock()
        threading.Thread(target=self._resource_monitor, daemon=True).start()

    # ---- 历史 ----
    def _load_history(self, key: str) -> List[Dict]:
        return self.app.kv.get(_NS_HISTORY, key, []) or []

    def _save_history(self, key: str, history: List[Dict]) -> None:
        self.app.kv.set(_NS_HISTORY, key, history[-AI_MAX_HISTORY:])

    def clear_history(self, key: str) -> None:
        self.app.kv.delete(_NS_HISTORY, key)

    # ---- 客户端（公共，供 CodeAgent 复用）----
    def get_client(self, provider: Provider):
        """获取指定 provider 的 OpenAI client（带缓存）。"""
        if provider.name in self._client_cache:
            return self._client_cache[provider.name]
        try:
            from openai import OpenAI
        except Exception as e:
            log.error("openai 库未安装", exc=e)
            return None
        client = OpenAI(api_key=provider.api_key, base_url=provider.base_url)
        self._client_cache[provider.name] = client
        return client

    @property
    def providers(self) -> List[Provider]:
        return self._providers

    @property
    def concurrency_available(self) -> int:
        """当前可用的 AI 并发槽位数。"""
        with self._lock:
            return max(0, self._effective_limit - self._active)

    @property
    def max_concurrency(self) -> int:
        """当前生效的并发上限（可能因资源紧张而低于配置值）。"""
        return self._effective_limit

    def _resource_monitor(self):
        """后台监测内存使用率，每 30 秒动态调整并发上限。

        256MB 机器的阈值：
        - 内存 > 85%：降到 1（保命，防止 OOM）
        - 内存 > 70%：降到 2（降负荷）
        - 内存 <= 70%：恢复配置值（正常）
        psutil 不可用时保持配置值不变。
        """
        while True:
            try:
                import psutil
                mem = psutil.virtual_memory()
                old = self._effective_limit
                if mem.percent > 85:
                    self._effective_limit = 1
                elif mem.percent > 70:
                    self._effective_limit = min(2, self._hard_limit)
                else:
                    self._effective_limit = self._hard_limit
                if old != self._effective_limit:
                    log.info("AI 并发调整", old=old, new=self._effective_limit,
                             mem_percent=round(mem.percent, 1))
            except Exception:
                pass
            time.sleep(30)

    def _acquire(self, timeout: float = 30.0) -> bool:
        """获取并发槽位，超时返回 False。"""
        deadline = time.time() + timeout
        while True:
            with self._lock:
                if self._active < self._effective_limit:
                    self._active += 1
                    return True
            if time.time() >= deadline:
                return False
            time.sleep(0.5)

    def _release(self):
        with self._lock:
            self._active = max(0, self._active - 1)

    def web_search(self, query: str) -> Any:
        """网络搜索（公共，供 CodeAgent 复用）。"""
        return self._web_search(query)

    def concurrency_slot(self):
        """并发槽位上下文管理器，供 CodeAgent 等复用（阻塞等待）。"""
        svc = self
        class _Slot:
            def __enter__(self):
                svc._acquire(timeout=999999)
                return self
            def __exit__(self, *args):
                svc._release()
        return _Slot()

    def request_with_tools(self, client, provider: Provider, messages: List[Dict],
                           tools: List[Dict], temperature: float = 0.7,
                           max_tokens: int = 4096):
        """发送带 tools 的请求，处理 Kilo 假 502。供 CodeAgent 复用。"""
        resp = client.chat.completions.create(
            model=provider.model, messages=messages,
            tools=tools, temperature=temperature,
            top_p=0.95, max_tokens=max_tokens,
        )
        if not resp.choices:
            error_info = getattr(resp, "error", None) or {}
            error_msg = error_info.get("message", "unknown") if isinstance(error_info, dict) else str(error_info)
            raise Exception(f"Provider {provider.name} 返回错误: {error_msg}")
        return resp

    # ---- reasoning 模型兼容 ----
    @staticmethod
    def _extract_content(msg) -> str:
        """从 message 中提取回复内容，兼容 reasoning 模型。

        GLM-5.2 / DeepSeek-R1 等 reasoning 模型可能将思考过程放在
        reasoning_content 字段，而 content 才是最终回复。
        如果 content 为空则尝试 reasoning_content 作为 fallback。
        """
        content = getattr(msg, "content", None) or ""
        if content:
            return content
        # fallback: reasoning_content（某些模型/平台可能把回复放这里）
        extra = getattr(msg, "model_extra", None) or {}
        reasoning = extra.get("reasoning_content", "")
        if reasoning:
            log.warning("content 为空，使用 reasoning_content 作为 fallback")
            return reasoning
        return ""

    # ---- 主入口 ----
    def chat(self, nick: str, trip: str, prompt: str, image_urls: Optional[List[str]] = None) -> Result:
        if not self.enabled or not self._providers:
            return Result.fail("AI 功能未配置（缺少 AI_PROVIDERS）")
        prompt = truncate((prompt or "").strip(), MAX_AI_INPUT)
        if not prompt and not image_urls:
            return Result.fail("请输入内容")
        key = user_key(nick, trip)
        history = self._load_history(key)
        user_content: Any = prompt
        if image_urls:
            user_content = [{"type": "text", "text": prompt or "请描述这张图片"}]
            for url in image_urls:
                user_content.append({"type": "image_url", "image_url": {"url": url}})
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_content})
        ctx = {"nick": nick, "trip": trip}
        try:
            if not self._acquire():
                return Result.fail("系统繁忙，请稍后再试")
            try:
                reply = self._run_with_fallback(messages, ctx)
            finally:
                self._release()
        except Exception as e:
            log.error("AI 调用失败", exc=e)
            return Result.fail("AI 暂时不可用，请稍后再试")
        reply = truncate(reply or "", MAX_AI_RESPONSE)
        history.append({"role": "user", "content": prompt})
        history.append({"role": "assistant", "content": reply})
        self._save_history(key, history)
        return Result.ok(reply)

    def chat_oneshot(self, system_prompt: str, prompt: str,
                     max_tokens: int = 1024) -> Result:
        """单次 AI 调用（不存历史，用于画像等内部任务）。"""
        if not self.enabled or not self._providers:
            return Result.fail("AI 功能未配置")
        prompt = truncate((prompt or "").strip(), MAX_AI_INPUT)
        if not prompt:
            return Result.fail("请输入内容")
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        try:
            if not self._acquire():
                return Result.fail("系统繁忙，请稍后再试")
            try:
                reply = self._run_with_fallback(messages, {"nick": "", "trip": ""})
            finally:
                self._release()
        except Exception as e:
            log.error("AI oneshot 调用失败", exc=e)
            return Result.fail("AI 暂时不可用，请稍后再试")
        return Result.ok(truncate(reply or "", max_tokens))

    def _run_with_fallback(self, messages: List[Dict], ctx: Dict) -> str:
        """遍历 providers，第一个成功就返回；全失败则抛最后一个异常。"""
        last_error: Optional[Exception] = None
        for provider in self._providers:
            client = self.get_client(provider)
            if client is None:
                continue
            try:
                return self._run_loop(client, provider, messages, ctx)
            except Exception as e:
                log.warning(
                    "AI provider 请求失败，尝试下一个",
                    provider=provider.name,
                    error=str(e),
                )
                last_error = e
        raise last_error or Exception("无可用 AI provider")

    def _run_loop(self, client, provider: Provider, messages: List[Dict], ctx: Dict) -> str:
        """用指定 provider 执行 tool-call 循环。"""
        for _ in range(AI_MAX_TOOL_ROUNDS):
            resp = self.request_with_tools(
                client, provider, messages, self.tools,
            )

            msg = resp.choices[0].message
            tool_calls = getattr(msg, "tool_calls", None)
            if not tool_calls:
                return self._extract_content(msg)
            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in tool_calls
                    ],
                }
            )
            for tc in tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except Exception:
                    args = {}
                result = self._dispatch_tool(tc.function.name, args, ctx)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
        return "（处理轮次过多，已中断）"

    # ---- 工具调度 ----
    def _dispatch_tool(self, name: str, args: Dict, ctx: Dict) -> Any:
        app = self.app
        nick, trip = ctx["nick"], ctx["trip"]
        try:
            if name == "get_user_coins":
                target = args.get("user") or nick
                row = app.users.get(target) or app.users.get(user_key(target, ""))
                return {"user": target, "coins": row["coins"] if row else 0}
            if name == "get_coin_rankings":
                rows = app.coins.rankings(args.get("limit", 10))
                return [{"nick": r["nick"], "coins": r["coins"]} for r in rows]
            if name == "get_user_stats":
                row = app.stats.get(user_key(nick, trip))
                return row or {"messages": 0}
            if name == "get_top_chatters":
                return app.stats.top_chatters(args.get("limit", 10))
            if name == "get_inventory":
                return app.inventory.get_all(user_key(nick, trip))
            if name == "get_shop_items":
                return app.shop.catalog()
            if name == "get_today_checkins":
                return app.checkin.today_list()
            if name == "get_fortune":
                r = app.fortune.daily(nick, trip)
                return {"text": r.message}
            if name == "get_user_rank":
                return {"rank": app.coins.rank_of(user_key(nick, trip))}
            if name == "set_afk":
                r = app.afk.set(user_key(nick, trip), nick, args.get("reason", ""))
                return {"text": r.message}
            if name == "web_search":
                return self._web_search(args.get("query", ""))
            if name == "crypto_price":
                return app.games.crypto.price_info(args.get("symbol", ""))
            if name == "admin_add_coins":
                if not config.bot.is_admin(nick, trip):
                    return {"error": "权限不足"}
                target = args.get("user", "")
                amount = int(args.get("amount", 0))
                t_nick, t_trip = (target.split("#", 1) + [""])[:2]
                app.coins.add(t_nick, t_trip, amount, reason="管理员发放")
                return {"ok": True}
        except Exception as e:
            log.error("工具执行失败", exc=e, tool=name)
            return {"error": str(e)}
        return {"error": f"unknown tool {name}"}

    def _web_search(self, query: str) -> Any:
        keys = config.api.tavily_keys
        if not keys or not query:
            return {"error": "web search 不可用"}
        try:
            import requests

            resp = requests.post(
                "https://api.tavily.com/search",
                json={"api_key": keys[0], "query": query, "max_results": 5},
                timeout=15,
            )
            data = resp.json()
            return [
                {"title": r.get("title"), "content": truncate(r.get("content", ""), 300)}
                for r in data.get("results", [])
            ]
        except Exception as e:
            return {"error": str(e)}


def build_tool_specs() -> List[Dict]:
    def spec(name, desc, props=None, required=None):
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": desc,
                "parameters": {
                    "type": "object",
                    "properties": props or {},
                    "required": required or [],
                },
            },
        }

    num = {"type": "integer"}
    txt = {"type": "string"}
    return [
        spec("get_user_coins", "查询用户金币余额", {"user": txt}),
        spec("get_coin_rankings", "金币排行榜", {"limit": num}),
        spec("get_user_stats", "当前用户聊天统计"),
        spec("get_top_chatters", "聊天活跃排行榜", {"limit": num}),
        spec("get_inventory", "当前用户背包"),
        spec("get_shop_items", "商店商品列表"),
        spec("get_today_checkins", "今日签到列表"),
        spec("get_fortune", "当前用户今日运势"),
        spec("get_user_rank", "当前用户金币排名"),
        spec("set_afk", "设置当前用户 AFK", {"reason": txt}),
        spec("web_search", "网络搜索", {"query": txt}, ["query"]),
        spec("crypto_price", "查询加密货币价格", {"symbol": txt}, ["symbol"]),
        spec("admin_add_coins", "（管理员）给用户发金币", {"user": txt, "amount": num}, ["user", "amount"]),
    ]
