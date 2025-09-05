from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings
from app.models.schemas import LoginRequest, LoginResponse, UserPublic

# OAuth2 파서 (Swagger용 tokenUrl, 실제로는 JSON 로그인 사용)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

ALGORITHM = "HS256"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 개발용 인메모리 유저 (운영에서는 DB로 대체)
_DEV_EMAIL = "admin@local"
_DEV_PASS = "admin1234"
_DEV_HASH = pwd_context.hash(_DEV_PASS)
_DEV_USER = UserPublic(user_id="u_dev_admin", email=_DEV_EMAIL)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(subject: str, *, expires_in: int) -> str:
    now = datetime.now(timezone.utc)
    to_encode = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
    }
    if not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET is not set")
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=ALGORITHM)


def authenticate(req: LoginRequest) -> Optional[UserPublic]:
    # 개발 단계: 딱 한 명만 허용
    if req.email.strip().lower() == _DEV_EMAIL and verify_password(
        req.password, _DEV_HASH
    ):
        return _DEV_USER
    return None


async def get_current_user(token: str = Depends(oauth2_scheme)) -> UserPublic:
    cred_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
    )
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        if not sub:
            raise cred_exc
        # 개발 단계: 토큰 subject가 dev 유저이면 OK
        if sub == _DEV_USER.user_id:
            return _DEV_USER
        # (운영 전환 시: DB에서 사용자 조회)
        raise cred_exc
    except JWTError:
        raise cred_exc


def decode_token_subject(token: str) -> Optional[str]:
    """토큰에서 subject(user_id)를 꺼내 반환. 유효하지 않으면 None."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
        return payload.get("sub")
    except Exception:
        return None


def try_validate_bearer(authorization: Optional[str]) -> Optional[UserPublic]:
    """
    'Authorization: Bearer <JWT>' 헤더를 선택적으로 검증.
    유효하면 UserPublic, 없거나 유효하지 않으면 None.
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    sub = decode_token_subject(token)
    if not sub:
        return None
    # 개발 단계: 데모 유저만 허용
    if sub == _DEV_USER.user_id:
        return _DEV_USER
    return None
