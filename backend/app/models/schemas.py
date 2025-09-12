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
    """검색/재랭킹 단계에서 쓰는 래퍼: 원본 청크 + 점수들.

    - similarity  : 코사인 유사도 (= 1 - distance), 0~1
    - distance    : 코사인 거리(Chroma)
    - final_score : 태그/피드백 반영 최종 점수(정렬 기준)
    - score       : [Deprecated] 과거 이름(입력 호환만 허용)
    - reasons     : 디버깅용 가중 근거 문자열
    """

    chunk: Chunk
    similarity: Optional[float] = Field(default=None)
    distance: Optional[float] = Field(default=None)
    final_score: Optional[float] = Field(default=None)
    # ↓ 하위호환: 외부에서 score 키를 보내도 받기만 하고 final_score로 올린다
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
    """최종 답변 페이로드."""

    answer: str
    chunks: List[Chunk] = Field(default_factory=list)

    # 디버깅/추적용 필드(라우터 구현과 로그에 맞춰 optional 로 허용)
    answer_id: Optional[str] = None
    used_tags: List[str] = Field(default_factory=list)
    latency_ms: Optional[int] = None

    # 메타
    version: str = Field(default=SCHEMA_VERSION)
    created_at: str = Field(default_factory=_now_iso)


class ChatDebugResponse(StrictModel):
    """디버깅 엔드포인트(/api/chat.debug)에서 사용."""

    question: str
    answer: str
    used_chunks: List[Chunk] = Field(default_factory=list)
    candidates: List[ScoredChunk] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now_iso)
    version: str = Field(default=SCHEMA_VERSION)


# (선택) 스트리밍 이벤트 스키마
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
# 업로드/잡 상태/인증
# -------------------------------------------------------------------


class UploadDocsResponse(StrictModel):
    job_id: str
    accepted: int
    skipped: int = 0


class IngestJobStatus(StrictModel):
    status: Literal["pending", "running", "succeeded", "failed"]
    processed: int = 0
    errors: List[str] = Field(default_factory=list)


# 인증 (프로토타입)
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
    url: AnyUrl  # 나중에 /static/... 링크가 들어갈 자리
    page: Optional[int] = None  # PDF 페이지 등 필요 없으면 생략 가능


class ChatResponse(BaseModel):
    # 기존 필드들 유지: e.g., message, conversation_id, etc.
    message: str
    conversation_id: str
    # 새 필드 추가
    sources: List[Source] = Field(default_factory=list)


# -------------------------------------------------------------------
# 피드백 스키마 (히스토리 호환 포함)
# -------------------------------------------------------------------


class FeedbackRequest(StrictModel):
    """/api/feedback 입력.

    - vote: "up" | "down"
    - query: 사용자가 평가를 남긴 당시 질의(선택)
    - tag_context: 페이지/탭 등 전역 태그 컨텍스트(선택)

    하위호환:
    - signal: (deprecated) "up"|"down" 이 오면 vote로 승격
    - weight: (deprecated) 가중치 수치(정규화는 서비스 계층에서)
    """

    chunk_id: str
    vote: Optional[Literal["up", "down"]] = None
    query: Optional[str] = None
    tag_context: List[str] = Field(default_factory=list)

    # ↓ 하위호환 입력 허용
    signal: Optional[Literal["up", "down"]] = Field(
        default=None, description="Deprecated; use vote"
    )
    weight: Optional[float] = Field(
        default=None, description="Deprecated; will be ignored or normalized"
    )

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
        # vote가 비어 있고 signal이 있으면 vote로 승격
        if isinstance(data, dict) and (not data.get("vote")) and data.get("signal"):
            data["vote"] = data["signal"]
        return data


class FeedbackUpdated(StrictModel):
    """응답의 보조 정보(선택). 실제 값은 서비스 계층에서 구성."""

    chunk_id: str
    delta: Optional[float] = None
    new_boost: Optional[float] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class FeedbackResponse(StrictModel):
    """/api/feedback 응답. 기존 OkResponse와 호환되도록 ok만으로도 유효."""

    ok: bool = True
    updated: Optional[FeedbackUpdated] = None
    error: Optional[str] = None


# -------------------------------------------------------------------
# 범용 응답
# -------------------------------------------------------------------


class OkResponse(StrictModel):
    ok: bool = True


class ErrorResponse(StrictModel):
    ok: bool = False
    error: str


# --- backward-compat aliases (legacy names used by older router/chat code) ---
ChatFinalData = ChatAnswer  # old -> new
ChatErrorData = ErrorResponse  # old -> new

# --- backward-compat aliases (legacy names used by older feedback router) ---
FeedbackIn = FeedbackRequest  # old -> new
FeedbackOut = FeedbackResponse  # old -> new


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
]
