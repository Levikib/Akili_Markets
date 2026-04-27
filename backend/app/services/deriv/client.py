"""
Deriv WebSocket connection manager — new api.derivws.com auth flow.
OTP-authenticated WebSocket. Auto-reconnects with fresh OTP on disconnect.
"""
import asyncio
import json
from typing import Any, Callable, Optional
import websockets
from websockets.exceptions import ConnectionClosed
from loguru import logger

from app.services.deriv.auth import deriv_auth


class DerivClient:
    PING_INTERVAL = 25
    RECONNECT_DELAY = 5

    def __init__(self):
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._authorized = True  # OTP auth means we're always authorized on connect
        self._req_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._subscriptions: dict[str, list[Callable]] = {}
        self._on_tick_callbacks: list[Callable] = []
        self._connected = False
        self._running = False
        self._use_real = False
        self._listener_task: Optional[asyncio.Task] = None
        self._ping_task: Optional[asyncio.Task] = None
        self._balance: float = 0.0
        self._currency: str = "USD"
        self._account_id: str = ""

    # ─── Connection ──────────────────────────────────────────────────────────

    async def connect(self, use_real: bool = False) -> None:
        self._running = True
        self._use_real = use_real
        await self._connect_once()

    async def _connect_once(self) -> None:
        try:
            ws_url = await deriv_auth.get_ws_url(use_real=self._use_real)
            logger.info(f"Connecting to Deriv WS ({'REAL' if self._use_real else 'DEMO'})...")
            self._ws = await websockets.connect(
                ws_url,
                ping_interval=None,
                ping_timeout=10,
                close_timeout=10,
            )
            self._connected = True
            self._authorized = True
            self._account_id = deriv_auth.real_account_id if self._use_real else deriv_auth.demo_account_id
            self._balance = deriv_auth.demo_balance if not self._use_real else 0.0
            self._listener_task = asyncio.create_task(self._listen())
            self._ping_task = asyncio.create_task(self._ping_loop())

            # Fetch real balance immediately
            bal = await self.request({"balance": 1})
            self._balance = float(bal.get("balance", {}).get("balance", self._balance))
            self._currency = bal.get("balance", {}).get("currency", "USD")

            logger.success(
                f"Deriv WS connected — Account: {self._account_id} | "
                f"Balance: {self._balance} {self._currency} | "
                f"Mode: {'REAL' if self._use_real else 'DEMO'}"
            )
        except Exception as e:
            logger.error(f"Deriv connection failed: {e}")
            self._connected = False
            if self._running:
                asyncio.create_task(self._reconnect())

    async def _reconnect(self) -> None:
        await asyncio.sleep(self.RECONNECT_DELAY)
        if self._running:
            logger.info("Reconnecting to Deriv...")
            # Cancel old tasks
            if self._listener_task:
                self._listener_task.cancel()
            if self._ping_task:
                self._ping_task.cancel()
            await self._connect_once()

    async def disconnect(self) -> None:
        self._running = False
        self._connected = False
        if self._ping_task:
            self._ping_task.cancel()
        if self._listener_task:
            self._listener_task.cancel()
        if self._ws:
            await self._ws.close()
        logger.info("Disconnected from Deriv")

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def is_authorized(self) -> bool:
        return self._authorized and self._connected

    @property
    def balance(self) -> float:
        return self._balance

    @property
    def currency(self) -> str:
        return self._currency

    # ─── Message Loop ────────────────────────────────────────────────────────

    async def _listen(self) -> None:
        try:
            async for raw in self._ws:
                try:
                    msg = json.loads(raw)
                    await self._dispatch(msg)
                except json.JSONDecodeError:
                    logger.warning(f"Bad JSON: {raw[:100]}")
                except Exception as e:
                    logger.error(f"Dispatch error: {e}")
        except ConnectionClosed as e:
            logger.warning(f"WS closed: {e}")
            self._connected = False
            self._authorized = False
            if self._running:
                asyncio.create_task(self._reconnect())
        except Exception as e:
            logger.error(f"Listener error: {e}")
            self._connected = False
            if self._running:
                asyncio.create_task(self._reconnect())

    async def _dispatch(self, msg: dict) -> None:
        req_id = msg.get("req_id")
        msg_type = msg.get("msg_type")

        if "error" in msg:
            err = msg["error"]
            logger.error(f"Deriv error [{msg_type}]: {err.get('message')} ({err.get('code')})")
            if req_id and req_id in self._pending:
                self._pending.pop(req_id).set_exception(
                    DerivAPIError(err.get("message", ""), err.get("code", ""))
                )
            return

        if req_id and req_id in self._pending:
            fut = self._pending.pop(req_id)
            if not fut.done():
                fut.set_result(msg)

        if msg_type == "tick":
            tick = msg.get("tick", {})
            for cb in self._on_tick_callbacks:
                result = cb(tick)
                if asyncio.iscoroutine(result):
                    asyncio.create_task(result)

        elif msg_type == "ohlc":
            candle = msg.get("ohlc", {})
            channel = f"candles:{candle.get('symbol')}:{candle.get('granularity')}"
            for cb in self._subscriptions.get(channel, []):
                result = cb(candle)
                if asyncio.iscoroutine(result):
                    asyncio.create_task(result)

        elif msg_type == "balance":
            b = msg.get("balance", {})
            self._balance = float(b.get("balance", self._balance))
            self._currency = b.get("currency", self._currency)

        elif msg_type == "proposal_open_contract":
            poc = msg.get("proposal_open_contract", {})
            channel = f"poc:{poc.get('contract_id')}"
            for cb in self._subscriptions.get(channel, []):
                result = cb(poc)
                if asyncio.iscoroutine(result):
                    asyncio.create_task(result)

    async def _ping_loop(self) -> None:
        while self._connected:
            await asyncio.sleep(self.PING_INTERVAL)
            try:
                await self._send({"ping": 1})
            except Exception:
                break

    # ─── Core Send/Request ───────────────────────────────────────────────────

    async def _send(self, payload: dict) -> int:
        self._req_id += 1
        payload["req_id"] = self._req_id
        await self._ws.send(json.dumps(payload))
        return self._req_id

    async def request(self, payload: dict, timeout: float = 15.0) -> dict:
        if not self._connected:
            raise DerivNotConnectedError("Not connected")
        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()
        req_id = await self._send(payload)
        self._pending[req_id] = fut
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise DerivTimeoutError(f"Request timed out: {payload}")

    # ─── Market Data ─────────────────────────────────────────────────────────

    async def subscribe_ticks(self, symbol: str, callback: Callable) -> None:
        self._on_tick_callbacks.append(callback)
        await self.request({"ticks": symbol, "subscribe": 1})
        logger.info(f"Subscribed to ticks: {symbol}")

    async def subscribe_candles(self, symbol: str, granularity: int, callback: Callable) -> None:
        channel = f"candles:{symbol}:{granularity}"
        if channel not in self._subscriptions:
            self._subscriptions[channel] = []
        self._subscriptions[channel].append(callback)
        await self.request({
            "ticks_history": symbol,
            "end": "latest",
            "count": 1,
            "granularity": granularity,
            "style": "candles",
            "subscribe": 1,
        })

    async def get_candle_history(self, symbol: str, granularity: int, count: int = 500) -> list[dict]:
        resp = await self.request({
            "ticks_history": symbol,
            "end": "latest",
            "count": count,
            "granularity": granularity,
            "style": "candles",
        }, timeout=30.0)
        candles = resp.get("candles", [])
        logger.info(f"Fetched {len(candles)} candles: {symbol} @ {granularity}s")
        return candles

    async def get_tick_history(self, symbol: str, count: int = 5000) -> list[dict]:
        resp = await self.request({
            "ticks_history": symbol,
            "end": "latest",
            "count": count,
            "style": "ticks",
        }, timeout=30.0)
        history = resp.get("history", {})
        prices = history.get("prices", [])
        times = history.get("times", [])
        return [{"epoch": t, "price": p} for t, p in zip(times, prices)]

    async def get_active_symbols(self) -> list[dict]:
        resp = await self.request({"active_symbols": "brief", "product_type": "basic"})
        return resp.get("active_symbols", [])

    async def get_balance(self) -> dict:
        resp = await self.request({"balance": 1})
        b = resp.get("balance", {})
        self._balance = float(b.get("balance", self._balance))
        return b

    # ─── Trading ─────────────────────────────────────────────────────────────

    async def buy_contract(
        self,
        contract_type: str,
        symbol: str,
        duration: int,
        duration_unit: str,
        amount: float,
        basis: str = "stake",
    ) -> dict:
        proposal = await self.request({
            "proposal": 1,
            "contract_type": contract_type,
            "symbol": symbol,
            "duration": duration,
            "duration_unit": duration_unit,
            "amount": amount,
            "basis": basis,
            "currency": self._currency,
        })
        p = proposal.get("proposal", {})
        buy = await self.request({"buy": p.get("id"), "price": p.get("ask_price", amount)})
        return buy.get("buy", {})

    async def sell_contract(self, contract_id: int, price: float = 0) -> dict:
        resp = await self.request({"sell": contract_id, "price": price})
        return resp.get("sell", {})

    async def get_open_contracts(self) -> list[dict]:
        resp = await self.request({"portfolio": 1})
        return resp.get("portfolio", {}).get("contracts", [])

    async def cancel_contract(self, contract_id: int) -> dict:
        resp = await self.request({"cancel": contract_id})
        return resp.get("cancel", {})


# ─── Exceptions ──────────────────────────────────────────────────────────────

class DerivAPIError(Exception):
    def __init__(self, message: str, code: str = ""):
        self.code = code
        super().__init__(f"[{code}] {message}")


class DerivNotConnectedError(Exception):
    pass


class DerivTimeoutError(Exception):
    pass


deriv_client = DerivClient()
