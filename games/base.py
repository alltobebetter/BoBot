"""游戏基类。

设计原则：游戏为纯逻辑，不直接操作金币。
需要扣费/发奖时，通过 Result.data 告知命令层，由命令层统一处理金币。
"""
from __future__ import annotations

import time


class BaseGame:
    name = "game"
    timeout = 0  # 秒；0 表示不超时

    def __init__(self):
        self.active = False
        self.started_at = 0.0

    def _start_clock(self) -> None:
        self.active = True
        self.started_at = time.time()

    def expired(self) -> bool:
        return self.active and self.timeout > 0 and (time.time() - self.started_at) > self.timeout

    def reset(self) -> None:
        self.active = False
        self.started_at = 0.0
