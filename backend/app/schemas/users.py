from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime
from app.models.users import UserRole


class UserRegister(BaseModel):
    email:     EmailStr
    password:  str = Field(..., min_length=8)
    full_name: str = Field(..., min_length=2)


class UserLogin(BaseModel):
    email:    EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token:  str
    refresh_token: str
    token_type:    str = "bearer"
    user_id:       str
    role:          UserRole


class UserResponse(BaseModel):
    id:          str
    email:       str
    full_name:   str
    role:        UserRole
    is_active:   bool
    is_verified: bool
    created_at:  datetime
    last_login:  Optional[datetime]

    class Config:
        from_attributes = True


class ExchangeKeyCreate(BaseModel):
    exchange:   str = "binance"
    api_key:    str
    api_secret: str
    is_testnet: bool = False
    label:      Optional[str] = "Main Account"


class ExchangeKeyResponse(BaseModel):
    id:         str
    exchange:   str
    label:      Optional[str]
    is_testnet: bool
    is_active:  bool
    created_at: datetime
    api_key_preview: str  # first 8 + last 4 chars only

    class Config:
        from_attributes = True


class UserSettingsUpdate(BaseModel):
    max_risk_per_trade_pct: Optional[float] = Field(default=None, gt=0, le=2.0)
    max_daily_loss_pct:     Optional[float] = Field(default=None, gt=0, le=10.0)
    paper_balance:          Optional[float] = Field(default=None, gt=0)
    default_timeframe:      Optional[str]   = None
    notifications_enabled:  Optional[bool]  = None


class AdminUserView(BaseModel):
    id:          str
    email:       str
    full_name:   str
    role:        UserRole
    is_active:   bool
    created_at:  datetime
    last_login:  Optional[datetime]
    has_exchange_keys: bool
    total_trades: int = 0

    class Config:
        from_attributes = True
