from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    # App
    environment: str = "development"
    secret_key: str = "change-me"
    log_level: str = "INFO"

    # Database
    database_url: str
    database_url_sync: str

    # Redis
    redis_url: str

    # Deriv (kept for market data — trading migrated to Binance)
    deriv_app_id: str = "1089"
    deriv_api_token: str = ""
    deriv_ws_url: str = "wss://ws.binaryws.com/websockets/v3"

    # Binance
    binance_api_key: str = ""
    binance_api_secret: str = ""
    binance_testnet: bool = True  # testnet by default — safe

    # Groq AI
    groq_api_key: str
    groq_model: str = "llama-3.3-70b-versatile"

    # Risk limits (hard ceiling — enforced in code, not configurable at runtime)
    max_risk_per_trade_pct: float = Field(default=1.5, le=2.0)
    max_daily_loss_pct: float = Field(default=5.0, le=10.0)
    max_drawdown_pct: float = Field(default=15.0, le=25.0)
    paper_mode_default: bool = True

    # Trading engine
    max_concurrent_positions: int = 5
    stop_loss_cooldown_minutes: int = 15
    min_rr_ratio: float = 1.5
    warn_rr_ratio: float = 2.0

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
