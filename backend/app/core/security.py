"""
Auth utilities — password hashing, JWT tokens, API key encryption.
API keys are AES-encrypted at rest. Never stored in plaintext.
"""
import base64
from datetime import datetime, timedelta
from typing import Optional
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from jose import jwt, JWTError
from cryptography.fernet import Fernet
from loguru import logger

from app.core.config import settings

_ph = PasswordHasher(time_cost=2, memory_cost=65536, parallelism=2)

def _derive_fernet_key(secret: str) -> bytes:
    import hashlib
    h = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(h)

_fernet = Fernet(_derive_fernet_key(settings.secret_key))

JWT_ALGORITHM  = "HS256"
ACCESS_EXPIRE  = timedelta(hours=8)
REFRESH_EXPIRE = timedelta(days=30)


# ─── Passwords ────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, plain)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


# ─── JWT ─────────────────────────────────────────────────────────────────────

def create_access_token(user_id: str, role: str) -> str:
    expire = datetime.utcnow() + ACCESS_EXPIRE
    return jwt.encode(
        {"sub": user_id, "role": role, "exp": expire, "type": "access"},
        settings.secret_key, algorithm=JWT_ALGORITHM,
    )


def create_refresh_token(user_id: str) -> str:
    expire = datetime.utcnow() + REFRESH_EXPIRE
    return jwt.encode(
        {"sub": user_id, "exp": expire, "type": "refresh"},
        settings.secret_key, algorithm=JWT_ALGORITHM,
    )


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None


# ─── API Key Encryption ───────────────────────────────────────────────────────

def encrypt_api_key(plaintext: str) -> str:
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt_api_key(ciphertext: str) -> str:
    return _fernet.decrypt(ciphertext.encode()).decode()
