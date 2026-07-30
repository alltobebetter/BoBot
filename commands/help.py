"""动态帮助（按分类 + 命令详细说明）。"""
from __future__ import annotations

# ---- 命令详细说明（help <命令名> 时显示）----
# 只列子命令/参数/示例，简短描述在大 help 里已有
DETAILS: dict[str, str] = {
    "ai": (
        "ai <内容>\n"
        "和 AI 对话，支持图片识别（发图 + ai 分析）\n"
        "\n"
        "用法：\n"
        "  ai 你好        和 AI 聊天\n"
        "  @BoB 你好      直接 @ 也可以触发\n"
        "  clearai        清空对话历史\n"
        "\n"
        "注：私聊直接发消息也会触发 AI"
    ),
    "bj": (
        "bj <下注|hit|stand|double|start|check|quit>\n"
        "21点 Blackjack，多人对战庄家\n"
        "\n"
        "子命令：\n"
        "  bj <下注>     下注加入（如 bj 50）\n"
        "  bj start      开始发牌（所有玩家就绪后）\n"
        "  bj hit        要牌\n"
        "  bj stand      停牌\n"
        "  bj double     双倍下注（仅首两张牌时可用）\n"
        "  bj check      查看当前局面\n"
        "  bj quit       退出（未开始时可退还）\n"
        "\n"
        "规则：\n"
        "  A 按 1 或 11 自动切换，J/Q/K 算 10\n"
        "  天然 Blackjack（首两张 = 21）赔率 1.5 倍\n"
        "  庄家 17 点必停牌"
    ),
    "packet": (
        "packet <金额> <人数> | packet <id> | packet\n"
        "红包系统，发红包 / 抢红包 / 查看列表\n"
        "\n"
        "用法：\n"
        "  packet 100 3    发 100 金币红包，3 人可抢\n"
        "  packet aB3xK9   抢指定 ID 的红包\n"
        "  packet          查看当前红包列表\n"
        "\n"
        "注：红包 24 小时未抢完自动退还给发送者"
    ),
    "wordle": (
        "wordle <猜词> | wordle hint | wordle status\n"
        "Wordle 猜词游戏\n"
        "\n"
        "子命令：\n"
        "  w <单词>       猜词（5 个字母）\n"
        "  w hint         使用提示卡获得一个字母（需道具）\n"
        "  w status       查看当前棋盘\n"
        "\n"
        "颜色：🟩 正确位置 🟨 存在但位置错 ⬜ 不存在"
    ),
    "dice": (
        "dice <注注> | dice join <注注> | dice roll\n"
        "多人比大小骰子\n"
        "\n"
        "子命令：\n"
        "  dice <注注>     开局并下注\n"
        "  dice join <注注>  加入并下注\n"
        "  dice roll       开骰，点数最大者赢奖池\n"
        "\n"
        "至少 2 人才能开骰"
    ),
    "zjh": (
        "zjh start <底注> | zjh call | zjh raise <金额> | zjh fold\n"
        "炸金花\n"
        "\n"
        "子命令：\n"
        "  zjh start <底注>  开局\n"
        "  zjh call       跟注\n"
        "  zjh raise <金额>  加注\n"
        "  zjh fold       弃牌\n"
        "  zjh check      查看局面\n"
        "\n"
        "牌型：豹子 > 顺金 > 金花 > 顺子 > 对子 > 单张"
    ),
    "uno": (
        "uno join | uno start | uno <牌> | uno draw | uno pass | uno check\n"
        "UNO 卡牌游戏\n"
        "\n"
        "子命令：\n"
        "  uno join       加入\n"
        "  uno start      开始（至少 2 人）\n"
        "  uno <颜色> <数字>  出牌（如 uno red 5）\n"
        "  uno draw       摸牌\n"
        "  uno pass       跳过（摸牌后无牌可出时）\n"
        "  uno check      查看手牌和当前局面"
    ),
    "crypto": (
        "crypto <买入|卖出|持有|行情> [参数]\n"
        "虚拟货币模拟交易\n"
        "\n"
        "子命令：\n"
        "  crypto 买入 <代号> <数量>  买入\n"
        "  crypto 卖出 <代号> <数量>  卖出\n"
        "  crypto 行情 [代号]        查看报价\n"
        "  crypto 持有               查看持仓\n"
        "\n"
        "支持 BTC/ETH/USDT 等主流币种"
    ),
    "guess": (
        "guess <数字>\n"
        "猜数字 1-100\n"
        "\n"
        "用法：\n"
        "  g 50           猜 50\n"
        "  g 75           范围会逐步缩小\n"
        "\n"
        "猜中获得金币奖励"
    ),
    "number": (
        "number <4位数字>\n"
        "1A2B 猜数字\n"
        "\n"
        "用法：\n"
        "  n 1234         猜 1234\n"
        "\n"
        "A = 数字和位置都对，B = 数字对但位置错"
    ),
    "idiom": (
        "idiom <成语>\n"
        "成语接龙\n"
        "\n"
        "用法：\n"
        "  idiom 一心一意  接「意」开头的成语\n"
        "  idiom skip      使用跳过卡（需道具）\n"
        "\n"
        "接不上可发 idiom skip 或等超时"
    ),
    "transfer": (
        "transfer <昵称#trip> <金额>\n"
        "给其他用户转账\n"
        "\n"
        "用法：\n"
        "  transfer Alice#abc123 50   给 Alice 转 50 金币\n"
        "  give Alice 50              简写（在线时可用昵称）\n"
        "\n"
        "注：对方不在线也可转账"
    ),
    "shop": (
        "shop | buy <物品id> [数量]\n"
        "商店与购买\n"
        "\n"
        "商品：\n"
        "  double_card    签到翻倍卡\n"
        "  skip_card       成语跳过卡\n"
        "  hint_card       Wordle 提示卡\n"
        "  color_card      昵称颜色卡\n"
        "  mystery_box     神秘宝箱\n"
        "\n"
        "用法：\n"
        "  shop            查看商品列表和价格\n"
        "  buy color_card  购买颜色卡\n"
        "  buy hint_card 3 购买 3 张提示卡"
    ),
    "bag": (
        "bag\n"
        "查看背包中的道具\n"
        "\n"
        "用法：bag（或 inventory / inv）"
    ),
    "color": (
        "color <hex|reset>\n"
        "设置昵称颜色（需颜色卡道具）\n"
        "\n"
        "用法：\n"
        "  color FF6600    设置为橙色\n"
        "  color 00FF00    设置为绿色\n"
        "  color reset     重置为默认色\n"
        "\n"
        "注：3 或 6 位十六进制，不含 # 号"
    ),
    "checkin": (
        "checkin\n"
        "每日签到，获得金币奖励\n"
        "\n"
        "奖励：基础 10 + 连签加成 + 排名加成\n"
        "连签 3/7/15/30 天额外加成\n"
        "使用签到翻倍卡可翻倍当日奖励"
    ),
    "rank": (
        "rank [coins|week|total]\n"
        "排行榜\n"
        "\n"
        "用法：\n"
        "  rank            金币排行（默认）\n"
        "  rank week       本周活跃排行\n"
        "  rank total       总活跃排行"
    ),
    "coins": (
        "coins\n"
        "查看金币余额和排名\n"
        "别名：money / balance / bal"
    ),
    "seen": (
        "seen <昵称> | seen *<识别码>\n"
        "查看用户最后发言时间和内容\n"
        "\n"
        "用法：\n"
        "  seen Alice       按昵称查\n"
        "  seen *abc123     按识别码查"
    ),
    "look": (
        "look <昵称>\n"
        "查看在线用户的加入时间和发言频率\n"
        "\n"
        "注：只能查当前在线的用户"
    ),
    "aka": (
        "aka <昵称> | aka *<hash>\n"
        "身份查询，基于 hack.chat 的 hash 记录历史昵称\n"
        "\n"
        "用法：\n"
        "  aka Alice       查 Alice 用过的所有 hash 和历史昵称\n"
        "  aka *Usq8WxD    直接用 hash 查历史昵称\n"
        "\n"
        "hash 基于 IP 生成，比 trip（基于密码）更稳定\n"
        "用户换密码 trip 会变，但 IP 不变 hash 就不变"
    ),
    "motto": (
        "motto <签名> | motto off\n"
        "设置个人签名，显示在 whois 身份卡片中\n"
        "\n"
        "用法：\n"
        "  motto 今天也要元气满满   设置签名\n"
        "  motto                      查看当前签名\n"
        "  motto off                  清除签名\n"
        "\n"
        "最多 100 字符"
    ),
    "whois": (
        "whois <昵称>\n"
        "查看用户的完整身份卡片\n"
        "\n"
        "包含信息：Trip / Hash / Level / Color / 状态（在线/离线）\n"
        "最后发言时间 / 聊天统计 / 个人签名 / 历史昵称\n"
        "\n"
        "别名：who"
    ),
    "time": (
        "time\n"
        "文学时钟，从文学作品中获取当前时间的引用\n"
        "\n"
        "数据来源：literature-clock.jenevoldsen.com"
    ),
    "today": (
        "today\n"
        "查看今日总结（每日 23:00 自动生成）\n"
        "\n"
        "包含：今日消息数、活跃用户、金句精选"
    ),
    "onthisday": (
        "onthisday\n"
        "历史上的今天，随机展示 5 条历史事件"
    ),
    "ping": (
        "ping\n"
        "测试机器人是否在线\n"
        "回复 pong"
    ),
    "profile": (
        "profile [昵称]\n"
        "查看用户画像（基于聊天历史 AI 生成）\n"
        "\n"
        "用法：\n"
        "  profile          查看自己的画像\n"
        "  profile Alice    查看别人的画像\n"
        "\n"
        "需要足够多的聊天记录才能生成"
    ),
    "dig": (
        "dig\n"
        "随机考古一条旧消息\n"
        "\n"
        "从聊天历史中随机抽取一条消息展示"
    ),
    "quote": (
        "quote\n"
        "随机展示一条金句\n"
        "\n"
        "金句来自管理员收藏的精彩发言"
    ),
    "star": (
        "star <昵称> <内容片段>\n"
        "收藏金句（管理员）\n"
        "\n"
        "用法：star Alice 今天天气真好\n"
        "\n"
        "收藏后可用 quote 随机展示"
    ),
    "friend": (
        "friend <链接> <标题> <描述> | friend delete\n"
        "友情链接管理\n"
        "\n"
        "用法：\n"
        "  friend https://example.com 我的网站 这是一个好站\n"
        "  friend delete    删除自己添加的友链"
    ),
    "msg": (
        "msg <昵称> <内容>\n"
        "给离线用户留言\n"
        "\n"
        "用法：msg Alice 回来后联系我\n"
        "\n"
        "对方上线时自动私聊送达"
    ),
    "clearai": (
        "clearai\n"
        "清空自己的 AI 对话历史\n"
        "\n"
        "AI 会从零开始对话，忘记之前的上下文"
    ),
    "addcoins": (
        "addcoins <昵称#trip> <数量>\n"
        "管理员发放/扣除金币\n"
        "\n"
        "用法：\n"
        "  addcoins Alice#abc123 100    发放 100 金币\n"
        "  addcoins Alice#abc123 -50     扣除 50 金币"
    ),
    "resetgame": (
        "resetgame\n"
        "重置所有游戏状态（管理员）\n"
        "\n"
        "适用于游戏卡住、状态异常时强制重置\n"
        "不会清除金币和统计"
    ),
    "say": (
        "say <内容>\n"
        "让机器人发送指定内容（管理员）\n"
        "\n"
        "用法：say 大家好\n"
        "BoB 会原样发送这条消息"
    ),
    "me": (
        "me <动作描述>\n"
        "发送动作描述（emote），显示为 * 昵称 <动作>\n"
        "\n"
        "用法：me 笑了   → * Alice 笑了"
    ),
    "stats": (
        "stats [week|total]\n"
        "查看自己的聊天统计\n"
        "\n"
        "用法：\n"
        "  stats           本周统计\n"
        "  stats total     总统计"
    ),
    "chatrank": (
        "chatrank\n"
        "聊天活跃排行榜（话痨榜）"
    ),
    "afk": (
        "afk [原因]\n"
        "设置离开状态\n"
        "\n"
        "用法：\n"
        "  afk             标记离开\n"
        "  afk 吃饭去了    带原因\n"
        "\n"
        "有人 @ 你时会自动提示 AFK 状态"
    ),
    "credits": (
        "credits\n"
        "致谢与开源信息\n"
        "\n"
        "展示 hack.chat、Awaya、HackChat Python 库等致谢\n"
        "以及 BoB 的开源仓库和社区信息"
    ),
    "feedback": (
        "feedback [内容]\n"
        "反馈 / 版本信息\n"
        "\n"
        "用法：\n"
        "  feedback         查看版本信息\n"
        "  feedback 有个bug  提交反馈\n"
        "\n"
        "注：反馈会存入数据库，管理员可查看并奖励采纳的反馈"
    ),
    "reward": (
        "reward <昵称> <金币> [道具:数量] [理由] | reward list | reward cancel <昵称>\n"
        "管理员挂奖励，用户进入聊天室时自动发放\n"
        "\n"
        "用法：\n"
        "  reward sun 300 反馈被采纳        给 sun 挂 300 金币奖励\n"
        "  reward sun 300 double_card:1 反馈  金币 + 道具\n"
        "  reward list                        查看待发放列表\n"
        "  reward cancel sun                  取消未发放的奖励"
    ),
    "feedbacks": (
        "feedbacks\n"
        "查看用户反馈列表（管理员）\n"
        "\n"
        "别名：fblist\n"
        "\n"
        "反馈由用户通过 feedback 命令提交，存入数据库"
    ),
    "welcome": (
        "welcome <文本> | welcome off\n"
        "设置入场欢迎词\n"
        "\n"
        "用法：\n"
        "  welcome 大家好    设置欢迎词\n"
        "  welcome off       关闭\n"
        "\n"
        "注：用 {nick} 代表你的昵称，设置收费 1 金币"
    ),
    "history": (
        "history [条数]\n"
        "查看最近消息（默认 10 条，最多 50 条）"
    ),
    "search": (
        "search <关键词>\n"
        "联网搜索（Tavily API）"
    ),
    "fortune": (
        "fortune\n"
        "今日运势，每日随机\n"
        "别名：yunshi"
    ),
    "code": (
        "code <需求描述>\n"
        "AI 代码生成，创建网页项目并预览\n"
        "\n"
        "注：需要配置 Supabase + AI"
    ),
    "ad": (
        "ad <广告内容>\n"
        "发布广告（花费金币），其他人观看可赚金币"
    ),
    "ads": (
        "ads\n"
        "观看广告领金币"
    ),
    "admin": (
        "admin <health|perf|clearai|cleanhist>\n"
        "管理员系统管理\n"
        "\n"
        "子命令：\n"
        "  admin health         系统健康检查\n"
        "  admin perf           性能监控\n"
        "  admin clearai        清除所有人 AI 记录\n"
        "  admin cleanhist [天数]  清理旧聊天记录"
    ),
    "serverstats": (
        "serverstats\n"
        "查看 hack.chat 服务器级统计（连接数/频道数/消息数/运行时间）\n"
        "别名：sstats"
    ),
    "changenick": (
        "changenick <新昵称>\n"
        "更改机器人昵称（管理员，不需要重连）\n"
        "别名：nick"
    ),
}


