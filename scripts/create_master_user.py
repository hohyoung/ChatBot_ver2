#!/usr/bin/env python3
from __future__ import annotations
import os
import sys
from pathlib import Path

# ========= 0) 외부 DB URL "하드코딩" =========
# ※ 반드시 실제 비밀번호로 교체하세요.
os.environ["DATABASE_URL"] = (
    "mssql+pyodbc://soosan_chatbot_svc:chatBot2025!@192.68.10.249:1433/"
    "ChatBot?driver=ODBC+Driver+17+for+SQL+Server&Encrypt=no&TrustServerCertificate=yes"
)

# ========= 1) import path 세팅 =========
ROOT = (
    Path(__file__).resolve().parents[1]
)  # repo 루트 추정: scripts/ 상위 상위가 backend 루트라면 조정
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# ========= 2) 백엔드 모듈 재사용(엔진/세션/모델/보안) =========
from app.db.database import SessionLocal, engine, Base  # type: ignore  # env DATABASE_URL 사용
from app.db import models as m  # type: ignore
from app.services.security import hash_password  # type: ignore

# ========= 3) 하드코딩할 관리자 정보 =========
ADMIN_NAME = "시스템 관리자"
ADMIN_USERNAME = "admin0702"
ADMIN_PASSWORD = "soosan1029!"  # ← 필요시 변경
ADMIN_EMAIL = "admin0702@soosan.co.kr"  # 선택


# ========= 4) 유틸: password 컬럼명 호환 =========
def set_user_password(user_obj, hashed: str) -> None:
    """
    프로젝트에 따라 컬럼명이 'password_hashed' 또는 'password_hash'일 수 있어
    둘 다 지원.
    """
    if hasattr(user_obj, "password_hashed"):
        setattr(user_obj, "password_hashed", hashed)
    elif hasattr(user_obj, "password_hash"):
        setattr(user_obj, "password_hash", hashed)
    else:
        raise RuntimeError(
            "User 모델에 password 필드가 없습니다. ('password_hashed' 또는 'password_hash')"
        )


def main() -> None:
    # 1) 테이블 보장 (모델이 선언된 경우에만 동작)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # 2) 기존 사용자 조회
        user = db.query(m.User).filter(m.User.username == ADMIN_USERNAME).first()

        if user:
            # 존재하면 비번/보안등급/활성 업데이트
            set_user_password(user, hash_password(ADMIN_PASSWORD))
            # SecurityLevel enum이 있으면 사용, 없다면 1을 MAINTAINER로 가정
            try:
                user.security_level = int(m.SecurityLevel.MASTER)
            except Exception:
                user.security_level = 1
            if hasattr(user, "name") and not getattr(user, "name"):
                setattr(user, "name", ADMIN_NAME)
            if hasattr(user, "email") and not getattr(user, "email"):
                setattr(user, "email", ADMIN_EMAIL)
            if hasattr(user, "is_active"):
                user.is_active = True
            db.commit()
            print(f"[OK] Updated existing admin '{ADMIN_USERNAME}'")
        else:
            # 신규 생성
            kwargs = {}
            if hasattr(m.User, "name"):
                kwargs["name"] = ADMIN_NAME
            if hasattr(m.User, "email"):
                kwargs["email"] = ADMIN_EMAIL
            if hasattr(m.User, "is_active"):
                kwargs["is_active"] = True
            # security_level 설정
            try:
                sec_val = int(m.SecurityLevel.MASTER)
            except Exception:
                sec_val = 1
            kwargs["security_level"] = sec_val

            user = m.User(username=ADMIN_USERNAME, **kwargs)
            set_user_password(user, hash_password(ADMIN_PASSWORD))

            db.add(user)
            db.commit()
            db.refresh(user)
            print(
                f"[OK] Created admin '{ADMIN_USERNAME}' (id={getattr(user, 'id', '?')})"
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
