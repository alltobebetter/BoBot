"""其他命令：AFK、ping、版本、反馈、聊天历史、搜索、画像、代码、友链、留言。"""
from __future__ import annotations

import threading

from utils.logger import log
from utils.text import now


def register(router):
    @router.command("time", help="文学时钟（文学作品中的时间）", category="信息")
    def time(ctx):
        import random
        import time as _time

        try:
            import requests
        except ImportError:
            ctx.reply("需要安装 requests")
            return

        # 当前时间（UTC+8）
        now = _time.localtime(_time.time() + 8 * 3600)
        hour_min = f"{now.tm_hour:02d}_{now.tm_min:02d}"
        url = f"https://literature-clock.jenevoldsen.com/times/{hour_min}.json"
        try:
            resp = requests.get(url, timeout=10)
            data = resp.json()
            if not data:
                ctx.reply("[ERR] 暂无文学时钟数据")
                return
            item = random.choice(data)
            quote = item.get("quote_first", "") + f"**{item.get('quote_time_case', '')}**" + item.get("quote_last", "")
            quote = quote.replace("<br/>", "\n>")
            source = f"\n- {item.get('title', '?')}, *{item.get('author', '?')}*"
            ctx.reply(f"> {quote}\n{source}")
        except Exception as e:
            ctx.reply(f"[ERR] 获取失败：{e}")

    @router.command("today", help="历史上的今天", category="信息")
    def today(ctx):
        import random
        import time as _time

        try:
            import requests
        except ImportError:
            ctx.reply("需要安装 requests")
            return

        now = _time.localtime(_time.time() + 8 * 3600)
        month, day = now.tm_mon, now.tm_mday
        url = f"https://wai.shaiwang.life/api/history/{month}/{day}"
        try:
            resp = requests.get(url, timeout=10)
            data = resp.json()
            if not data:
                ctx.reply(f"[INFO] 历史上的 {month}月{day}日：暂无数据")
                return
            events = data if isinstance(data, list) else data.get("data", [])
            if not events:
                ctx.reply(f"[INFO] 历史上的 {month}月{day}日：暂无数据")
                return
            picked = random.sample(events, min(5, len(events)))
            lines = [f"[INFO] 历史上的 {month}月{day}日", ""]
            for e in picked:
                year = e.get("year", "?")
                title = e.get("title", e.get("event", "?"))
                lines.append(f"**{year}年** {title}")
            ctx.reply("\n".join(lines))
        except Exception as e:
            # fallback: 使用本地数据
            ctx.reply(f"[ERR] 获取失败：{e}\n历史上的 {month}月{day}日")

    @router.command("seen", help="查看用户最后发言 seen <昵称|#识别码>", category="信息")
    def seen(ctx):
        if not ctx.args:
            ctx.reply("用法：seen <昵称> 或 seen *<识别码>")
            return
        target = ctx.args[0]
        if target.startswith("*"):
            r = ctx.app.seen.get_by_trip(target[1:])
        else:
            target = target.lstrip("@")
            r = ctx.app.seen.get_by_nick(target)
        ctx.reply(r.message)

    @router.command("look", help="查看在线用户信息 look <昵称>", category="信息")
    def look(ctx):
        if not ctx.args:
            ctx.reply("用法：look <昵称>")
            return
        target = ctx.args[0].lstrip("@")
        r = ctx.app.look.get(target)
        ctx.reply(r.message)

    @router.command("aka", help="身份查询 aka <昵称> | aka *<hash>", category="信息")
    def aka(ctx):
        if not ctx.args:
            ctx.reply("用法：aka <昵称> 查历史昵称\naka *<hash> 通过 hash 查")
            return
        target = ctx.args[0]
        if target.startswith("*"):
            r = ctx.app.identity.lookup_by_hash(target[1:])
        else:
            target = target.lstrip("@")
            r = ctx.app.identity.lookup_by_nick(target)
        ctx.reply(r.message)

    @router.command("motto", help="个人签名 motto <签名|off>", category="信息")
    def motto(ctx):
        if not ctx.args:
            motto_text = ctx.app.motto.get(ctx.user_key)
            if motto_text:
                ctx.reply(f"[INFO] 你的签名：{motto_text}")
            else:
                ctx.reply("用法：motto <签名内容>（最多 100 字）\nmotto off 清除签名")
            return
        if ctx.args[0].lower() in ("off", "清除", "删除"):
            ctx.reply(ctx.app.motto.clear(ctx.user_key).message)
            return
        text = ctx.arg_str
        ctx.reply(ctx.app.motto.set(ctx.user_key, text).message)

    @router.command("whois", "who", help="身份卡片 whois <昵称>", category="信息")
    def whois(ctx):
        if not ctx.args:
            ctx.reply("用法：whois <昵称>")
            return
        target = ctx.args[0].lstrip("@")
        # 1. 在线信息（look）
        look_r = ctx.app.look.get(target)
        online = look_r.success
        # 2. 最后发言（seen）
        seen_r = ctx.app.seen.get_by_nick(target)
        # 3. 身份记录（aka）
        aka_r = ctx.app.identity.lookup_by_nick(target)
        # 4. 聊天统计
        try:
            stat = ctx.app.stats.get(target, "")
            stat_text = f"消息 {stat.get('messages', 0)} 条，字符 {stat.get('chars', 0)}"
        except Exception:
            stat_text = "统计不可用"
        # 5. 在线用户详情
        user_info = ctx.bot.online_users.get(target, {})
        trip = user_info.get("trip", "")
        hash_code = user_info.get("hash", "")
        level = user_info.get("level", "")
        color = user_info.get("color", "")
        is_bot = user_info.get("isBot", False)
        # 6. 个人签名（只查在线用户）
        motto_text = ""
        if online and trip:
            from utils.text import user_key
            motto_text = ctx.app.motto.get(user_key(target, trip)) or ""

        lines = [f"[INFO] {target} 的身份卡片"]
        if trip:
            lines.append(f"Trip: #{trip}")
        if hash_code:
            lines.append(f"Hash: {hash_code}")
        if level:
            lines.append(f"Level: {level}")
        if color:
            lines.append(f"Color: #{color}")
        if is_bot:
            lines.append("Bot: 是")
        lines.append(f"状态: {'在线' if online else '离线'}")
        if seen_r.success:
            lines.append(f"最后发言: {seen_r.message.split('最后发言：')[1].split(chr(10))[0] if '最后发言' in seen_r.message else '未知'}")
        lines.append(f"统计: {stat_text}")
        if motto_text:
            lines.append(f"签名: \"{motto_text}\"")
        if aka_r.success:
            # 提取历史昵称
            aka_lines = aka_r.message.split("\n")
            for al in aka_lines:
                if "历史昵称" in al:
                    lines.append(al.strip())
        ctx.reply("\n".join(lines))

    @router.command("me", help="发送动作描述 me <动作>", category="娱乐")
    def me(ctx):
        if not ctx.arg_str:
            ctx.reply("用法：me <动作描述>")
            return
        ctx.bot.emote(f"{ctx.nick} {ctx.arg_str}")

    @router.command("afk", help="设置离开 afk [原因]", category="其他")
    def afk(ctx):
        ctx.reply(ctx.app.afk.set(ctx.user_key, ctx.nick, ctx.arg_str).message)

    @router.command("ping", help="测试机器人", category="其他")
    def ping(ctx):
        ctx.reply("pong")

    @router.command("feedback", "bug", "version", "new", help="反馈/版本信息 feedback [内容]", category="其他")
    def feedback(ctx):
        if not ctx.arg_str:
            web = ctx.bot.config.bot.web_url
            ctx.reply(
                f"[INFO] {ctx.bot.config.bot.name} v{ctx.bot.VERSION}\n"
                "多 Provider AI · SQLite 存储 · 代码生成 · 聊天历史\n"
                f"网页版：{web}\n"
                "开源：https://github.com/alltobebetter/BoBot\n"
                "输入 help 查看全部功能"
            )
            return
        log.info("用户反馈", user=ctx.user_key, content=ctx.arg_str[:200])
        ctx.reply("[OK] 感谢反馈")

    @router.command("credits", "致谢", "credit", "thanks", help="致谢与开源信息", category="其他")
    def credits(ctx):
        ctx.reply(
            "致谢 Credits\n"
            "\n"
            "BoB 运行在 hack.chat 平台上，感谢官方开源服务器端代码，"
            "让 BoB 能深度适配协议。(・∀・)\n"
            "仓库：https://github.com/hack-chat/main\n"
            "\n"
            "部分功能设计参考了 Awaya(阿瓦娅)，感谢 21 点、红包、"
            "seen/look 等灵感～ BoB 用自己的风格重新实现了这些功能。\n"
            "仓库：https://github.com/Kroos372/awaya\n"
            "\n"
            "最初的 hackchat Python 封装来自 HackChat 库。\n"
            "仓库：https://github.com/gkbrk/hackchat\n"
            "\n"
            "---\n"
            "\n"
            "BoB 是完全开源的 hack.chat 机器人，欢迎更多小伙伴一起优化！\n"
            "Star / Issue / PR：https://github.com/alltobebetter/BoBot\n"
            "也欢迎更多开源的 hack.chat 机器人一起建设社区，"
            "让这个小聊天室变得更有趣吧～ ╰(°▽°)╯\n"
            "\n"
            "BoB 用心打造 ✦"
        )

    # ---- 聊天历史 ----

    @router.command("history", "历史", help="查看最近消息 history [条数]", category="信息")
    def history(ctx):
        limit = 10
        if ctx.args:
            try:
                limit = min(int(ctx.args[0]), 50)
            except ValueError:
                pass
        channel = ctx.bot.config.bot.room
        msgs = ctx.app.history.recent(limit=limit, channel=channel)
        if not msgs:
            ctx.reply("暂无聊天记录")
            return
        lines = [f"[INFO] 最近 {len(msgs)} 条消息："]
        for m in msgs:
            text = m["text"][:40] + "…" if len(m["text"]) > 40 else m["text"]
            lines.append(f"• {m['nick']}: {text}")
        lines.append(f"完整历史记录：{ctx.bot.config.bot.web_url}/history")
        ctx.reply_smart("\n".join(lines))

    @router.command("search", "搜索", help="搜索聊天记录 search <关键词>", category="信息")
    def search(ctx):
        if not ctx.arg_str:
            ctx.reply("用法：search <关键词>")
            return
        channel = ctx.bot.config.bot.room
        results = ctx.app.history.search(ctx.arg_str, limit=10, channel=channel)
        if not results:
            ctx.reply(f"未找到包含「{ctx.arg_str}」的消息")
            return
        lines = [f"[INFO] 搜索「{ctx.arg_str}」结果："]
        for m in results:
            text = m["text"][:50] + "…" if len(m["text"]) > 50 else m["text"]
            lines.append(f"• {m['nick']}: {text}")
        lines.append(f"更多结果：{ctx.bot.config.bot.web_url}/history")
        ctx.reply_smart("\n".join(lines))

    # ---- 考古 ----

    @router.command("dig", "考古", help="随机考古一条旧消息 dig", category="娱乐")
    def dig(ctx):
        channel = ctx.bot.config.bot.room
        msg = ctx.app.history.random_message(channel=channel, min_days_ago=3)
        if not msg:
            ctx.reply("[INFO] 还没有足够的历史消息可以考古")
            return
        ts = msg["ts"][:16].replace("T", " ") if msg["ts"] else ""
        text = msg["text"][:200] + ("..." if len(msg["text"]) > 200 else "")
        ctx.reply(f"[INFO] 考古发现\n[{ts}] {msg['nick']}: {text}")

    # ---- 金句 ----

    @router.command("star", "金句", help="收藏金句 star <昵称> <内容片段>", category="娱乐")
    def star(ctx):
        if len(ctx.args) < 2:
            ctx.reply("用法：star <昵称> <消息内容片段>\n示例：star Alice 今天天气不错")
            return
        target_nick = ctx.args[0]
        fragment = ctx.arg_str[len(target_nick):].strip()
        if not fragment:
            ctx.reply("内容片段不能为空")
            return
        # 在聊天记录中查找匹配的消息
        channel = ctx.bot.config.bot.room
        results = ctx.app.history.search(fragment, limit=10, channel=channel)
        # 优先匹配指定昵称的消息
        match = None
        for m in results:
            if m["nick"] == target_nick:
                match = m
                break
        if not match:
            ctx.reply(f"[INFO] 未找到 {target_nick} 说过包含「{fragment}」的消息")
            return
        r = ctx.app.quotes.add(
            channel, match["nick"], match.get("trip", ""),
            match["text"], starred_by=ctx.nick,
        )
        ctx.reply(r.message)

    @router.command("quote", "金句随机", help="随机一条金句 quote", category="娱乐")
    def quote(ctx):
        channel = ctx.bot.config.bot.room
        quotes = ctx.app.quotes.random(channel=channel, limit=1)
        if not quotes:
            ctx.reply("[INFO] 还没有收藏任何金句，用 star <昵称> <内容> 来收藏")
            return
        q = quotes[0]
        ts = q["ts"][:16].replace("T", " ") if q["ts"] else ""
        ctx.reply(f"[INFO] 金句\n[{ts}] {q['nick']}: {q['text']}\n更多金句：{ctx.bot.config.bot.web_url}/quotes")

    # ---- 每日总结 ----

    @router.command("today", "日报", help="查看今日总结 today", category="信息")
    def today(ctx):
        channel = ctx.bot.config.bot.room
        existing = ctx.app.digest.get_today(channel)
        if existing:
            ctx.reply(f"[INFO] 今日总结\n\n{existing}")
            return
        # 没有总结，检查消息量
        msg_count = ctx.app.history.count_today(channel)
        if msg_count < ctx.app.digest.MIN_MESSAGES:
            ctx.reply(
                f"[INFO] 今日总结将在 {ctx.app.digest.SCHEDULE_HOUR}:{ctx.app.digest.SCHEDULE_MINUTE:02d} 自动生成\n"
                f"当前消息数 {msg_count}/{ctx.app.digest.MIN_MESSAGES}"
            )
            return
        ctx.reply("[INFO] 今日总结尚未生成，正在生成...")

        def _worker():
            result = ctx.app.digest.generate(channel)
            if result:
                ctx.bot.say(f"[INFO] 今日总结\n\n{result.message}")
            else:
                ctx.bot.say(f"[INFO] {result.message}")

        threading.Thread(target=_worker, daemon=True).start()

    # ---- 用户画像 ----

    @router.command("profile", "画像", help="查看用户画像 profile [昵称]", category="信息")
    def profile(ctx):
        target = ctx.args[0] if ctx.args else ctx.nick
        ctx.reply("[INFO] 正在生成画像...")
        def _worker():
            result = ctx.app.profile.get_profile(target)
            ctx.reply(result.message)
        threading.Thread(target=_worker, daemon=True).start()

    # ---- CodeAgent ----

    @router.command("code", "编程", help="AI 写代码 code <需求>", category="AI")
    def code(ctx):
        agent = ctx.app.codeagent
        if not agent.available:
            ctx.reply("CodeAgent 未配置（需要 Supabase + AI）")
            return
        if not ctx.arg_str:
            preview = agent.preview_url(ctx.nick, ctx.trip)
            ctx.reply(f"用法：code <需求描述>\n你的项目地址：{preview}")
            return

        # 速率限制
        if not ctx.is_admin and not ctx.app.rate_ai.allow(ctx.user_key):
            ctx.reply("[WARN] 请求太频繁，请稍后再试")
            return

        preview = agent.preview_url(ctx.nick, ctx.trip)
        ctx.reply(f"@{ctx.nick} 任务已创建，完成后回复你。\n项目地址：{preview}")

        def _worker():
            try:
                result = agent.run(ctx.nick, ctx.trip, ctx.arg_str)
                if result:
                    ctx.bot.say(f"@{ctx.nick} [OK] {result.message}\n预览：{preview}")
                else:
                    ctx.bot.say(f"@{ctx.nick} [ERR] {result.message}")
            except Exception as e:
                log.error("CodeAgent 执行失败", exc=e)
                ctx.bot.say(f"@{ctx.nick} [ERR] 执行出错")

        threading.Thread(target=_worker, daemon=True).start()

    # ---- 友情链接 ----

    @router.command("friend", "友链", help="友情链接 friend <链接> <标题> <描述> | friend delete", category="其他")
    def friend(ctx):
        if not ctx.args:
            ctx.reply("用法：friend <链接> <标题> <描述>\nfriend delete - 删除友链")
            return
        sub = ctx.args[0].lower()
        if sub == "delete":
            ctx.reply(ctx.app.friends.delete(ctx.nick, ctx.trip).message)
            return
        if len(ctx.args) < 3:
            ctx.reply("用法：friend <链接> <标题> <描述>")
            return
        link = ctx.args[0]
        if not link.startswith("http"):
            ctx.reply("链接必须以 http:// 或 https:// 开头")
            return
        name = ctx.args[1]
        desc = " ".join(ctx.args[2:])
        ctx.reply(ctx.app.friends.add(ctx.nick, ctx.trip, link, name, desc).message)

    # ---- 留言 ----

    @router.command("msg", "留言", help="给离线用户留言 msg <昵称> <内容>", category="其他")
    def msg(ctx):
        if len(ctx.args) < 2:
            ctx.reply("用法：msg <昵称> <留言内容>")
            return
        to_nick = ctx.args[0]
        text = ctx.arg_str[len(to_nick):].strip()
        if not text:
            ctx.reply("留言内容不能为空")
            return
        # 在线则直接私聊通知
        if to_nick in ctx.bot.online_users:
            ts = now().strftime("%m-%d %H:%M")
            ctx.bot.whisper(to_nick, f"[INFO] {ctx.nick} 给你留言（{ts}）：{text}")
            ctx.reply(f"[OK] {to_nick} 在线，已通过私聊通知")
            return
        r = ctx.app.messages.leave(ctx.nick, ctx.trip, to_nick, text)
        ctx.reply(r.message)
