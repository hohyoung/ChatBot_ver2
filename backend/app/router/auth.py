from __future__ import annotations
from fastapi import APIRouter, HTTPException, status
from app.models.schemas import LoginRequest, LoginResponse
from app.services.auth import authenticate, create_access_token
from app.config import settings

router = APIRouter()


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    user = authenticate(body)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    token = create_access_token(user.user_id, expires_in=settings.jwt_expires_in)
    return LoginResponse(access_token=token, expires_in=settings.jwt_expires_in)