def register(router):
    @router.command("help", "menu", "帮助", help="显示帮助 help [命令名]", category="其他")
    def help_cmd(ctx):
        # help <命令名> → 详细说明
        if ctx.args:
            target = ctx.args[0].lower().lstrip("-")
            # 先查别名
            real_name = router._aliases.get(target, target)
            # 查详细说明
            detail = DETAILS.get(real_name) or DETAILS.get(target)
            if detail:
                ctx.reply_smart(f"[INFO] {detail}")
            else:
                # 没有详细说明，回退到简短描述
                entries = router.help_entries()
                info = entries.get(real_name) or entries.get(target)
                if info:
                    ctx.reply_smart(f"[INFO] {target} - {info['help']}")
                else:
                    ctx.reply(f"[ERR] 未找到命令「{target}」，输入 help 查看全部命令")
            return

        # help（无参数）→ 分类列表
        entries = router.help_entries()
        cats = {}
        for name, info in entries.items():
            cats.setdefault(info["category"], []).append((name, info["help"]))
        lines = [f"[INFO] {ctx.bot.config.bot.name} 命令帮助"]
        for cat in sorted(cats):
            lines.append(f"\n【{cat}】")
            for name, h in sorted(cats[cat]):
                lines.append(f"{name} - {h}" if h else f"{name}")
        lines.append(f"\n输入 help <命令名> 查看详细用法")
        lines.append(f"网页版：{ctx.bot.config.bot.web_url}")
        lines.append("开源：https://github.com/alltobebetter/BoBot")
        ctx.reply_smart("\n".join(lines))
