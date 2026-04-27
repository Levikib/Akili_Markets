"""
Binance Futures WebSocket + REST client.
Handles live price streams, account info, and order execution.
Uses Binance Futures (USDT-margined) for 24/7 trading with leverage control.
Testnet by default — flips to live with explicit flag.
"""
import asyncio
import json
import time
import hmac
import hashlib
from typing import Any, Callable, Optional
from urllib.parse import urlencode
import aiohttp
import websockets
from loguru import logger

from app.core.config import settings


# ─── Instrument Map (Deriv → Binance equivalents) ─────────────────────────────
# V75/Crash/Boom don't exist on Binance — mapped to high-volatility crypto pairs
INSTRUMENT_MAP = {
    # Synthetic → Crypto equivalent (volatility profile match)
    "R_75":      "BTCUSDT",   # High volatility flagship
    "R_100":     "ETHUSDT",   # High volatility
    "R_50":      "BNBUSDT",   # Medium volatility
    "R_25":      "SOLUSDT",   # Lower volatility
    "CRASH300N": "BTCUSDT",   # High momentum moves
    "CRASH500":  "BTCUSDT",
    "CRASH1000": "BTCUSDT",
    "BOOM300N":  "ETHUSDT",
    "BOOM500":   "ETHUSDT",
    "BOOM1000":  "ETHUSDT",
    "stpRNG":    "XRPUSDT",   # Step-like price action
    "JD25":      "SOLUSDT",
    "JD50":      "BNBUSDT",
    "JD75":      "BTCUSDT",
    # Forex → Binance crypto
    "frxEURUSD": "ETHUSDT",
    "frxGBPUSD": "BNBUSDT",
    "frxUSDJPY": "XRPUSDT",
    "frxAUDUSD": "ADAUSDT",
    "frxUSDCHF": "DOTUSDT",
}

# Binance Futures instruments we actively trade
BINANCE_INSTRUMENTS = {
    "BTCUSDT":  "Bitcoin / USDT Perpetual",
    "ETHUSDT":  "Ethereum / USDT Perpetual",
    "BNBUSDT":  "BNB / USDT Perpetual",
    "SOLUSDT":  "Solana / USDT Perpetual",
    "XRPUSDT":  "Ripple / USDT Perpetual",
    "ADAUSDT":  "Cardano / USDT Perpetual",
    "DOTUSDT":  "Polkadot / USDT Perpetual",
    "AVAXUSDT": "Avalanche / USDT Perpetual",
    "LINKUSDT": "Chainlink / USDT Perpetual",
    "MATICUSDT":"Polygon / USDT Perpetual",
}

TIMEFRAME_MAP = {
    "M1":  "1m",
    "M5":  "5m",
    "M15": "15m",
    "H1":  "1h",
    "H4":  "4h",
    "D1":  "1d",
}


