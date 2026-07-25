"""游戏命令。所有金币收支在这里统一处理（游戏为纯逻辑）。"""
from __future__ import annotations

from commands.registry import (
    charge_after,
    handle_win,
    need_balance,
    payout,
)
from config import config
from utils.gyazo import upload_to_gyazo
from utils.logger import log
from utils.validate import parse_float, parse_int, parse_positive_int


def _send_wordle_image(ctx, g) -> bool:
    """尝试生成 Wordle 棋盘图片并上传 Gyazo，成功返回 True。

    图片优先：配了 Gyazo 就发图片，没配或失败时调用方自行降级为文本棋盘。
    """
    if not config.api.gyazo_enabled:
        return False
    try:
        image_data = g.generate_image()
        if not image_data:
            return False
        url = upload_to_gyazo(image_data)
        if url:
            ctx.reply(f"![]({url})")
            return True
    except Exception as e:
        log.error("Wordle 图片上传失败", exc=e)
    return False


def _strip_emoji_board(msg: str) -> str:
    """从消息中去掉以 Wordle 方块 emoji 开头的棋盘行，只留结果行。"""
    lines = msg.split("\n")
    kept = [
        ln for ln in lines
        if not (ln.startswith("🟩") or ln.startswith("🟨") or ln.startswith("⬜"))
    ]
    return "\n".join(kept) if kept else msg


