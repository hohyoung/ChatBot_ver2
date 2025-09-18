from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from jose import jwt, JWTError
from passlib.context import CryptContext

from app.config import settings  # settings.jwt_secret, settings.jwt_exp_minutes

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _pwd.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _pwd.verify(plain, hashed)
    except Exception:
        return False


def create_access_token(sub: str | int, expires_minutes: int | None = None) -> str:
    now = datetime.now(timezone.utc)
    exp_mins = expires_minutes or getattr(settings, "jwt_exp_minutes", 60 * 24)
    payload = {
        "sub": str(sub),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=exp_mins)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        data = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        # sub를 정수처럼 다루고 싶다면 보정
        sub = data.get("sub")
        if isinstance(sub, str) and sub.isdigit():
            data["sub"] = int(sub)
        return data
    except JWTError:
        return None


def has_upload_permission(level: int) -> bool:
    # 1=MASTER, 2=EXEC, 3=STAFF 허용 / 4=EXTERNAL 불가
    return level in (1, 2, 3)
