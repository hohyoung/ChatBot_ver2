from __future__ import annotations

from sqlalchemy import Column, Integer, String, Boolean, DateTime, func
from sqlalchemy.schema import UniqueConstraint
from app.db.database import Base


# SQL Server 기본 스키마가 dbo 이므로 별도 schema 지정 불필요
class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("username", name="UX_users_username"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)  # 실명
    username = Column(String(50), nullable=False)  # 로그인 아이디(유니크)
    password_hash = Column(String(255), nullable=False)  # bcrypt 등 해시
    security_level = Column(Integer, nullable=False, default=3)  # 1~4
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.sysutcdatetime()
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=True, onupdate=func.sysutcdatetime()
    )
