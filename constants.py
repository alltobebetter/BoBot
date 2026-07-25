"""集中管理所有魔法数字、道具定义、文案模板（单一数据源）。"""

# ---- 展示相关 ----
RANK_EMOJI = ["🥇", "🥈", "🥉"]
WHISPER_THRESHOLD = 120          # 超过此长度的帮助/列表类文本改用私聊

# ---- AI 相关 ----
MAX_AI_INPUT = 4000              # 用户输入上限
MAX_AI_RESPONSE = 2000           # AI 回复上限
AI_MAX_TOOL_ROUNDS = 10          # function-calling 最大轮数
AI_MAX_HISTORY = 20              # 每个用户保存的对话条数

# ---- 道具（唯一数据源，商店/背包/广告共用）----
ITEMS = {
    "double_card": {"name": "签到翻倍卡", "desc": "下次签到金币翻倍"},
    "skip_card": {"name": "成语跳过卡", "desc": "成语接龙跳过一次"},
    "hint_card": {"name": "Wordle提示卡", "desc": "获得一个字母提示"},
    "color_card": {"name": "昵称颜色卡", "desc": "自定义昵称颜色"},
}


def item_name(item_id: str) -> str:
    return ITEMS.get(item_id, {}).get("name", item_id)
