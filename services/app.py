"""App 容器：统一装配数据库与所有 service / game。

所有命令通过 ctx.app 访问服务，彻底消除旧项目中的循环引用与全局单例懒加载。
"""
from __future__ import annotations

from config import config
from services.ads import AdsService
from services.afk import AFKService
from services.ai import AIService
from services.codeagent import CodeAgent
from services.digest import DigestService
from services.economy import CheckinService, CoinService, InventoryService, ShopService
from services.fortune import FortuneService
from services.friends import FriendsService
from services.history import HistoryService
from services.identity import IdentityService, MottoService
from services.messages import MessageService
from services.profile import ProfileService
from services.quotes import QuoteService
from services.redpacket import RedPacketService
from services.seen import LookService, SeenService
from services.stats import StatsService
from services.users import UserManager
from storage.db import Database
from storage.kv import KVStore
from utils.cache import TTLCache
from utils.ratelimit import RateLimiter


class GameRegistry:
    """持有所有游戏实例（游戏为纯逻辑，不直接操作金币）。"""

    def __init__(self, kv: KVStore):
        from games.crypto import CryptoGame
        from games.dice import DiceGame
        from games.guess import GuessGame, NumberGame
        from games.idiom import IdiomGame
        from games.uno import UnoGame
        from games.wordle import WordleGame
        from games.zhajinhua import ZhaJinHuaGame
        from games.blackjack import BlackjackGame

        self.wordle = WordleGame()
        self.idiom = IdiomGame()
        self.dice = DiceGame()
        self.guess = GuessGame()
        self.number = NumberGame()
        self.zhajinhua = ZhaJinHuaGame()
        self.uno = UnoGame()
        self.crypto = CryptoGame(kv)
        self.blackjack = BlackjackGame()


class App:
    def __init__(self):
        self.config = config
        self.bot = None  # 由 Bot 构造时回填

        # 存储
        self.db = Database(config.db_path)
        self.kv = KVStore(self.db)

        # 经济 / 用户
        self.users = UserManager(self.db)
        self.coins = CoinService(self.db, self.users)
        self.inventory = InventoryService(self.db, self.users)
        self.shop = ShopService(self.coins, self.inventory, self.users)
        self.checkin = CheckinService(self.db, self.users, self.coins, self.inventory)

        # 其他 service
        self.stats = StatsService(self.db)
        self.history = HistoryService(self.db)
        self.messages = MessageService(self.db)
        self.fortune = FortuneService(config.data_dir)
        self.ads = AdsService(self.kv, self.coins)
        self.afk = AFKService()
        self.ai = AIService(self)
        self.profile = ProfileService(self)
        self.codeagent = CodeAgent(self)
        self.friends = FriendsService()
        self.quotes = QuoteService(self.db)
        self.digest = DigestService(self)
        self.redpacket = RedPacketService(self.kv, self.coins)
        self.seen = SeenService(self.kv)
        self.look = LookService()
        self.identity = IdentityService(self.kv)
        self.motto = MottoService(self.kv)

        # 游戏
        self.games = GameRegistry(self.kv)

        # 基础设施
        self.cache = TTLCache()
        self.rate_global = RateLimiter(config.limits.global_max, config.limits.global_window)
        self.rate_ai = RateLimiter(config.limits.ai_max, config.limits.ai_window)

    def close(self) -> None:
        self.db.close()
