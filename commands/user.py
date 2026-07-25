"""经济 / 信息 / 娱乐类命令。"""
from __future__ import annotations

from config import config
from constants import item_name
from utils.text import render_ranking
from utils.validate import parse_positive_int


def register(router):
    @router.command("coins", "money", "balance", "bal", help="查询金币余额", category="经济")
    def coins(ctx):
        bal = ctx.app.coins.balance(ctx.nick, ctx.trip)
        rank = ctx.app.coins.rank_of(ctx.user_key)
        ctx.reply(f"[OK] {ctx.nick} 余额：{bal} 金币（排名 #{rank}）")

    @router.command("checkin", "qd", help="每日签到", category="经济")
    def checkin(ctx):
        ctx.reply(ctx.app.checkin.checkin(ctx.nick, ctx.trip).message)

    @router.command("rank", "top", help="排行榜 rank [coins|week|total]", category="经济")
    def rank(ctx):
        sub = ctx.args[0].lower() if ctx.args else "coins"
        if sub == "week":
            rows = ctx.app.stats.top_weekly(10)
            text = render_ranking("[INFO] 本周话痨榜", rows,
                lambda r: f"{r['nick']} - {r['messages']} 条")
            text += f"\n完整排行：{ctx.bot.config.bot.web_url}/leaderboard"
            ctx.reply_smart(text)
            return
        if sub == "total":
            rows = ctx.app.stats.top_chatters(10)
            text = render_ranking("[INFO] 总话痨榜", rows,
                lambda r: f"{r['nick']} - {r['messages']} 条")
            text += f"\n完整排行：{ctx.bot.config.bot.web_url}/leaderboard"
            ctx.reply_smart(text)
            return
        # 默认金币排行
        rows = ctx.app.coins.rankings(10)
        text = render_ranking("[INFO] 金币排行榜", rows, lambda r: f"{r['nick']} - {r['coins']}")
        text += f"\n完整排行：{ctx.bot.config.bot.web_url}/leaderboard"
        ctx.reply_smart(text)

    @router.command("transfer", "give", help="转账 transfer <昵称#trip> <金额>", category="经济")
    def transfer(ctx):
        if len(ctx.args) < 2:
            ctx.reply("用法：transfer <昵称#trip> <金额>")
            return
        amount = parse_positive_int(ctx.args[-1])
        target = " ".join(ctx.args[:-1])
        if amount is None:
            ctx.reply("金额无效")
            return
        ctx.reply(ctx.app.coins.transfer(ctx.nick, ctx.trip, target, amount).message)

    @router.command("packet", "红包", "redpacket", help="红包 packet <金额> <人数> | packet <id> | packet", category="经济")
    def packet(ctx):
        if not ctx.args:
            # 查看红包列表
            r = ctx.app.redpacket.list_packets()
            ctx.reply(r.message)
            return
        # 尝试解析为抢红包（ID 是字母数字混合）
        sub = ctx.args[0]
        if len(sub) == 6 and not sub.isdigit() and sub.isalnum():
            r = ctx.app.redpacket.grab(ctx.nick, ctx.trip, sub)
            if r and r.data and "grant" in r.data:
                ctx.app.coins.add(r.data["to_nick"], r.data["to_trip"], r.data["grant"], reason="抢红包")
            ctx.reply(r.message)
            return
        # 解析为发红包：packet <金额> <人数>
        if len(ctx.args) < 2:
            ctx.reply("用法：\npacket <金额> <人数>  发红包\npacket <id>  抢红包\npacket  查看列表")
            return
        amount = parse_positive_int(ctx.args[0])
        people = parse_positive_int(ctx.args[1])
        if amount is None or people is None:
            ctx.reply("金额和人数必须是正整数")
            return
        # 检查余额
        if ctx.app.coins.balance(ctx.nick, ctx.trip) < amount:
            ctx.reply(f"金币不足（需要 {amount}）")
            return
        r = ctx.app.redpacket.create(ctx.nick, ctx.trip, amount, people)
        if not r:
            ctx.reply(r.message)
            return
        # 扣费
        ctx.app.coins.spend(ctx.nick, ctx.trip, amount, reason="发红包")
        ctx.reply(r.message)

    @router.command("shop", help="查看商店", category="经济")
    def shop(ctx):
        ctx.reply_smart(ctx.app.shop.list_text())

    @router.command("buy", help="购买 buy <物品id> [数量]", category="经济")
    def buy(ctx):
        if not ctx.args:
            ctx.reply("用法：buy <物品id> [数量]，shop 查看")
            return
        qty = parse_positive_int(ctx.args[1]) if len(ctx.args) > 1 else 1
        ctx.reply(ctx.app.shop.buy(ctx.nick, ctx.trip, ctx.args[0], qty or 1).message)

    @router.command("bag", "inventory", "inv", help="查看背包", category="经济")
    def bag(ctx):
        items = ctx.app.inventory.get_all(ctx.user_key)
        if not items:
            ctx.reply("[INFO] 背包是空的")
            return
        lines = ["[INFO] 背包："] + [f"• {item_name(i)} x{q}" for i, q in items.items()]
        ctx.reply_smart("\n".join(lines))

    @router.command("welcome", help="设置入场欢迎词 welcome <文本|off>", category="经济")
    def welcome(ctx):
        if not ctx.args:
            ctx.reply("用法：welcome <文本>（用 {nick} 代表昵称），welcome off 关闭")
            return
        if ctx.args[0].lower() == "off":
            ctx.app.users.set_welcome(ctx.nick, ctx.trip, None)
            ctx.reply("已关闭欢迎词")
            return
        price = config.shop.custom_welcome_update_price
        spend = ctx.app.coins.spend(ctx.nick, ctx.trip, price, reason="设置欢迎词")
        if not spend:
            ctx.reply(spend.message)
            return
        ctx.app.users.set_welcome(ctx.nick, ctx.trip, ctx.arg_str)
        ctx.reply(f"[OK] 欢迎词已设置（花费 {price} 金币）")

    @router.command("color", "颜色", help="设置昵称颜色 color <hex|reset>", category="经济")
    def color(ctx):
        if not ctx.args:
            ctx.reply("用法：color <十六进制颜色> 或 color reset\n示例：color FF6600（橙色）, color 00FF00（绿色）")
            return
        target = ctx.args[0].upper().replace("#", "")
        if target == "RESET":
            ctx.bot.conn.change_color("RESET")
            ctx.reply("[OK] 已重置昵称颜色")
            return
        # 验证 hex 颜色：3 或 6 位 0-9A-F
        import re
        if not re.match(r'^[0-9A-F]{3}([0-9A-F]{3})?$', target):
            ctx.reply("颜色格式无效，请输入 3 或 6 位十六进制（如 FF6600）")
            return
        # 消耗颜色卡
        if not ctx.app.inventory.use(ctx.user_key, "color_card"):
            ctx.reply("你没有昵称颜色卡，商店购买：buy color_card")
            return
        ctx.bot.conn.change_color(target)
        ctx.reply(f"[OK] 昵称颜色已设置为 #{target}")

    @router.command("stats", help="聊天统计 stats [week|total]", category="信息")
    def stats(ctx):
        if ctx.args and ctx.args[0].lower() == "week":
            rows = ctx.app.stats.top_weekly(10)
            text = render_ranking("[INFO] 本周发言排行", rows,
                lambda r: f"{r['nick']} - {r['messages']} 条")
            ctx.reply_smart(text)
            return
        if ctx.args and ctx.args[0].lower() == "total":
            rows = ctx.app.stats.top_chatters(10)
            text = render_ranking("[INFO] 总发言排行", rows,
                lambda r: f"{r['nick']} - {r['messages']} 条")
            ctx.reply_smart(text)
            return
        # 默认：个人统计
        s = ctx.app.stats.get(ctx.user_key)
        weekly = ctx.app.stats.user_weekly(ctx.user_key)
        if not s:
            ctx.reply(f"[INFO] {ctx.nick}：本周 0 条，总计 0 条")
            return
        ctx.reply(f"[INFO] {ctx.nick}：本周 {weekly} 条，总计 {s['messages']} 条，字符 {s['chars']}")

    @router.command("chatrank", help="聊天活跃排行", category="信息")
    def chatrank(ctx):
        rows = ctx.app.stats.top_chatters(10)
        text = render_ranking("[INFO] 话痨榜", rows, lambda r: f"{r['nick']} - {r['messages']} 条")
        text += f"\n完整排行：{ctx.bot.config.bot.web_url}/leaderboard"
        ctx.reply_smart(text)

    @router.command("fortune", "yunshi", help="今日运势", category="娱乐")
    def fortune(ctx):
        ctx.reply_smart(ctx.app.fortune.daily(ctx.nick, ctx.trip).message)

    @router.command("ad", help="发布广告 ad <内容>", category="娱乐")
    def ad(ctx):
        if not ctx.args:
            ctx.reply("用法：ad <广告内容>")
            return
        ctx.reply(ctx.app.ads.post(ctx.nick, ctx.trip, ctx.arg_str).message)

    @router.command("ads", help="观看广告领金币", category="娱乐")
    def ads_view(ctx):
        ctx.reply(ctx.app.ads.view(ctx.nick, ctx.trip).message)