def register(router):
    R = config.rewards

    # ---------- Wordle ----------
    @router.command("wordle", help="开始 Wordle（w 猜词）", category="游戏")
    def wordle(ctx):
        g = ctx.app.games.wordle
        if ctx.args:
            sub = ctx.args[0].lower()
            if sub == "hint":
                ctx.reply(g.hint().message)
                return
            if sub == "status":
                result = g.status()
                if not result:
                    ctx.reply(result.message)
                    return
                # 图片优先：发图成功则不发文本棋盘，失败降级为 emoji 棋盘
                if not _send_wordle_image(ctx, g):
                    ctx.reply(result.message)
                return
        ctx.reply(g.start().message)

    @router.command("w", help="Wordle 猜词 w <单词>", category="游戏")
    def w_guess(ctx):
        if not ctx.args:
            ctx.reply("用法：w <5字母单词>")
            return
        g = ctx.app.games.wordle
        result = g.guess(ctx.nick, ctx.args[0])
        if not result:
            ctx.reply(result.message)
            return

        # 尝试生成图片并上传 Gyazo（图片优先，失败则降级文本棋盘）
        msg = result.message
        if _send_wordle_image(ctx, g):
            # 图片已发送，只发结果行，避免棋盘重复刷屏
            msg = _strip_emoji_board(msg)

        # 发奖
        if result.data and result.data.get("win") and R.wordle_win:
            ctx.app.coins.add(ctx.nick, ctx.trip, R.wordle_win, reason="Wordle 胜利")
            msg += f"\n[OK] +{R.wordle_win} 金币"
        try:
            ctx.app.stats.record_game(ctx.nick, ctx.trip, "wordle", bool(result.data and result.data.get("win")))
        except Exception:
            pass
        ctx.reply(msg)

    # ---------- 猜数字 ----------
    @router.command("guess", help="猜数字 1-100（g 猜）", category="游戏")
    def guess_cmd(ctx):
        ctx.reply(ctx.app.games.guess.start().message)

    @router.command("g", help="g <数字>", category="游戏")
    def g_guess(ctx):
        n = parse_int(ctx.args[0]) if ctx.args else None
        if n is None:
            ctx.reply("用法：g <数字>")
            return
        handle_win(ctx, ctx.app.games.guess.guess(n), R.guess_win, "猜数字胜利", "guess")

    # ---------- 1A2B ----------
    @router.command("number", "1a2b", help="1A2B（n 猜）", category="游戏")
    def number_cmd(ctx):
        ctx.reply(ctx.app.games.number.start().message)

    @router.command("n", help="n <4位数字>", category="游戏")
    def n_guess(ctx):
        if not ctx.args:
            ctx.reply("用法：n <4位不重复数字>")
            return
        handle_win(ctx, ctx.app.games.number.guess(ctx.args[0]), R.number_win, "1A2B 胜利", "number")

    # ---------- 成语接龙 ----------
    @router.command("idiom", help="成语接龙（i 接龙）", category="游戏")
    def idiom_cmd(ctx):
        g = ctx.app.games.idiom
        if ctx.args:
            sub = ctx.args[0].lower()
            if sub == "stop":
                ctx.reply(g.stop().message)
                return
            if sub == "skip":
                if ctx.app.inventory.use(ctx.user_key, "skip_card"):
                    ctx.reply(g.skip().message)
                else:
                    ctx.reply("你没有成语跳过卡")
                return
        ctx.reply(g.start().message)

    @router.command("i", help="i <成语>", category="游戏")
    def i_submit(ctx):
        if not ctx.args:
            ctx.reply("用法：i <成语>")
            return
        reward = R.idiom_win[-1] if R.idiom_win else 30
        handle_win(ctx, ctx.app.games.idiom.submit(ctx.args[0]), reward, "成语接龙", "idiom")

    # ---------- 骰子 ----------
    @router.command("dice", help="骰子对赌 dice <注> | join <注> | roll", category="游戏")
    def dice(ctx):
        g = ctx.app.games.dice
        if not ctx.args:
            ctx.reply("用法：dice <注注> 开局，dice join <注注> 加入，dice roll 开骰")
            return
        sub = ctx.args[0].lower()
        if sub == "roll":
            r = g.roll()
            payout(ctx, r, "骰子胜利", "dice")
            ctx.reply(r.message)
            return
        if sub == "status":
            ctx.reply(g.status().message)
            return
        if sub == "join":
            bet = parse_positive_int(ctx.args[1]) if len(ctx.args) > 1 else None
            if bet is None:
                ctx.reply("用法：dice join <注注>")
                return
            if not need_balance(ctx, bet):
                return
            r = g.join(ctx.nick, ctx.trip, bet)
            charge_after(ctx, r, "骰子下注")
            ctx.reply(r.message)
            return
        bet = parse_positive_int(sub)
        if bet is None:
            ctx.reply("用法：dice <注注>")
            return
        if not need_balance(ctx, bet):
            return
        r = g.start(ctx.nick, ctx.trip, bet)
        charge_after(ctx, r, "骰子下注")
        ctx.reply(r.message)

    # ---------- 炸金花 ----------
    @router.command("zjh", help="炸金花 zjh start <底注>|join|deal|look|call|raise <n>|fold|open", category="游戏")
    def zjh(ctx):
        g = ctx.app.games.zhajinhua
        if not ctx.args:
            ctx.reply("用法：zjh start <底注> | join | deal | look | call | raise <n> | fold | open")
            return
        sub = ctx.args[0].lower()
        if sub == "start":
            ante = parse_positive_int(ctx.args[1]) if len(ctx.args) > 1 else None
            if ante is None:
                ctx.reply("用法：zjh start <底注>")
                return
            if not need_balance(ctx, ante):
                return
            r = g.start(ctx.nick, ctx.trip, ante)
            charge_after(ctx, r, "炸金花底注")
            ctx.reply(r.message)
            return
        if sub == "join":
            if not need_balance(ctx, g.current_bet):
                return
            r = g.join(ctx.nick, ctx.trip)
            charge_after(ctx, r, "炸金花底注")
            ctx.reply(r.message)
            return
        if sub == "deal":
            ctx.reply(g.deal().message)
            return
        if sub == "look":
            ctx.whisper(g.look(ctx.nick, ctx.trip).message)
            return
        if sub == "call":
            if not need_balance(ctx, g.current_bet):
                return
            r = g.call(ctx.nick, ctx.trip)
            charge_after(ctx, r, "炸金花跟注")
            ctx.reply(r.message)
            return
        if sub == "raise":
            amt = parse_positive_int(ctx.args[1]) if len(ctx.args) > 1 else None
            if amt is None:
                ctx.reply("用法：zjh raise <金额>")
                return
            if not need_balance(ctx, amt):
                return
            r = g.raise_bet(ctx.nick, ctx.trip, amt)
            charge_after(ctx, r, "炸金花加注")
            ctx.reply(r.message)
            return
        if sub == "fold":
            r = g.fold(ctx.nick, ctx.trip)
            payout(ctx, r, "炸金花胜利", "zhajinhua")
            ctx.reply(r.message)
            return
        if sub == "open":
            r = g.open()
            payout(ctx, r, "炸金花胜利", "zhajinhua")
            ctx.reply(r.message)
            return
        ctx.reply("未知子命令，zjh 查看用法")

    # ---------- UNO ----------
    @router.command("uno", help="UNO uno start|join|begin|hand|play <牌> [颜色]|draw|status", category="游戏")
    def uno(ctx):
        g = ctx.app.games.uno
        if not ctx.args:
            ctx.reply("用法：uno start|join|begin|hand|play <牌> [颜色]|draw|status")
            return
        sub = ctx.args[0].lower()
        if sub == "start":
            ctx.reply(g.start(ctx.nick, ctx.trip).message)
        elif sub == "join":
            ctx.reply(g.join(ctx.nick, ctx.trip).message)
        elif sub == "begin":
            ctx.reply(g.begin().message)
        elif sub == "hand":
            ctx.whisper(g.hand(ctx.nick, ctx.trip).message)
        elif sub == "status":
            ctx.reply(g.status().message)
        elif sub == "draw":
            ctx.reply(g.draw(ctx.nick, ctx.trip).message)
        elif sub == "play":
            if len(ctx.args) < 2:
                ctx.reply("用法：uno play <牌> [颜色]")
                return
            color = ctx.args[2] if len(ctx.args) > 2 else None
            r = g.play(ctx.nick, ctx.trip, ctx.args[1], color)
            if r and r.data and r.data.get("win"):
                ctx.app.coins.add(ctx.nick, ctx.trip, R.uno_win, reason="UNO 胜利")
                try:
                    ctx.app.stats.record_game(ctx.nick, ctx.trip, "uno", True)
                except Exception:
                    pass
                ctx.reply(r.message + f"\n[OK] +{R.uno_win} 金币")
            else:
                ctx.reply(r.message)
        else:
            ctx.reply("未知子命令")

    # ---------- 加密货币 ----------
    @router.command("crypto", "coin", help="加密货币 crypto price <币>|buy <币> <量>|sell <币> <量>|portfolio", category="游戏")
    def crypto(ctx):
        g = ctx.app.games.crypto
        if not ctx.args:
            ctx.reply(g.list_text() + "\n用法：crypto price <币> | buy <币> <量> | sell <币> <量> | portfolio")
            return
        sub = ctx.args[0].lower()
        if sub == "list":
            ctx.reply(g.list_text())
        elif sub == "price":
            if len(ctx.args) < 2:
                ctx.reply("用法：crypto price <币>")
                return
            info = g.price_info(ctx.args[1])
            ctx.reply(info["error"] if "error" in info else f"[INFO] {info['symbol']}: ${info['price']:,.2f}")
        elif sub in ("portfolio", "pf"):
            ctx.reply_smart(g.portfolio_text(ctx.user_key))
        elif sub == "buy":
            if len(ctx.args) < 3:
                ctx.reply("用法：crypto buy <币> <数量>")
                return
            sym = ctx.args[1].upper()
            qty = parse_float(ctx.args[2])
            if qty is None or qty <= 0:
                ctx.reply("数量无效")
                return
            price = g.quote(sym)
            if price is None:
                ctx.reply("报价不可用或不支持该币")
                return
            cost = int(round(price * qty))
            if cost <= 0:
                ctx.reply("金额过小")
                return
            spend = ctx.app.coins.spend(ctx.nick, ctx.trip, cost, reason=f"买入{sym}")
            if not spend:
                ctx.reply(spend.message)
                return
            g.add_holding(ctx.user_key, sym, qty)
            ctx.reply(f"[OK] 买入 {qty:g} {sym}，花费 {cost} 金币，余额 {spend.data['balance']}")
        elif sub == "sell":
            if len(ctx.args) < 3:
                ctx.reply("用法：crypto sell <币> <数量>")
                return
            sym = ctx.args[1].upper()
            qty = parse_float(ctx.args[2])
            if qty is None or qty <= 0:
                ctx.reply("数量无效")
                return
            price = g.quote(sym)
            if price is None:
                ctx.reply("报价不可用")
                return
            rem = g.remove_holding(ctx.user_key, sym, qty)
            if not rem:
                ctx.reply(rem.message)
                return
            proceeds = int(round(price * qty))
            ctx.app.coins.add(ctx.nick, ctx.trip, proceeds, reason=f"卖出{sym}")
            ctx.reply(f"[OK] 卖出 {qty:g} {sym}，获得 {proceeds} 金币")
        else:
            ctx.reply("未知子命令")
