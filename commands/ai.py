"""AI 对话命令 + 非命令消息回退处理。

流程：
1. 用户发消息 → 先发"思考中..."（带 customId）
2. 后台线程调用 AI
3. AI 完成后用 updateMessage 更新那条消息为最终回复
"""
from __future__ import annotations

import random
import re
import threading

from utils.logger import log

_IMG_RE = re.compile(r"!\[[^\]]*\]\((https?://[^)]+)\)")

THINKING_MESSAGES = [
    "正在思考...",
    "让我想想...",
    "思考中...",
    "容我三思...",
    "正在查阅...",
    "处理中...",
    "稍等，我查一下...",
    "我想想...",
]


def _extract_images(text):
    return _IMG_RE.findall(text or "")


def _do_ai(ctx, prompt):
    """发起 AI 对话：先发思考消息，后台处理，完成后更新消息。"""
    if not ctx.app.rate_ai.allow(ctx.user_key):
        ctx.reply("[WARN] AI 请求太频繁，请稍后再试")
        return

    images = _extract_images(ctx.text)

    # 生成 customId（纯数字，兼容服务器）
    custom_id = str(random.randint(100000, 999999))
    thinking = f"@{ctx.nick} {random.choice(THINKING_MESSAGES)}"

    # 先发送"正在思考"（带 customId）
    if ctx.is_whisper:
        ctx.bot.whisper_with_id(ctx.nick, thinking, custom_id)
    else:
        ctx.bot.say_with_id(thinking, custom_id)

    # 后台线程处理 AI 请求
    def _worker():
        try:
            result = ctx.app.ai.chat(ctx.nick, ctx.trip, prompt, images)
            reply = result.message or "(无内容)"
            # 更新消息为最终回复
            ctx.bot.update_message(custom_id, reply)
        except Exception as e:
            log.error("AI 后台处理失败", exc=e)
            ctx.bot.update_message(custom_id, f"@{ctx.nick} [ERR] AI 暂时不可用，请稍后再试")

    threading.Thread(target=_worker, daemon=True).start()


def register(router):
    @router.command("ai", "chat", help="和 AI 对话 ai <内容>", category="AI")
    def ai(ctx):
        if not ctx.args:
            ctx.reply("用法：ai <你的问题>")
            return
        _do_ai(ctx, ctx.arg_str)

    @router.command("clearai", help="清空 AI 对话历史", category="AI")
    def clearai(ctx):
        ctx.app.ai.clear_history(ctx.user_key)
        ctx.reply("[OK] 已清空对话历史")

    @router.fallback
    def fallback(ctx):
        if not ctx.text or not ctx.app.ai.enabled:
            return
        base_name = ctx.bot.config.bot.name
        current_nick = getattr(ctx.bot, "nick", base_name)
        text_lower = ctx.text.lower()
        mentioned = base_name.lower() in text_lower or current_nick.lower() in text_lower
        if ctx.is_whisper or mentioned:
            prompt = ctx.text
            for n in (current_nick, base_name):
                prompt = prompt.replace(f"@{n}", "")
            prompt = prompt.strip()
            if prompt:
                _do_ai(ctx, prompt)
