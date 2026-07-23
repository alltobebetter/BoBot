"""统一配置（纯环境变量 + dataclass）。"""
import os
from dataclasses import dataclass, field
from typing import Dict, List

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


def _int(key: str, default: int = 0) -> int:
    try:
        return int(os.getenv(key, default))
    except (ValueError, TypeError):
        return default


def _list(key: str, default=None, sep: str = ",") -> List[str]:
    v = os.getenv(key, "")
    if not v:
        return list(default or [])
    return [x.strip() for x in v.split(sep) if x.strip()]


def _int_list(key: str, default: List[int]) -> List[int]:
    vals = _list(key)
    if not vals:
        return list(default)
    try:
        return [int(x) for x in vals]
    except ValueError:
        return list(default)


def _admins(raw: str) -> List[Dict[str, str]]:
    out = []
    for item in raw.split(","):
        if ":" in item:
            nick, trip = item.split(":", 1)
            out.append({"nick": nick.strip(), "trip": trip.strip()})
    return out


# 昵称后缀单词库（3-5 个字母的常见单词，重连时随机选取避免昵称冲突）
NICK_SUFFIXES: List[str] = [
    # 动物
    "Cat", "Dog", "Fox", "Owl", "Bee", "Ant", "Bat", "Cow", "Pig", "Hen",
    "Bear", "Bird", "Crab", "Deer", "Duck", "Fish", "Frog", "Goat", "Lion", "Wolf",
    # 水果/食物
    "Apple", "Grape", "Lemon", "Mango", "Peach", "Berry", "Candy", "Bread", "Cake", "Milk",
    # 颜色
    "Red", "Blue", "Gold", "Pink", "Gray", "Cyan", "Jade", "Ruby", "Navy",
    # 自然
    "Sun", "Moon", "Star", "Rain", "Snow", "Wind", "Fire", "Ice", "Rock", "Sand",
    "Cloud", "Storm", "River", "Ocean", "Lake", "Tree", "Leaf", "Rose", "Lily",
    # 其他
    "Ace", "Bit", "Dot", "Key", "Gem", "Orb", "Zen", "Neo", "Max", "Sky",
    "Echo", "Nova", "Pixel", "Spark", "Flash", "Swift", "Lucky", "Happy", "Sunny",
]


@dataclass
class BotConfig:
    name: str = os.getenv("BOT_NAME", "BoB")
    room: str = os.getenv("BOT_ROOM", "lounge")
    password: str = os.getenv("BOT_PASSWORD", "")
    server_url: str = os.getenv("BOT_SERVER_URL", "wss://hack.chat/chat-ws")
    prefix: str = os.getenv("BOT_PREFIX", "")
    admin_users: List[Dict[str, str]] = field(
        default_factory=lambda: _admins(os.getenv("BOT_ADMINS", ""))
    )
    # 健康监控
    health_check_interval: int = _int("HEALTH_CHECK_INTERVAL", 10)
    health_inactive_timeout: int = _int("HEALTH_INACTIVE_TIMEOUT", 300)
    nick_suffixes: List[str] = field(default_factory=lambda: NICK_SUFFIXES)

    def is_admin(self, nick: str, trip: str) -> bool:
        return any(
            a.get("nick") == nick and a.get("trip") == trip for a in self.admin_users
        )


@dataclass
class Provider:
    """AI 提供商配置（OpenAI 兼容接口）。"""
    name: str
    api_key: str
    base_url: str
    model: str


def _load_providers() -> List[Provider]:
    """从环境变量加载 AI provider 列表（按优先级排列）。

    新格式（推荐）：
        AI_PROVIDERS=kilo,nvidia
        AI_KILO_API_KEY=...
        AI_KILO_BASE_URL=...
        AI_KILO_MODEL=...
        AI_NVIDIA_API_KEY=...
        ...

    旧格式（向后兼容）：
        OPENAI_API_KEYS=...
        OPENAI_BASE_URL=...
        OPENAI_MODEL=...
    """
    names = _list("AI_PROVIDERS")
    if names:
        providers = []
        for name in names:
            prefix = f"AI_{name.upper()}"
            key = os.getenv(f"{prefix}_API_KEY", "")
            base = os.getenv(f"{prefix}_BASE_URL", "")
            model = os.getenv(f"{prefix}_MODEL", "")
            if key and base and model:
                providers.append(Provider(name, key, base, model))
        return providers
    # 向后兼容：用旧的 OPENAI_* 作为唯一 provider
    keys = _list("OPENAI_API_KEYS")
    if keys:
        return [Provider(
            name="default",
            api_key=keys[0],
            base_url=os.getenv("OPENAI_BASE_URL", ""),
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        )]
    return []


