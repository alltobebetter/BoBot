"""命令层共享设施：中间件、金币收支助手。

重要：所有游戏的金币收支都在这里统一处理（游戏接受后才扣/发）。
"""
from __future__ import annotations

from utils.logger import log


# ---- 金币收支助手（游戏与命令共用）----
def need_balance(ctx, amount: int) -> bool:
    if ctx.app.coins.balance(ctx.nick, ctx.trip) < amount:
        ctx.reply(f"金币不足（需要 {amount}）")
        return False
    return True


def charge_after(ctx, result, reason: str) -> None:
    """游戏接受后才扣费，避免“扣了钱却没成”。"""
    if result and result.data and "charge" in result.data:
        ctx.app.coins.spend(ctx.nick, ctx.trip, result.data["charge"], reason=reason)


def payout(ctx, result, reason: str, game_name: str = "") -> None:
    if not result or not result.data:
        return
    for p in result.data.get("payouts", []):
        ctx.app.coins.add(p["nick"], p["trip"], p["amount"], reason=reason)
        if game_name:
            try:
                ctx.app.stats.record_game(p["nick"], p["trip"], game_name, True)
            except Exception:
                pass
    p = result.data.get("payout")
    if p:
        ctx.app.coins.add(p["nick"], p["trip"], p["amount"], reason=reason)
        if game_name:
            try:
                ctx.app.stats.record_game(p["nick"], p["trip"], game_name, True)
            except Exception:
                pass


def handle_win(ctx, result, reward: int, reason: str, game_name: str = "") -> None:
    """单人游戏胜利：给当前玩家发奖并回复，同时记录游戏统计。"""
    msg = result.message
    won = bool(result and result.data and result.data.get("win"))
    if won and reward:
        ctx.app.coins.add(ctx.nick, ctx.trip, reward, reason=reason)
        msg += f"\n[OK] +{reward} 金币"
    # 记录游戏统计（胜/负）
    if game_name:
        try:
            ctx.app.stats.record_game(ctx.nick, ctx.trip, game_name, won)
        except Exception:
            pass
    ctx.reply(msg)


def build_middleware(app):
    def pre(ctx):
        # 1) 聊天统计（非私聊）
        if not ctx.is_whisper:
            try:
                app.stats.record(ctx.nick, ctx.trip, ctx.text)
            except Exception as e:
                log.error("统计记录失败", exc=e)
        # 2) AFK 回归
        key = ctx.user_key
        if app.afk.is_afk(key) and not (ctx.command == "afk"):
            app.afk.clear(key)
            ctx.bot.say(f"[INFO] {ctx.nick} 回来了")
        # 3) 命令限流
        if ctx.command and not app.rate_global.allow(key):
            ctx.reply("[WARN] 操作太快，请稍后再试")
            return False
        return True

    return [pre]

