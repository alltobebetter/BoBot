"""文本 / 时间 / 排行 等通用助手。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional

from constants import RANK_EMOJI

CST = timezone(timedelta(hours=8))


def user_key(nick: str, trip: Optional[str]) -> str:
    """统一的用户标识：nick#trip（无 trip 时仅 nick）。"""
    trip = (trip or "").strip()
    return f"{nick}#{trip}" if trip else nick


def split_user_key(key: str):
    if "#" in key:
        nick, trip = key.split("#", 1)
        return nick, trip
    return key, ""


def now() -> datetime:
    return datetime.now(CST)


def today_str() -> str:
    return now().strftime("%Y-%m-%d")


def yesterday_str() -> str:
    return (now() - timedelta(days=1)).strftime("%Y-%m-%d")


def render_ranking(
    title: str,
    entries: Iterable[Any],
    line_fmt: Callable[[Any], str],
    empty: str = "暂无数据",
) -> str:
    """统一的排行榜渲染（前三名奖牌，其余数字序号）。"""
    entries = list(entries)
    if not entries:
        return f"{title}\n{empty}"
    lines = [title]
    for i, e in enumerate(entries):
        medal = RANK_EMOJI[i] if i < len(RANK_EMOJI) else f"{i + 1}."
        lines.append(f"{medal} {line_fmt(e)}")
    return "\n".join(lines)


_DICE_FACES = {1: "⚀", 2: "⚁", 3: "⚂", 4: "⚃", 5: "⚄", 6: "⚅"}


def dice_emoji(n: int) -> str:
    return _DICE_FACES.get(n, str(n))


def truncate(text: str, limit: int, suffix: str = "…") -> str:
    if text is None:
        return ""
    return text if len(text) <= limit else text[: limit - len(suffix)] + suffix