class BinanceClient:
    # Testnet URLs
    TESTNET_REST  = "https://testnet.binancefuture.com"
    TESTNET_WS    = "wss://stream.binancefuture.com/ws"
    # Live URLs
    LIVE_REST     = "https://fapi.binance.com"
    LIVE_WS       = "wss://fstream.binance.com/ws"

    def __init__(self):
        self._api_key    = settings.binance_api_key
        self._api_secret = settings.binance_api_secret
        self._testnet    = settings.binance_testnet
        self._rest_base  = self.TESTNET_REST if self._testnet else self.LIVE_REST
        self._ws_base    = self.TESTNET_WS   if self._testnet else self.LIVE_WS

        self._session: Optional[aiohttp.ClientSession] = None
        self._ws_connections: dict[str, websockets.WebSocketClientProtocol] = {}
        self._tick_callbacks: dict[str, list[Callable]] = {}
        self._candle_callbacks: dict[str, list[Callable]] = {}
        self._running = False

        self._balance: float = 0.0
        self._positions: dict[str, dict] = {}
        self._connected = False

    # ─── Lifecycle ───────────────────────────────────────────────────────────

    async def connect(self) -> None:
        self._session = aiohttp.ClientSession(headers={"X-MBX-APIKEY": self._api_key})
        self._running = True
        self._connected = True
        mode = "TESTNET" if self._testnet else "LIVE"
        logger.info(f"Binance Futures client initialized [{mode}]")

        if self._api_key:
            await self._refresh_balance()
            logger.success(
                f"Binance connected — Balance: ${self._balance:,.2f} USDT | Mode: {mode}"
            )
        else:
            logger.warning("Binance running without API keys — market data only")

    async def disconnect(self) -> None:
        self._running = False
        self._connected = False
        for ws in self._ws_connections.values():
            await ws.close()
        if self._session:
            await self._session.close()
        logger.info("Binance client disconnected")

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def is_authorized(self) -> bool:
        return bool(self._api_key and self._api_secret and self._connected)

    @property
    def balance(self) -> float:
        return self._balance

    # ─── Signature (for authenticated endpoints) ──────────────────────────────

    def _sign(self, params: dict) -> dict:
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = 10000
        query = urlencode(params)
        sig = hmac.new(
            self._api_secret.encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        params["signature"] = sig
        return params

    # ─── REST Helpers ────────────────────────────────────────────────────────

    async def _get(self, path: str, params: dict = None, signed: bool = False) -> dict:
        if params is None:
            params = {}
        if signed:
            params = self._sign(params)
        url = f"{self._rest_base}{path}"
        async with self._session.get(url, params=params) as r:
            data = await r.json()
            if r.status >= 400:
                raise BinanceAPIError(data.get("msg", str(data)), data.get("code", r.status))
            return data

    async def _post(self, path: str, params: dict = None, signed: bool = True) -> dict:
        if params is None:
            params = {}
        if signed:
            params = self._sign(params)
        url = f"{self._rest_base}{path}"
        async with self._session.post(url, params=params) as r:
            data = await r.json()
            if r.status >= 400:
                raise BinanceAPIError(data.get("msg", str(data)), data.get("code", r.status))
            return data

    async def _delete(self, path: str, params: dict = None, signed: bool = True) -> dict:
        if params is None:
            params = {}
        if signed:
            params = self._sign(params)
        url = f"{self._rest_base}{path}"
        async with self._session.delete(url, params=params) as r:
            data = await r.json()
            if r.status >= 400:
                raise BinanceAPIError(data.get("msg", str(data)), data.get("code", r.status))
            return data

    # ─── Market Data ─────────────────────────────────────────────────────────

    async def get_candle_history(
        self,
        symbol: str,
        timeframe: str,
        count: int = 500,
    ) -> list[dict]:
        """Fetch historical OHLCV candles. Returns list matching Deriv format."""
        interval = TIMEFRAME_MAP.get(timeframe, "5m")
        raw = await self._get("/fapi/v1/klines", {
            "symbol": symbol,
            "interval": interval,
            "limit": min(count, 1500),
        })
        candles = [
            {
                "epoch":  int(c[0]) // 1000,
                "open":   float(c[1]),
                "high":   float(c[2]),
                "low":    float(c[3]),
                "close":  float(c[4]),
                "volume": float(c[5]),
            }
            for c in raw
        ]
        logger.info(f"Fetched {len(candles)} {timeframe} candles for {symbol}")
        return candles

    async def get_ticker(self, symbol: str) -> dict:
        raw = await self._get("/fapi/v1/ticker/price", {"symbol": symbol})
        return {"symbol": symbol, "price": float(raw["price"]), "epoch": int(time.time())}

    async def get_24h_stats(self, symbol: str) -> dict:
        return await self._get("/fapi/v1/ticker/24hr", {"symbol": symbol})

    async def subscribe_ticks(self, symbol: str, callback: Callable) -> None:
        stream = f"{symbol.lower()}@aggTrade"
        if symbol not in self._tick_callbacks:
            self._tick_callbacks[symbol] = []
        self._tick_callbacks[symbol].append(callback)
        if symbol not in self._ws_connections:
            asyncio.create_task(self._stream_ticks(symbol, stream))
        logger.info(f"Subscribed to ticks: {symbol}")

    async def subscribe_candles(self, symbol: str, timeframe: str, callback: Callable) -> None:
        interval = TIMEFRAME_MAP.get(timeframe, "5m")
        stream = f"{symbol.lower()}@kline_{interval}"
        key = f"{symbol}:{timeframe}"
        if key not in self._candle_callbacks:
            self._candle_callbacks[key] = []
        self._candle_callbacks[key].append(callback)
        if key not in self._ws_connections:
            asyncio.create_task(self._stream_candles(symbol, timeframe, stream))
        logger.info(f"Subscribed to candles: {symbol} {timeframe}")

    async def _stream_ticks(self, symbol: str, stream: str) -> None:
        url = f"{self._ws_base}/{stream}"
        while self._running:
            try:
                async with websockets.connect(url, ping_interval=20) as ws:
                    self._ws_connections[symbol] = ws
                    logger.info(f"Tick stream connected: {symbol}")
                    async for raw in ws:
                        try:
                            msg = json.loads(raw)
                            tick = {
                                "symbol": symbol,
                                "quote":  float(msg.get("p", 0)),
                                "epoch":  int(msg.get("T", 0)) // 1000,
                                "volume": float(msg.get("q", 0)),
                            }
                            for cb in self._tick_callbacks.get(symbol, []):
                                result = cb(tick)
                                if asyncio.iscoroutine(result):
                                    asyncio.create_task(result)
                        except Exception as e:
                            logger.error(f"Tick parse error [{symbol}]: {e}")
            except Exception as e:
                logger.warning(f"Tick stream dropped [{symbol}]: {e}")
                if self._running:
                    await asyncio.sleep(3)

    async def _stream_candles(self, symbol: str, timeframe: str, stream: str) -> None:
        url = f"{self._ws_base}/{stream}"
        key = f"{symbol}:{timeframe}"
        while self._running:
            try:
                async with websockets.connect(url, ping_interval=20) as ws:
                    self._ws_connections[key] = ws
                    logger.info(f"Candle stream connected: {symbol} {timeframe}")
                    async for raw in ws:
                        try:
                            msg = json.loads(raw)
                            k = msg.get("k", {})
                            if k.get("x"):  # only closed candles
                                candle = {
                                    "epoch":  int(k["t"]) // 1000,
                                    "open":   float(k["o"]),
                                    "high":   float(k["h"]),
                                    "low":    float(k["l"]),
                                    "close":  float(k["c"]),
                                    "volume": float(k["v"]),
                                }
                                for cb in self._candle_callbacks.get(key, []):
                                    result = cb(candle)
                                    if asyncio.iscoroutine(result):
                                        asyncio.create_task(result)
                        except Exception as e:
                            logger.error(f"Candle parse error: {e}")
            except Exception as e:
                logger.warning(f"Candle stream dropped [{key}]: {e}")
                if self._running:
                    await asyncio.sleep(3)

    # ─── Account ─────────────────────────────────────────────────────────────

    async def _refresh_balance(self) -> None:
        try:
            data = await self._get("/fapi/v2/balance", signed=True)
            for asset in data:
                if asset.get("asset") == "USDT":
                    self._balance = float(asset.get("availableBalance", 0))
                    break
        except Exception as e:
            logger.warning(f"Balance fetch failed: {e}")

    async def get_balance(self) -> float:
        await self._refresh_balance()
        return self._balance

    async def get_positions(self) -> list[dict]:
        data = await self._get("/fapi/v2/positionRisk", signed=True)
        active = [p for p in data if float(p.get("positionAmt", 0)) != 0]
        return active

    async def get_open_orders(self, symbol: str = None) -> list[dict]:
        params = {}
        if symbol:
            params["symbol"] = symbol
        return await self._get("/fapi/v1/openOrders", params, signed=True)

    # ─── Trading ─────────────────────────────────────────────────────────────

    async def place_order(
        self,
        symbol: str,
        side: str,          # "BUY" or "SELL"
        quantity: float,
        order_type: str = "MARKET",
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        reduce_only: bool = False,
    ) -> dict:
        """Place a Futures market order with optional SL/TP."""
        # Set leverage to 1x by default (safe)
        try:
            await self._post("/fapi/v1/leverage", {
                "symbol": symbol,
                "leverage": 1,
            })
        except Exception:
            pass

        params = {
            "symbol":   symbol,
            "side":     side,
            "type":     order_type,
            "quantity": f"{quantity:.4f}",
        }
        if reduce_only:
            params["reduceOnly"] = "true"

        order = await self._post("/fapi/v1/order", params)
        order_id = order.get("orderId")
        entry_price = float(order.get("avgPrice", 0) or order.get("price", 0))

        logger.success(
            f"Binance ORDER PLACED — {side} {symbol} qty:{quantity} | "
            f"OrderID:{order_id} | Entry:{entry_price}"
        )

        # Place stop loss
        if stop_loss:
            sl_side = "SELL" if side == "BUY" else "BUY"
            try:
                await self._post("/fapi/v1/order", {
                    "symbol":           symbol,
                    "side":             sl_side,
                    "type":             "STOP_MARKET",
                    "stopPrice":        f"{stop_loss:.4f}",
                    "closePosition":    "true",
                    "workingType":      "MARK_PRICE",
                })
                logger.info(f"Stop loss set at {stop_loss}")
            except Exception as e:
                logger.error(f"SL placement failed: {e}")

        # Place take profit
        if take_profit:
            tp_side = "SELL" if side == "BUY" else "BUY"
            try:
                await self._post("/fapi/v1/order", {
                    "symbol":           symbol,
                    "side":             tp_side,
                    "type":             "TAKE_PROFIT_MARKET",
                    "stopPrice":        f"{take_profit:.4f}",
                    "closePosition":    "true",
                    "workingType":      "MARK_PRICE",
                })
                logger.info(f"Take profit set at {take_profit}")
            except Exception as e:
                logger.error(f"TP placement failed: {e}")

        return order

    async def close_position(self, symbol: str, quantity: float, side: str) -> dict:
        close_side = "SELL" if side == "BUY" else "BUY"
        return await self.place_order(symbol, close_side, quantity, reduce_only=True)

    async def cancel_all_orders(self, symbol: str = None) -> dict:
        if symbol:
            return await self._delete("/fapi/v1/allOpenOrders", {"symbol": symbol})
        # Cancel for all tracked instruments
        results = {}
        for sym in BINANCE_INSTRUMENTS:
            try:
                r = await self._delete("/fapi/v1/allOpenOrders", {"symbol": sym})
                results[sym] = r
            except Exception:
                pass
        return results

    async def close_all_positions(self) -> list[dict]:
        positions = await self.get_positions()
        results = []
        for pos in positions:
            sym = pos["symbol"]
            amt = float(pos["positionAmt"])
            side = "SELL" if amt > 0 else "BUY"
            try:
                r = await self.close_position(sym, abs(amt), "BUY" if amt > 0 else "SELL")
                results.append(r)
                logger.info(f"Closed position: {sym} amt:{amt}")
            except Exception as e:
                logger.error(f"Failed to close {sym}: {e}")
        return results

    async def kill_all(self) -> dict:
        """Emergency: cancel all orders and close all positions."""
        await self.cancel_all_orders()
        closed = await self.close_all_positions()
        logger.critical(f"KILL ALL executed — {len(closed)} positions closed")
        return {"positions_closed": len(closed)}

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def to_binance_symbol(self, instrument: str) -> str:
        return INSTRUMENT_MAP.get(instrument, instrument)

    def get_min_quantity(self, symbol: str) -> float:
        minimums = {
            "BTCUSDT": 0.001, "ETHUSDT": 0.001, "BNBUSDT": 0.01,
            "SOLUSDT": 0.1,   "XRPUSDT": 1.0,   "ADAUSDT": 1.0,
            "DOTUSDT": 0.1,   "AVAXUSDT": 0.1,  "LINKUSDT": 0.1,
            "MATICUSDT": 1.0,
        }
        return minimums.get(symbol, 0.01)


# ─── Exceptions ──────────────────────────────────────────────────────────────

class BinanceAPIError(Exception):
    def __init__(self, message: str, code: Any = ""):
        self.code = code
        super().__init__(f"[{code}] {message}")


# ─── Singleton ───────────────────────────────────────────────────────────────

binance_client = BinanceClient()
