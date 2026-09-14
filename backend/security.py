"""Password hashing and JWT issuing/verification for sessions and one-time
email links (verify-email, reset-password)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from . import config

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return _pwd_context.verify(password, hashed)


def _create_token(subject: int, purpose: str, minutes: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(subject), "purpose": purpose, "iat": now, "exp": now + timedelta(minutes=minutes)}
    return jwt.encode(payload, config.SECRET_KEY, algorithm="HS256")


def create_access_token(user_id: int) -> str:
    return _create_token(user_id, "access", config.ACCESS_TOKEN_EXPIRE_MINUTES)


def create_email_token(user_id: int, purpose: str) -> str:
    return _create_token(user_id, purpose, config.EMAIL_TOKEN_EXPIRE_MINUTES)


def decode_token(token: str, expected_purpose: str) -> int | None:
    """Return the user id encoded in `token` if valid and matching `expected_purpose`."""
    try:
        payload = jwt.decode(token, config.SECRET_KEY, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    if payload.get("purpose") != expected_purpose:
        return None
    try:
        return int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        return None
