"""管理员命令。"""
from __future__ import annotations

import os

from utils.text import split_user_key
from utils.validate import parse_int


def register(router):
    @router.command("addcoins", help="（管理员）addcoins <昵称#trip> <数量>", category="管理")
    def addcoins(ctx):
        if not ctx.is_admin:
            ctx.reply("[ERR] 仅管理员可用")
            return
        if len(ctx.args) < 2:
            ctx.reply("用法：addcoins <昵称#trip> <数量>")
            return
        amount = parse_int(ctx.args[-1])
        target = " ".join(ctx.args[:-1])
        if amount is None:
            ctx.reply("数量无效")
            return
        nick, trip = split_user_key(target)
        ctx.app.coins.add(nick, trip, amount, reason="管理员发放")
        verb = "发放" if amount >= 0 else "扣除"
        ctx.reply(f"[OK] 已给 {target} {verb} {abs(amount)} 金币")

    @router.command("resetgame", help="（管理员）重置所有游戏", category="管理")
    def resetgame(ctx):
        if not ctx.is_admin:
            ctx.reply("[ERR] 仅管理员可用")
            return
        g = ctx.app.games
        for game in (g.wordle, g.idiom, g.dice, g.guess, g.number, g.zhajinhua, g.uno):
            game.reset()
        ctx.reply("[OK] 已重置所有游戏")

    @router.command("say", help="（管理员）让机器人发言 say <内容>", category="管理")
    def say(ctx):
        if not ctx.is_admin:
            ctx.reply("[ERR] 仅管理员可用")
            return
        if ctx.arg_str:
            ctx.bot.say(ctx.arg_str)

    @router.command("serverstats", "sstats", help="（管理员）服务器统计", category="管理")
    def serverstats(ctx):
        if not ctx.is_admin:
            ctx.reply("[ERR] 仅管理员可用")
            return
        ctx.reply("[INFO] 正在请求服务器统计...")
        ctx.bot.conn.request_stats()

        import threading
        import time

        def _worker():
            time.sleep(2)
            stats = ctx.bot._last_server_stats
            if stats:
                ctx.reply(
                    f"[INFO] 服务器统计\n"
                    f"连接数：{stats.get('users', '?')}\n"
                    f"频道数：{stats.get('channels', '?')}\n"
                    f"总加入：{stats.get('joins', '?')}\n"
                    f"总消息：{stats.get('messages', '?')}\n"
                    f"运行时间：{stats.get('uptime', '?')}"
                )
            else:
                ctx.reply("[ERR] 未收到服务器统计响应")

        threading.Thread(target=_worker, daemon=True).start()

    @router.command("changenick", "nick", help="（管理员）更改机器人昵称 changenick <新昵称>", category="管理")
    def changenick(ctx):
        if not ctx.is_admin:
            ctx.reply("[ERR] 仅管理员可用")
            return
        if not ctx.args:
            ctx.reply(f"当前昵称：{ctx.bot.nick}\n用法：changenick <新昵称>")
            return
        new_nick = ctx.args[0]
        # 验证昵称格式：1-24 位字母数字下划线
        import re
        if not re.match(r'^[a-zA-Z0-9_]{1,24}$', new_nick):
            ctx.reply("昵称只能包含字母、数字、下划线，1-24 位")
            return
        old_nick = ctx.bot.nick
        ctx.bot.conn.change_nick(new_nick)
        ctx.bot.nick = new_nick
        ctx.reply(f"[OK] 昵称已更改：{old_nick} → {new_nick}")

    @router.command("admin", help="（管理员）系统管理 admin <health|perf|clearai|cleanhist>", category="管理")
    def admin(ctx):
        if not ctx.is_admin:
            ctx.reply("[ERR] 仅管理员可用")
            return
        if not ctx.args:
            ctx.reply(
                "管理员命令：\n"
                "• admin health - 系统健康检查\n"
                "• admin perf - 性能监控\n"
                "• admin clearai - 清除所有人 AI 聊天记录\n"
                "• admin cleanhist [天数] - 清理旧聊天记录\n"
                "• serverstats - 服务器统计\n"
                "• changenick <昵称> - 更改机器人昵称"
            )
            return
        sub = ctx.args[0].lower()
        if sub == "health":
            _health(ctx)
        elif sub == "perf":
            _perf(ctx)
        elif sub == "clearai":
            _clearai(ctx)
        elif sub == "cleanhist":
            _cleanhist(ctx)
        else:
            ctx.reply("未知子命令")


def _health(ctx):
    """系统健康检查。"""
    try:
        # 数据库
        db_ok = True
        try:
            ctx.app.db.execute("SELECT 1")
        except Exception:
            db_ok = False

        # 在线用户
        online = len(ctx.bot.online_users)

        # 今日消息数
        today_msgs = ctx.app.history.count_today(ctx.bot.config.bot.room)

        # AI 状态
        ai_providers = [p.name for p in ctx.app.ai.providers] if ctx.app.ai.enabled else []

        max_ai = ctx.app.ai.max_concurrency
        active_ai = max_ai - ctx.app.ai.concurrency_available
        ctx.reply(
            f"[INFO] 系统健康检查\n"
            f"数据库：{'OK' if db_ok else 'ERR'}\n"
            f"在线用户：{online}\n"
            f"今日消息：{today_msgs}\n"
            f"AI Providers：{', '.join(ai_providers) or '未配置'}\n"
            f"AI 活跃：{active_ai}/{max_ai}"
        )
    except Exception as e:
        ctx.reply(f"健康检查失败：{e}")


def _perf(ctx):
    """性能监控。"""
    try:
        import psutil
        process = psutil.Process(os.getpid())
        cpu = process.cpu_percent(interval=0.1)
        mem_mb = process.memory_info().rss / 1024 / 1024
        threads = process.num_threads()

        max_ai = ctx.app.ai.max_concurrency
        active_ai = max_ai - ctx.app.ai.concurrency_available
        ctx.reply(
            f"[INFO] 性能监控\n"
            f"CPU：{cpu:.1f}%\n"
            f"内存：{mem_mb:.1f} / 256 MB\n"
            f"线程数：{threads}\n"
            f"AI 活跃：{active_ai}/{max_ai}"
        )
    except ImportError:
        ctx.reply("需要安装 psutil：pip install psutil")
    except Exception as e:
        ctx.reply(f"性能监控失败：{e}")


def _clearai(ctx):
    """清除所有人的 AI 聊天记录。"""
    try:
        rows = ctx.app.db.query("SELECT key FROM kv WHERE namespace='ai_history'")
        for r in rows:
            ctx.app.kv.delete("ai_history", r["key"])
        ctx.reply(f"[OK] 已清除 {len(rows)} 个用户的 AI 聊天记录")
    except Exception as e:
        ctx.reply(f"[ERR] 清除失败：{e}")


def _cleanhist(ctx):
    """清理旧聊天记录。"""
    days = 90
    if len(ctx.args) > 1:
        try:
            days = int(ctx.args[1])
        except ValueError:
            pass
    try:
        deleted = ctx.app.history.cleanup_old(days)
        ctx.reply(f"[OK] 已清理 {deleted} 条 {days} 天前的聊天记录")
    except Exception as e:
        ctx.reply(f"[ERR] 清理失败：{e}")
