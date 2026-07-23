"""模拟加密货币交易（价格来自 Finnhub / Binance）。

持仓存于 SQLite 的 kv 表（namespace='crypto'）。
金币买卖由命令层处理：本模块只提供报价与持仓变更。
"""
from __future__ import annotations

from typing import Dict, Optional

from config import config
from core.result import Result
from storage.kv import KVStore

_NS = "crypto"

COINS: Dict[str, str] = {
    "BTC": "BINANCE:BTCUSDT",
    "ETH": "BINANCE:ETHUSDT",
    "BNB": "BINANCE:BNBUSDT",
    "SOL": "BINANCE:SOLUSDT",
    "DOGE": "BINANCE:DOGEUSDT",
    "XRP": "BINANCE:XRPUSDT",
}


class CryptoGame:
    name = "crypto"

    def __init__(self, kv: KVStore):
        self.kv = kv

    @property
    def enabled(self) -> bool:
        return bool(config.api.finnhub_key)

    # ---- 报价 ----
    def quote(self, symbol: str) -> Optional[float]:
        symbol = symbol.upper()
        pair = COINS.get(symbol)
        if not pair or not self.enabled:
            return None
        try:
            import requests

            resp = requests.get(
                "https://finnhub.io/api/v1/quote",
                params={"symbol": pair, "token": config.api.finnhub_key},
                timeout=10,
            )
            price = resp.json().get("c")
            return float(price) if price else None
        except Exception:
            return None

    def price_info(self, symbol: str) -> Dict:
        symbol = symbol.upper()
        if symbol not in COINS:
            return {"error": f"不支持 {symbol}，可选：{', '.join(COINS)}"}
        price = self.quote(symbol)
        if price is None:
            return {"error": "报价不可用"}
        return {"symbol": symbol, "price": price}

    def list_text(self) -> str:
        return "[INFO] 支持的币种：" + "、".join(COINS)

    # ---- 持仓 ----
    def portfolio(self, key: str) -> Dict[str, float]:
        return self.kv.get(_NS, key, {}) or {}

    def portfolio_text(self, key: str) -> str:
        pf = self.portfolio(key)
        if not pf:
            return "[INFO] 你的持仓为空"
        lines = ["[INFO] 你的持仓："]
        for sym, qty in pf.items():
            lines.append(f"{sym}: {qty:g}")
        return "\n".join(lines)

    def add_holding(self, key: str, symbol: str, qty: float) -> None:
        pf = self.portfolio(key)
        pf[symbol] = pf.get(symbol, 0) + qty
        self.kv.set(_NS, key, pf)

    def remove_holding(self, key: str, symbol: str, qty: float) -> Result:
        pf = self.portfolio(key)
        have = pf.get(symbol, 0)
        if have < qty:
            return Result.fail(f"持仓不足（{symbol} 你有 {have:g}）")
        pf[symbol] = have - qty
        if pf[symbol] <= 0:
            pf.pop(symbol, None)
        self.kv.set(_NS, key, pf)
        return Result.ok()
