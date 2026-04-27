"""
Akili Markets Trader — FastAPI application entry point.
Systematic. Disciplined. Transparent.

Exchange: Binance Futures (primary) + Deriv (market data)
"""
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.database import init_db
from app.core.redis import close_redis
from app.services.deriv.client import deriv_client
from app.services.deriv.auth import deriv_auth
from app.services.binance.client import binance_client
from app.services.binance.market_data import binance_market_data
from app.services.risk.manager import risk_manager
from app.services.execution.user_trading_engine import user_trading_engine
from app.workers.tick_processor import tick_processor
from app.workers.position_monitor import position_monitor
from app.api.routes import strategies, trading, backtest, performance, risk
from app.api.routes import auth


scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logger.info("  AKILI MARKETS TRADER — Starting up")
    logger.info("  Systematic. Disciplined. Transparent.")
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # Database
    await init_db()
    logger.success("Database initialized")

    # Binance — primary exchange
    try:
        await binance_market_data.init()
    except Exception as e:
        logger.warning(f"Binance market data init warning (Redis may be unavailable): {e}")
    await binance_client.connect()
    balance = await binance_client.get_balance() if binance_client.is_authorized else 1000.0
    await risk_manager.init(balance)
    mode = "TESTNET" if binance_client._testnet else "LIVE"
    logger.success(f"Binance connected [{mode}] — Balance: ${balance:,.2f} USDT")

    # Subscribe flagship: BTCUSDT ticks + 5m candles
    await binance_market_data.subscribe_ticks("BTCUSDT", lambda t: None)
    await binance_market_data.subscribe_candles("BTCUSDT", "M5", lambda c: None)
    logger.success("BTCUSDT live tick + M5 candle stream active")

    # Deriv — market data only (synthetic indices prices, no trading)
    try:
        await deriv_auth.fetch_accounts()
        await deriv_client.connect(use_real=False)
        logger.success(f"Deriv connected — synthetic indices data stream active")
    except Exception as e:
        logger.warning(f"Deriv connection failed (non-critical — Binance is primary): {e}")

    # Load all user trading contexts
    await user_trading_engine.load_all_users()

    # Workers
    await tick_processor.start()
    await position_monitor.start()

    # Scheduler: strategy scan every 60 seconds
    scheduler.add_job(tick_processor.process_strategies, "interval", seconds=60, id="strategy_scan")
    scheduler.start()
    logger.success("Strategy scanner scheduled (60s interval)")

    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logger.info("  AKILI MARKETS TRADER — Ready")
    logger.info(f"  Exchange: Binance Futures [{mode}]")
    logger.info("  Mode: PAPER (live requires qualification)")
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────
    logger.info("Shutting down...")
    scheduler.shutdown()
    await tick_processor.stop()
    await position_monitor.stop()
    await binance_client.disconnect()
    await deriv_client.disconnect()
    await close_redis()
    logger.info("Shutdown complete.")


app = FastAPI(
    title="Akili Markets Trader API",
    description="Systematic algorithmic trading — Binance Futures + Deriv. Systematic. Disciplined. Transparent.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://akili-markets-trader.vercel.app",
        "https://akilimarketstrader.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,        prefix="/api")
app.include_router(strategies.router,  prefix="/api")
app.include_router(trading.router,     prefix="/api")
app.include_router(backtest.router,    prefix="/api")
app.include_router(performance.router, prefix="/api")
app.include_router(risk.router,        prefix="/api")


@app.get("/")
async def root():
    return {
        "name":     "Akili Markets Trader",
        "tagline":  "Systematic. Disciplined. Transparent.",
        "version":  "1.0.0",
        "exchange": "Binance Futures",
        "status":   "running",
        "docs":     "/docs",
    }


@app.get("/health")
async def health():
    return {
        "status":              "healthy",
        "binance_connected":   binance_client.is_connected,
        "binance_authorized":  binance_client.is_authorized,
        "binance_mode":        "testnet" if binance_client._testnet else "live",
        "deriv_connected":     deriv_client.is_connected,
        "mode":                "paper",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