@dataclass
class ApiConfig:
    openai_keys: List[str] = field(default_factory=lambda: _list("OPENAI_API_KEYS"))
    openai_base: str = os.getenv("OPENAI_BASE_URL", "")
    model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    # 多 provider 支持（Kilo 主力 + NVIDIA 保底等）
    providers: List[Provider] = field(default_factory=_load_providers)
    tavily_keys: List[str] = field(default_factory=lambda: _list("TAVILY_API_KEYS"))
    finnhub_key: str = os.getenv("FINNHUB_API_KEY", "")
    gyazo_token: str = os.getenv("GYAZO_TOKEN", "")
    # Supabase（CodeAgent + 友情链接）
    supabase_url: str = os.getenv("SUPABASE_URL", "")
    supabase_key: str = os.getenv("SUPABASE_SERVICE_KEY", "")
    supabase_bucket: str = os.getenv("SUPABASE_BUCKET", "Code")
    code_preview_base: str = os.getenv("CODE_PREVIEW_BASE", "https://bob.supage.eu.org/code")
    # AI 并发上限（256MB/0.25CPU 机器默认 3，IO 密集场景够用且留有余量）
    ai_concurrency: int = _int("AI_CONCURRENCY", 3)

    @property
    def ai_enabled(self) -> bool:
        return bool(self.providers or self.openai_keys)

    @property
    def gyazo_enabled(self) -> bool:
        return bool(self.gyazo_token)


@dataclass
class GameConfig:
    wordle_timeout: int = _int("GAME_WORDLE_TIMEOUT", 600)
    idiom_timeout: int = _int("GAME_IDIOM_TIMEOUT", 30)
    dice_timeout: int = _int("GAME_DICE_TIMEOUT", 60)
    zjh_timeout: int = _int("GAME_ZJH_TIMEOUT", 300)


@dataclass
class RewardsConfig:
    checkin_base: int = _int("REWARD_CHECKIN_BASE", 10)
    checkin_rank_bonus: List[int] = field(
        default_factory=lambda: _int_list("REWARD_CHECKIN_RANK_BONUS", [20, 15, 10])
    )
    checkin_streak_bonus: Dict[int, int] = field(
        default_factory=lambda: {
            3: _int("REWARD_CHECKIN_STREAK_3", 5),
            7: _int("REWARD_CHECKIN_STREAK_7", 15),
            15: _int("REWARD_CHECKIN_STREAK_15", 30),
            30: _int("REWARD_CHECKIN_STREAK_30", 50),
        }
    )
    wordle_win: int = _int("REWARD_WORDLE_WIN", 30)
    uno_win: int = _int("REWARD_UNO_WIN", 50)
    idiom_win: List[int] = field(
        default_factory=lambda: _int_list("REWARD_IDIOM_WIN", [100, 60, 30])
    )
    guess_win: int = _int("REWARD_GUESS_WIN", 50)
    number_win: int = _int("REWARD_NUMBER_WIN", 25)


@dataclass
class ShopConfig:
    custom_welcome_price: int = _int("SHOP_CUSTOM_WELCOME_PRICE", 50)
    custom_welcome_update_price: int = _int("SHOP_CUSTOM_WELCOME_UPDATE_PRICE", 1)
    double_card_price: int = _int("SHOP_DOUBLE_CARD_PRICE", 60)
    skip_card_price: int = _int("SHOP_SKIP_CARD_PRICE", 40)
    hint_card_price: int = _int("SHOP_HINT_CARD_PRICE", 30)
    mystery_box_price: int = _int("SHOP_MYSTERY_BOX_PRICE", 80)


@dataclass
class AdsConfig:
    post_cost: int = _int("ADS_POST_COST", 20)
    daily_view_limit: int = _int("ADS_DAILY_VIEW_LIMIT", 3)
    view_reward_min: int = _int("ADS_VIEW_REWARD_MIN", 10)
    view_reward_max: int = _int("ADS_VIEW_REWARD_MAX", 50)
    ad_view_cap: int = _int("ADS_AD_VIEW_CAP", 5)


@dataclass
class LimitsConfig:
    global_max: int = _int("RATE_GLOBAL_MAX", 10)
    global_window: int = _int("RATE_GLOBAL_WINDOW", 60)
    ai_max: int = _int("RATE_AI_MAX", 5)
    ai_window: int = _int("RATE_AI_WINDOW", 60)


@dataclass
class ApiServerConfig:
    """内嵌 HTTP API Server 配置。"""
    enabled: bool = _int("API_ENABLED", 0) != 0
    host: str = os.getenv("API_HOST", "::")  # IPv6 优先
    port: int = _int("API_PORT", 8300)
    api_key: str = os.getenv("API_KEY", "")


@dataclass
class Config:
    db_path: str = os.getenv("DATABASE_PATH", "data/aibob.db")
    data_dir: str = os.getenv("DATA_DIR", "data/games")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    bot: BotConfig = field(default_factory=BotConfig)
    api: ApiConfig = field(default_factory=ApiConfig)
    game: GameConfig = field(default_factory=GameConfig)
    rewards: RewardsConfig = field(default_factory=RewardsConfig)
    shop: ShopConfig = field(default_factory=ShopConfig)
    ads: AdsConfig = field(default_factory=AdsConfig)
    limits: LimitsConfig = field(default_factory=LimitsConfig)
    api_server: ApiServerConfig = field(default_factory=ApiServerConfig)


config = Config()
