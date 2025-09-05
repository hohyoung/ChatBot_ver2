from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Literal, Optional, Union, Annotated
import re

from pydantic import BaseModel, Field, field_validator

# -------------------------------------------------------------------
# 공통 상수/유틸
# -------------------------------------------------------------------

SCHEMA_VERSION = "v1"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_tag(t: str) -> str:
    # 공백/언더스코어 -> 하이픈, 소문자, 비허용문자 제거, 연속 하이픈 축약
    t = t.strip().lower().replace("_", "-")
    t = re.sub(r"\s+", "-", t)
    t = re.sub(r"[^a-z0-9\-]", "-", t)
    t = re.sub(r"-{2,}", "-", t)
    return t.strip("-")


class StrictModel(BaseModel):
    """스키마 계약 엄수: 정의되지 않은 필드가 들어오면 에러."""

    model_config = {
        "extra": "forbid",
        "populate_by_name": True,
        "str_strip_whitespace": True,
        "use_enum_values": True,
    }


# -------------------------------------------------------------------
# 핵심 도메인: Chunk (벡터DB 메타)
# -------------------------------------------------------------------


class Chunk(StrictModel):
    schema_version: Literal[SCHEMA_VERSION] = Field(default=SCHEMA_VERSION)
    doc_id: str
    chunk_id: str
    doc_type: str  # 예: "policy-manual" | "hr-guideline"
    doc_title: Optional[str] = None
    section_title: Optional[str] = None
    page: Optional[int] = None

    tags: List[str] = Field(default_factory=list)  # kebab-case
    content: str

    source_url: Optional[str] = None
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)
    embedding_version: str = "v1"

    feedback_score: float = 0.0  # 전역 누적(집계 테이블로 관리)
    usage_count: int = 0
    visibility: Literal["public", "org", "private"] = "org"

    @field_validator("tags", mode="before")
    @classmethod
    def _ensure_tags(cls, v):
        if v is None:
            return []
        # 문자열 하나가 오면 분리하지 않고 단일 태그로 취급
        if isinstance(v, str):
            v = [v]
        out, seen = [], set()
        for t in v:
            nt = _normalize_tag(str(t))
            if not nt or nt in seen:
                continue
            seen.add(nt)
            out.append(nt)
        return out


# 검색/재랭크 단계에서 내부적으로 쓰기 좋은 점수 래퍼
class ScoredChunk(StrictModel):
    chunk: Chunk
    similarity: float = 0.0
    feedback_boost: float = 0.0
    tag_overlap: float = 0.0
    final_score: float = 0.0


# -------------------------------------------------------------------
# WebSocket 채팅 이벤트 (문자열 IN, JSON OUT)
# -------------------------------------------------------------------


class ChatTokenData(StrictModel):
    text: str


class ChatTokenEvent(StrictModel):
    type: Literal["token"] = "token"
    data: ChatTokenData


class ChatFinalData(StrictModel):
    answer: str
    chunks: List[Chunk]
    answer_id: str
    used_tags: List[str] = Field(default_factory=list)
    latency_ms: int

    @field_validator("used_tags", mode="before")
    @classmethod
    def _normalize_used_tags(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            v = [v]
        return [_normalize_tag(str(t)) for t in v if _normalize_tag(str(t))]


class ChatFinalEvent(StrictModel):
    type: Literal["final"] = "final"
    data: ChatFinalData


class ChatErrorData(StrictModel):
    message: str
    code: str  # 예: "internal" | "invalid_argument" 등


class ChatErrorEvent(StrictModel):
    type: Literal["error"] = "error"
    data: ChatErrorData


# Pydantic에서 구분자(discriminator) 기반 유니온 스키마를 위한 힌트(선택적)
ChatEvent = Annotated[
    Union[ChatTokenEvent, ChatFinalEvent, ChatErrorEvent],
    Field(discriminator="type"),
]

# -------------------------------------------------------------------
# 업로드/잡 상태/인증/피드백 HTTP 스키마
# -------------------------------------------------------------------


# 업로드 응답 (스켈레톤 단계)
class UploadDocsResponse(StrictModel):
    job_id: str
    accepted: int
    skipped: int = 0


class IngestJobStatus(StrictModel):
    status: Literal["pending", "running", "succeeded", "failed"]
    processed: int = 0
    errors: List[str] = Field(default_factory=list)


# 인증
class LoginRequest(StrictModel):
    email: str
    password: str


class LoginResponse(StrictModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class UserPublic(StrictModel):
    user_id: str
    email: str


# 피드백
class FeedbackRequest(StrictModel):
    answer_id: str
    rating: Literal["up", "down"]
    chunk_ids: List[str] = Field(default_factory=list)
    reason: Optional[str] = None


class OkResponse(StrictModel):
    ok: bool = True


# 공통 에러(HTTP JSON)
class ErrorBody(StrictModel):
    code: str
    message: str


class ErrorResponse(StrictModel):
    error: ErrorBody


__all__ = [
    "SCHEMA_VERSION",
    "Chunk",
    "ScoredChunk",
    "ChatTokenEvent",
    "ChatFinalEvent",
    "ChatErrorEvent",
    "ChatEvent",
    "UploadDocsResponse",
    "IngestJobStatus",
    "LoginRequest",
    "LoginResponse",
    "UserPublic",
    "FeedbackRequest",
    "OkResponse",
    "ErrorResponse",
]
