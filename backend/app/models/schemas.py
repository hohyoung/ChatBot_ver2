from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Literal, Optional, Union, Annotated, Dict, Any
from pydantic import (
    BaseModel,
    Field,
    field_validator,
    ConfigDict,
    model_validator,
    AnyUrl,
    EmailStr,
)

# -------------------------------------------------------------------
# 공통: Pydantic 설정 & 유틸
# -------------------------------------------------------------------

SCHEMA_VERSION = "v1"


class StrictModel(BaseModel):
    """추가 필드 금지(엄격) 기본 베이스 (Pydantic v2)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _normalize_tag(t: str) -> str:
    t = (t or "").strip().lower()
    # 공백/슬래시/콤마 등을 공백으로 통일 후 하이픈 조인
    for ch in [",", "/", "\\", "|"]:
        t = t.replace(ch, " ")
    return "-".join(p for p in t.split() if p)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# -------------------------------------------------------------------
# 코어 데이터 모델 (문서/청크)
# -------------------------------------------------------------------


class Chunk(StrictModel):
    """저장소(Chroma)에 업서트/쿼리되는 최소 단위."""

    chunk_id: str = Field(..., description="문서 내 청크 고유 ID")
    doc_id: str = Field(..., description="원본 문서 ID(파일명/해시 등)")
    doc_type: Optional[str] = Field(
        default=None, description="문서 유형(e.g. policy-manual)"
    )
    doc_title: Optional[str] = Field(default=None, description="문서 표시용 제목")
    visibility: Literal["private", "org", "public"] = Field(default="org")
    tags: List[str] = Field(default_factory=list, description="정규화된 태그 목록")
    content: str = Field(..., description="청크 텍스트 본문")
    doc_url: Optional[str] = Field(
        default=None,
        description="정적 서빙되는 원본 문서 URL (예: /static/docs/doc_foo.pdf)",
    )

    doc_relpath: Optional[str] = Field(
        default=None,
        description="storage/docs 하위 상대 경로 (예: 'public/foo.pdf' 또는 'private/bar.pdf')",
    )

    # ✅ 질의와 가장 유사한 문장(미리보기 보조)
    focus_sentence: Optional[str] = Field(
        default=None, description="질의와 가장 관련 높은 문장(미리보기 보조용)"
    )

    owner_id: Optional[int] = Field(default=None, description="업로더 사용자 ID")
    owner_username: Optional[str] = Field(default=None, description="업로더 계정명")
    doc_hash: Optional[str] = Field(default=None, description="SHA-256 해시(내용 기반)")

    # PDF 기준 시작/끝 페이지(1-base). PDF가 아니면 None.
    page_start: Optional[int] = Field(default=None, description="시작 페이지(1-base)")
    page_end: Optional[int] = Field(default=None, description="끝 페이지(1-base)")

    @field_validator("tags", mode="before")
    @classmethod
    def _v_tags(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            v = [v]
        out, seen = [], set()
        for raw in v:
            tag = _normalize_tag(str(raw))
            if not tag or tag in seen:
                continue
            seen.add(tag)
            out.append(tag)
        return out


# 과거 코드 호환용 별칭
ChunkOut = Chunk


class ScoredChunk(StrictModel):
    """검색/재랭킹 단계에서 쓰는 래퍼: 원본 청크 + 점수들."""

    chunk: Chunk
    similarity: Optional[float] = Field(default=None)
    distance: Optional[float] = Field(default=None)
    final_score: Optional[float] = Field(default=None)
    # ↓ 하위호환: score 입력 들어오면 final_score로 승격
    score: Optional[float] = Field(
        default=None, description="Deprecated; use final_score"
    )
    reasons: List[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _compat_score_to_final(cls, data):
        if isinstance(data, dict) and "score" in data and "final_score" not in data:
            data["final_score"] = data.get("score")
        return data


# -------------------------------------------------------------------
# 채팅 API 스키마
# -------------------------------------------------------------------


class ChatRequest(StrictModel):
    question: str


class ChatAnswer(StrictModel):
    answer: str
    chunks: List[Chunk] = Field(default_factory=list)

    # 디버깅/추적용
    answer_id: Optional[str] = None
    used_tags: List[str] = Field(default_factory=list)
    latency_ms: Optional[int] = None

    # 메타
    version: str = Field(default=SCHEMA_VERSION)
    created_at: str = Field(default_factory=_now_iso)


class ChatDebugResponse(StrictModel):
    question: str
    answer: str
    used_chunks: List[Chunk] = Field(default_factory=list)
    candidates: List[ScoredChunk] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now_iso)
    version: str = Field(default=SCHEMA_VERSION)


class ChatTokenEvent(StrictModel):
    type: Literal["token"] = "token"
    token: str


class ChatFinalEvent(StrictModel):
    type: Literal["final"] = "final"
    data: ChatAnswer


class ChatErrorEvent(StrictModel):
    type: Literal["error"] = "error"
    error: str


ChatEvent = Annotated[
    Union[ChatTokenEvent, ChatFinalEvent, ChatErrorEvent],
    Field(discriminator="type"),
]


# -------------------------------------------------------------------
# 업로드/잡 상태/인증(레거시 섹션: 필요시 유지)
# -------------------------------------------------------------------


class UploadDocsResponse(StrictModel):
    job_id: str
    accepted: int
    skipped: int = 0


class IngestJobStatus(StrictModel):
    status: Literal["pending", "running", "succeeded", "failed"]
    processed: int = 0
    errors: List[str] = Field(default_factory=list)


class LoginRequest(StrictModel):
    email: str
    password: str


class UserPublic(StrictModel):
    user_id: str
    email: str
    role: Literal["user", "admin"] = "user"


class LoginResponse(StrictModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserPublic


class Source(BaseModel):
    title: str
    url: AnyUrl
    page: Optional[int] = None


class ChatResponse(BaseModel):
    message: str
    conversation_id: str
    sources: List[Source] = Field(default_factory=list)


# -------------------------------------------------------------------
# 피드백
# -------------------------------------------------------------------


class FeedbackRequest(StrictModel):
    chunk_id: str
    vote: Optional[Literal["up", "down"]] = None
    query: Optional[str] = None
    tag_context: List[str] = Field(default_factory=list)
    signal: Optional[Literal["up", "down"]] = Field(
        default=None, description="Deprecated"
    )
    weight: Optional[float] = Field(default=None, description="Deprecated")

    @field_validator("tag_context", mode="before")
    @classmethod
    def _v_tag_context(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            v = [v]
        return [_normalize_tag(str(t)) for t in v if _normalize_tag(str(t))]

    @model_validator(mode="before")
    @classmethod
    def _compat_signal_to_vote(cls, data):
        if isinstance(data, dict) and (not data.get("vote")) and data.get("signal"):
            data["vote"] = data["signal"]
        return data


class FeedbackUpdated(StrictModel):
    chunk_id: str
    delta: Optional[float] = None
    new_boost: Optional[float] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class FeedbackResponse(StrictModel):
    ok: bool = True
    updated: Optional[FeedbackUpdated] = None
    error: Optional[str] = None


class OkResponse(StrictModel):
    ok: bool = True


class ErrorResponse(StrictModel):
    ok: bool = False
    error: str


ChatFinalData = ChatAnswer  # alias
ChatErrorData = ErrorResponse  # alias
FeedbackIn = FeedbackRequest  # alias
FeedbackOut = FeedbackResponse  # alias


# -------------------------------------------------------------------
# 유저 인증 스키마 (실사용)
# -------------------------------------------------------------------

_FROM_ORM = ConfigDict(from_attributes=True)


class UserOut(BaseModel):
    model_config = _FROM_ORM
    id: int
    username: str
    # ✅ 지금은 이메일 검증/인증을 사용하지 않으므로 선택값으로
    email: Optional[EmailStr] = None
    security_level: int
    is_active: bool = True


class UserCreateExternal(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_]{3,50}$")
    # ✅ 나중에 이메일을 붙일 때 EmailStr로 바꾸기 쉬우니 필드 유지(지금은 선택값)
    email: Optional[EmailStr] = None
    password: str = Field(min_length=8, max_length=128)
    password_confirm: Optional[str] = Field(default=None, min_length=8, max_length=128)


class LoginIn(BaseModel):
    # 프론트는 지금 username으로만 로그인
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AuthUser(BaseModel):
    model_config = _FROM_ORM
    id: int
    username: str
    # ✅ 이메일 검증/인증 도입 전까지 optional
    email: Optional[EmailStr] = None
    security_level: int


class InternalSignupRequest(BaseModel):
    email: EmailStr  # @soosan.co.kr 전용 가입은 추후 도입 시 사용


class InternalSignupVerify(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_]{3,50}$")
    password: str = Field(min_length=8, max_length=128)


__all__ = [
    "SCHEMA_VERSION",
    "Chunk",
    "ChunkOut",
    "ScoredChunk",
    "ChatRequest",
    "ChatAnswer",
    "ChatDebugResponse",
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
    "FeedbackUpdated",
    "FeedbackResponse",
    "OkResponse",
    "ErrorResponse",
    "ChatFinalData",
    "ChatErrorData",
    "FeedbackIn",
    "FeedbackOut",
    "ChatResponse",
    "Source",
    "UserOut",
    "UserCreateExternal",
    "LoginIn",
    "TokenOut",
    "AuthUser",
    "InternalSignupRequest",
    "InternalSignupVerify",
]
