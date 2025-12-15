from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from app.models.schemas import AuthUser
from app.db.database import get_db
from app.db import models as m
from app.services.security import (
    verify_password,
    hash_password,
    create_access_token,
    decode_access_token,
)

router = APIRouter()


# ─────────────
# Pydantic 스키마
# ─────────────
class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=128)  # 프론트와 동일 기준

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("이름을 입력하세요.")
        return v.strip()


class LoginIn(BaseModel):
    username: str
    password: str


class MeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    username: str
    security_level: int
    is_active: bool
    team_id: Optional[int] = None
    team_name: Optional[str] = None


class TeamSimple(BaseModel):
    """일반 유저용 팀 정보 (간소화)"""
    id: int
    name: str


# ─────────────
# 유틸
# ─────────────
def _get_user_by_username(db: Session, username: str) -> Optional[m.User]:
    return db.query(m.User).filter(m.User.username == username).first()


def current_user(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> AuthUser:
    # 1) 헤더 확인
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="인증 토큰이 없습니다.")

    # 2) 토큰 파싱 & 검증
    token = authorization.split(" ", 1)[1]
    data = decode_access_token(token)
    if not data or "sub" not in data:
        raise HTTPException(status_code=401, detail="토큰이 유효하지 않습니다.")

    # 3) DB에서 사용자 로드
    user = db.get(m.User, int(data["sub"]))
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    if not getattr(user, "is_active", True):
        raise HTTPException(status_code=403, detail="비활성화된 계정입니다.")

    # 4) AuthUser 스키마로 반환
    #    이메일 검증/인증은 추후 도입 예정이므로, 지금은 없을 수 있음(None 허용)
    email = getattr(user, "email", None) or None
    return AuthUser(
        id=user.id,
        username=user.username,
        email=email,
        security_level=int(getattr(user, "security_level", 3)),
        team_id=user.team_id,
        team_name=user.team.name if user.team else None,
    )


# ─────────────
# API
# ─────────────
@router.post("/register")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    exists = db.query(m.User).filter(m.User.username == body.username).first()
    if exists:
        raise HTTPException(status_code=409, detail="이미 사용 중인 아이디입니다.")

    user = m.User(
        name=body.name,  # validator로 strip 처리됨
        username=body.username,
        password_hash=hash_password(body.password),
        security_level=3,
        is_active=True,
        # email은 현재 선택값(없어도 됨)
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id)
    return {"access_token": token, "token_type": "bearer"}


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = _get_user_by_username(db, body.username)
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다."
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="비활성화된 계정입니다.")

    token = create_access_token(user.id)
    return {"access_token": token, "token_type": "bearer"}


@router.post("/logout")
def logout():
    # 클라이언트 보관 토큰(Bearer)을 무효화할 저장소가 없다면,
    # 단순 ok 반환(프론트에서 토큰 삭제)
    return {"ok": True}


@router.post("/me")
def me(authorization: str = Header(None), db: Session = Depends(get_db)):
    """
    프론트에서 저장한 Bearer 토큰으로 현재 사용자 조회.
    (주의: 이 엔드포인트는 POST 방식으로 쓰고 있음)
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="인증 토큰이 없습니다.")

    token = authorization.split(" ", 1)[1]
    data = decode_access_token(token)
    if not data or "sub" not in data:
        raise HTTPException(status_code=401, detail="토큰이 유효하지 않습니다.")

    user = db.get(m.User, int(data["sub"]))
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    return MeOut(
        id=user.id,
        name=user.name,
        username=user.username,
        security_level=user.security_level,
        is_active=user.is_active,
        team_id=user.team_id,
        team_name=user.team.name if user.team else None,
    )


class MePatch(BaseModel):
    """유저 본인 정보 수정용 스키마"""
    name: Optional[str] = None
    username: Optional[str] = None
    email: Optional[str] = None
    team_id: Optional[int] = None  # 팀 변경 허용


@router.patch("/me")
def update_me(
    body: MePatch,
    authorization: str = Header(None),
    db: Session = Depends(get_db),
):
    """
    현재 로그인 유저 본인 정보 수정.
    - name, username, email, team_id 변경 가능
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="인증 토큰이 없습니다.")

    token = authorization.split(" ", 1)[1]
    data = decode_access_token(token)
    if not data or "sub" not in data:
        raise HTTPException(status_code=401, detail="토큰이 유효하지 않습니다.")

    user = db.get(m.User, int(data["sub"]))
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    # 변경 적용 (명시적으로 전달된 필드만)
    patch_data = body.model_dump(exclude_unset=True)

    if "name" in patch_data and patch_data["name"]:
        user.name = patch_data["name"].strip()
    if "username" in patch_data and patch_data["username"]:
        # 중복 체크
        exists = db.query(m.User).filter(
            m.User.username == patch_data["username"],
            m.User.id != user.id
        ).first()
        if exists:
            raise HTTPException(status_code=409, detail="이미 사용 중인 아이디입니다.")
        user.username = patch_data["username"].strip()
    if "email" in patch_data:
        user.email = patch_data["email"].strip() if patch_data["email"] else None
    if "team_id" in patch_data:
        # team_id 유효성 검사
        if patch_data["team_id"] is not None:
            team = db.get(m.Team, patch_data["team_id"])
            if not team or not team.is_active:
                raise HTTPException(status_code=400, detail="유효하지 않은 팀입니다.")
        user.team_id = patch_data["team_id"]

    db.commit()
    db.refresh(user)

    return MeOut(
        id=user.id,
        name=user.name,
        username=user.username,
        security_level=user.security_level,
        is_active=user.is_active,
        team_id=user.team_id,
        team_name=user.team.name if user.team else None,
    )


@router.get("/check-username")
def check_username(
    username: str = Query(..., min_length=3, max_length=50),
    db: Session = Depends(get_db),
):
    """아이디 사용 가능 여부 조회: { available: true/false }"""
    exists = db.query(m.User).filter(m.User.username == username).first()
    return {"available": exists is None}


@router.get("/teams", response_model=list[TeamSimple])
def list_teams_for_user(
    db: Session = Depends(get_db),
):
    """
    팀 목록 조회 (활성화된 팀만)

    - 질의 페이지에서 답변팀 선택 드롭다운에 사용
    - 로그인 불필요 (비로그인 사용자도 팀 선택 가능)
    """
    # 활성화된 팀만 조회
    teams = db.query(m.Team).filter(m.Team.is_active == True).order_by(m.Team.id).all()

    return [TeamSimple(id=t.id, name=t.name) for t in teams]
