import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Boolean, DateTime, Text, Float, ForeignKey, Enum as SAEnum, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum
from app.core.database import Base


def gen_uuid():
    return str(uuid.uuid4())


class UserRole(str, enum.Enum):
    ADMIN  = "admin"   # full access, sees all users
    TRADER = "trader"  # trades their own account
    VIEWER = "viewer"  # read-only, no trading


class User(Base):
    __tablename__ = "users"

    id:             Mapped[str]            = mapped_column(String(36), primary_key=True, default=gen_uuid)
    email:          Mapped[str]            = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password:Mapped[str]            = mapped_column(String(255), nullable=False)
    full_name:      Mapped[str]            = mapped_column(String(100), nullable=False)
    role:           Mapped[UserRole]       = mapped_column(SAEnum(UserRole), nullable=False, default=UserRole.TRADER)
    is_active:      Mapped[bool]           = mapped_column(Boolean, default=True)
    is_verified:    Mapped[bool]           = mapped_column(Boolean, default=False)
    created_at:     Mapped[datetime]       = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login:     Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    exchange_keys:  Mapped[list["UserExchangeKey"]] = relationship("UserExchangeKey", back_populates="user", cascade="all, delete-orphan")
    settings:       Mapped[Optional["UserSettings"]] = relationship("UserSettings", back_populates="user", uselist=False, cascade="all, delete-orphan")


class UserExchangeKey(Base):
    __tablename__ = "user_exchange_keys"

    id:             Mapped[str]  = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id:        Mapped[str]  = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    exchange:       Mapped[str]  = mapped_column(String(20), nullable=False, default="binance")
    api_key:        Mapped[str]  = mapped_column(Text, nullable=False)         # encrypted at rest
    api_secret:     Mapped[str]  = mapped_column(Text, nullable=False)         # encrypted at rest
    is_testnet:     Mapped[bool] = mapped_column(Boolean, default=True)
    is_active:      Mapped[bool] = mapped_column(Boolean, default=True)
    label:          Mapped[Optional[str]] = mapped_column(String(50))          # e.g. "Main Account"
    created_at:     Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user:           Mapped["User"] = relationship("User", back_populates="exchange_keys")


class UserSettings(Base):
    __tablename__ = "user_settings"

    id:                     Mapped[str]   = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id:                Mapped[str]   = mapped_column(String(36), ForeignKey("users.id"), unique=True, nullable=False)
    max_risk_per_trade_pct: Mapped[float] = mapped_column(Float, default=1.5)   # max 2%
    max_daily_loss_pct:     Mapped[float] = mapped_column(Float, default=5.0)
    paper_balance:          Mapped[float] = mapped_column(Float, default=1000.0)
    default_timeframe:      Mapped[str]   = mapped_column(String(5), default="M5")
    notifications_enabled:  Mapped[bool]  = mapped_column(Boolean, default=True)
    updated_at:             Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user:                   Mapped["User"] = relationship("User", back_populates="settings")
