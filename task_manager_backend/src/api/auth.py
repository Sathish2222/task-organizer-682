import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext

from src.api.db import fetch_one

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_bearer = HTTPBearer(auto_error=False)


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable {name}. "
            f"Please set it in the backend container .env."
        )
    return value


# PUBLIC_INTERFACE
def hash_password(password: str) -> str:
    """Hash a plaintext password."""
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _pwd_context.verify(password, password_hash)


# PUBLIC_INTERFACE
def create_access_token(*, user_id: UUID, email: str, expires_minutes: int) -> str:
    """Create a JWT access token.

    Args:
        user_id: Authenticated user UUID.
        email: User email for convenience/debugging.
        expires_minutes: Token lifetime (minutes).

    Returns:
        Encoded JWT string.
    """
    secret = _required_env("JWT_SECRET")
    now = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {
        "sub": str(user_id),
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=expires_minutes)).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


# PUBLIC_INTERFACE
def decode_access_token(token: str) -> Dict[str, Any]:
    """Decode and validate a JWT access token.

    Raises HTTPException(401) if invalid/expired.
    """
    secret = _required_env("JWT_SECRET")
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        ) from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        ) from exc


# PUBLIC_INTERFACE
def get_current_user(creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer)) -> Dict[str, Any]:
    """FastAPI dependency to resolve the current user from Authorization: Bearer <token>."""
    if creds is None or not creds.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    payload = decode_access_token(creds.credentials)
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    user = fetch_one("SELECT id, email FROM users WHERE id = %s", (sub,))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return user
