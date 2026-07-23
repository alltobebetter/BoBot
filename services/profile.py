"""用户画像：AI 驱动的自然画像。

不做刻意追踪（不记录关键词/情感/时段），而是当用户查询时，
从聊天历史取最近消息，让 AI 生成一段自然的性格侧写。
"""
from __future__ import annotations

from core.result import Result
from utils.logger import log


class ProfileService:
    """AI 驱动的用户画像。"""

    SYSTEM_PROMPT = "你是一个聊天室观察者。根据用户的聊天记录，写一段简短有趣的性格侧写。不要使用 emoji，不要用波浪号，语气平实。"

    PROMPT = """根据以下用户「{nick}」的最近聊天记录，写一段简短有趣的性格侧写。
要求：
- 2-3 句话，口语化、有画面感
- 可以提到兴趣、说话风格、性格特点
- 不要罗列数据，像朋友间的评价
- 如果消息太少，就说"还不太了解这个人"
- 不要使用 emoji，不要用波浪号 ~，语气平实

聊天记录：
{messages}
"""

    def __init__(self, app):
        self.app = app

    def get_profile(self, nick: str) -> Result:
        """生成用户画像。"""
        # 从聊天历史取最近 50 条消息
        messages = self.app.history.user_messages(nick, limit=50)
        if not messages or len(messages) < 3:
            return Result.ok(f"[INFO] {nick} 还是个神秘人，消息太少，暂无法画像")

        # 拼接消息文本
        lines = [f"[{m['ts'][:16]}] {m['text']}" for m in messages]
        msg_text = "\n".join(lines[-30:])  # 最近 30 条，避免太长

        prompt = self.PROMPT.format(nick=nick, messages=msg_text)

        # 用 AI 生成画像（单次调用，不存历史）
        if not self.app.ai.enabled:
            return Result.fail("AI 未启用，无法生成画像")

        try:
            result = self.app.ai.chat_oneshot(
                system_prompt=self.SYSTEM_PROMPT,
                prompt=prompt,
                max_tokens=512,
            )
            if result:
                return Result.ok(f"[INFO] {nick} 的画像\n\n{result.message}")
            return Result.fail("画像生成失败")
        except Exception as e:
            log.error("用户画像生成失败", exc=e, nick=nick)
            return Result.fail("画像生成出错")
