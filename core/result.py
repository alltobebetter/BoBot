"""全局统一的返回类型。

所有 service 与 game 的方法都返回 Result，彻底取代旧项目中
重复定义的 GameResult / 元组 / dict 混用。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class Result:
    success: bool
    message: str = ""
    data: Any = None
    error: Optional[str] = None

    def __bool__(self) -> bool:
        return self.success

    @classmethod
    def ok(cls, message: str = "", data: Any = None) -> "Result":
        return cls(True, message, data)

    @classmethod
    def fail(cls, message: str = "", error: Optional[str] = None) -> "Result":
        return cls(False, message, None, error or message)
