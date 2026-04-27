"""
Auth routes — register, login, refresh, user management, exchange key management.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from datetime import datetime
from loguru import logger

from app.core.database import get_db
from app.core.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token,
    encrypt_api_key, decrypt_api_key,
)
from app.models.users import User, UserExchangeKey, UserSettings, UserRole
from app.schemas.users import (
    UserRegister, UserLogin, TokenResponse, UserResponse,
    ExchangeKeyCreate, ExchangeKeyResponse, UserSettingsUpdate, AdminUserView,
)
from app.services.binance.client import BinanceClient

router   = APIRouter(prefix="/auth", tags=["Auth"])
security = HTTPBearer()


# ─── Dependency: current user from JWT ───────────────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_token(credentials.credentials)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = await db.get(User, payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# ─── Register ────────────────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(payload: UserRegister, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    # First user ever becomes admin automatically
    count = await db.execute(select(User))
    is_first = len(count.scalars().all()) == 0
    role = UserRole.ADMIN if is_first else UserRole.TRADER

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=role,
        is_verified=is_first,  # first user auto-verified
    )
    db.add(user)
    await db.flush()

    # Create default settings
    user_settings = UserSettings(user_id=user.id)
    db.add(user_settings)
    await db.flush()

    logger.info(f"New user registered: {user.email} [{role}]")
    return TokenResponse(
        access_token=create_access_token(user.id, role),
        refresh_token=create_refresh_token(user.id),
        user_id=user.id,
        role=role,
    )


# ─── Login ───────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
async def login(payload: UserLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account deactivated")

    user.last_login = datetime.utcnow()
    await db.flush()

    logger.info(f"User logged in: {user.email}")
    return TokenResponse(
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(user.id),
        user_id=user.id,
        role=user.role,
    )


# ─── Refresh Token ────────────────────────────────────────────────────────────

@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
):
    payload = decode_token(credentials.credentials)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    user = await db.get(User, payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")
    return TokenResponse(
        access_token=create_access_token(user.id, user.role),
        refresh_token=create_refresh_token(user.id),
        user_id=user.id,
        role=user.role,
    )


# ─── Me ──────────────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    return user


# ─── Exchange Keys ────────────────────────────────────────────────────────────

@router.post("/keys", response_model=ExchangeKeyResponse, status_code=201)
async def add_exchange_key(
    payload: ExchangeKeyCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Validate keys work before saving
    import aiohttp
    test_client = BinanceClient()
    test_client._api_key    = payload.api_key
    test_client._api_secret = payload.api_secret
    test_client._testnet    = payload.is_testnet
    test_client._rest_base  = test_client.TESTNET_REST if payload.is_testnet else test_client.LIVE_REST
    test_client._session    = aiohttp.ClientSession(headers={"X-MBX-APIKEY": payload.api_key})

    try:
        balance_data = await test_client._get("/fapi/v2/balance", signed=True)
        usdt = next((a for a in balance_data if a.get("asset") == "USDT"), None)
        balance = float(usdt["availableBalance"]) if usdt else 0.0
    except Exception as e:
        await test_client._session.close()
        raise HTTPException(status_code=400, detail=f"API keys invalid or Futures not enabled: {e}")
    finally:
        await test_client._session.close()

    key = UserExchangeKey(
        user_id=user.id,
        exchange=payload.exchange,
        api_key=encrypt_api_key(payload.api_key),
        api_secret=encrypt_api_key(payload.api_secret),
        is_testnet=payload.is_testnet,
        label=payload.label,
    )
    db.add(key)
    await db.flush()
    await db.refresh(key)

    logger.info(f"Exchange key added for {user.email} — balance: ${balance:,.2f} USDT")
    return ExchangeKeyResponse(
        id=key.id,
        exchange=key.exchange,
        label=key.label,
        is_testnet=key.is_testnet,
        is_active=key.is_active,
        created_at=key.created_at,
        api_key_preview=f"{payload.api_key[:8]}...{payload.api_key[-4:]}",
    )


@router.get("/keys", response_model=list[ExchangeKeyResponse])
async def list_exchange_keys(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserExchangeKey).where(UserExchangeKey.user_id == user.id)
    )
    keys = result.scalars().all()
    return [
        ExchangeKeyResponse(
            id=k.id,
            exchange=k.exchange,
            label=k.label,
            is_testnet=k.is_testnet,
            is_active=k.is_active,
            created_at=k.created_at,
            api_key_preview=f"{decrypt_api_key(k.api_key)[:8]}...{decrypt_api_key(k.api_key)[-4:]}",
        )
        for k in keys
    ]


@router.delete("/keys/{key_id}")
async def delete_exchange_key(
    key_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    key = await db.get(UserExchangeKey, key_id)
    if not key or key.user_id != user.id:
        raise HTTPException(status_code=404, detail="Key not found")
    await db.delete(key)
    return {"message": "Key deleted"}


# ─── Settings ─────────────────────────────────────────────────────────────────

@router.put("/settings", response_model=dict)
async def update_settings(
    payload: UserSettingsUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == user.id)
    )
    s = result.scalar_one_or_none()
    if not s:
        s = UserSettings(user_id=user.id)
        db.add(s)
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(s, field, value)
    await db.flush()
    return {"message": "Settings updated"}


# ─── Admin: all users ─────────────────────────────────────────────────────────

@router.get("/admin/users", response_model=list[AdminUserView])
async def list_all_users(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).order_by(User.created_at))
    users = result.scalars().all()
    out = []
    for u in users:
        keys_result = await db.execute(
            select(UserExchangeKey).where(UserExchangeKey.user_id == u.id)
        )
        has_keys = len(keys_result.scalars().all()) > 0
        out.append(AdminUserView(
            id=u.id, email=u.email, full_name=u.full_name,
            role=u.role, is_active=u.is_active,
            created_at=u.created_at, last_login=u.last_login,
            has_exchange_keys=has_keys,
        ))
    return out


@router.put("/admin/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    role: UserRole,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.role = role
    await db.flush()
    return {"message": f"Role updated to {role}"}


@router.put("/admin/users/{user_id}/deactivate")
async def deactivate_user(
    user_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = False
    await db.flush()
    return {"message": "User deactivated"}
