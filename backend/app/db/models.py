from __future__ import annotations

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Index, func, ForeignKey
from sqlalchemy.schema import UniqueConstraint
from sqlalchemy.orm import relationship
from app.db.database import Base


# ─────────────────────────────────────────────────────────
# Team: 팀별 문서 격리를 위한 팀 테이블
# ─────────────────────────────────────────────────────────
class Team(Base):
    """
    팀 테이블

    팀별로 문서를 격리하여 질의 시 해당 팀의 문서만 참조하도록 함.
    관리자가 팀을 동적으로 추가/삭제 가능.
    """
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False, unique=True)  # 팀 이름 (예: "인사팀")
    description = Column(String(200), nullable=True)  # 팀 설명
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.sysutcdatetime()
    )

    # 관계: 팀에 소속된 유저들
    users = relationship("User", back_populates="team")


# SQL Server 기본 스키마가 dbo 이므로 별도 schema 지정 불필요
class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username", name="UX_users_username"),
        Index("idx_users_team_id", "team_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)  # 실명
    username = Column(String(50), nullable=False)  # 로그인 아이디(유니크)
    password_hash = Column(String(255), nullable=False)  # bcrypt 등 해시
    security_level = Column(Integer, nullable=False, default=3)  # 1~4
    is_active = Column(Boolean, nullable=False, default=True)

    # 팀 소속 (NULL = 팀 미배정 → 업로드 불가)
    # ON DELETE SET NULL: 팀 삭제 시 유저의 team_id가 NULL로 변경
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.sysutcdatetime()
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=True, onupdate=func.sysutcdatetime()
    )

    # 관계: 소속 팀
    team = relationship("Team", back_populates="users")


class QueryLog(Base):
    """
    사용자 질문 로그 테이블

    FAQ 생성 및 분석을 위해 모든 사용자 질문을 저장합니다.
    임베딩은 별도로 생성하므로 여기서는 질문 텍스트만 저장합니다.
    """
    __tablename__ = "query_logs"
    __table_args__ = (
        Index('idx_query_logs_created_at', 'created_at'),
        Index('idx_query_logs_user_id', 'user_id'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    question = Column(Text, nullable=False)  # 사용자 질문
    answer_id = Column(String(50), nullable=True)  # 답변 ID (선택)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # 사용자 ID (선택)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.sysutcdatetime()
    )
