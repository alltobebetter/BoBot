"""输入校验与清洗。"""
from __future__ import annotations

from typing import Optional


def clean_text(text: Optional[str], max_len: Optional[int] = None) -> str:
    if not text:
        return ""
    text = text.replace("\x00", "").strip()
    if max_len and len(text) > max_len:
        text = text[:max_len]
    return text


def parse_positive_int(value: str) -> Optional[int]:
    """解析正整数，失败返回 None。"""
    try:
        n = int(str(value).strip())
    except (ValueError, TypeError):
        return None
    return n if n > 0 else None


def parse_int(value: str) -> Optional[int]:
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return None


def parse_float(value: str) -> Optional[float]:
    try:
        return float(str(value).strip())
    except (ValueError, TypeError):
        return None
