# backend/app/rag/doc_discovery.py
"""
Document Discovery - GAR Phase 1

현재 시스템에 업로드된 문서들의 컨텍스트를 조회합니다.
- 전체 문서 목록
- 문서 유형/태그/통계
- Redis 캐싱 (TTL 10분)
"""

from __future__ import annotations

from typing import List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime, timezone, timedelta

from app.vectorstore.store import get_doc_stats, search_docs
from app.services.logging import get_logger

log = get_logger("app.rag.doc_discovery")

# Redis 캐싱 (향후 추가)
# from app.services.redis_client import get_redis
# CACHE_KEY = "doc_context"
# CACHE_TTL = 600  # 10분


class DocSummary(BaseModel):
    """개별 문서 요약"""

    doc_id: str
    doc_title: str
    doc_type: str | None = None
    tags: List[str] = Field(default_factory=list)
    chunk_count: int = 0
    uploaded_at: str | None = None


class DocContext(BaseModel):
    """
    현재 시스템에 업로드된 문서들의 컨텍스트.

    GAR 파이프라인에서 질문 분해 및 확장 시 활용.
    """

    total_docs: int = Field(..., description="전체 문서 수")
    total_chunks: int = Field(..., description="전체 청크 수")
    doc_types: List[str] = Field(default_factory=list, description="문서 유형 목록")
    all_tags: List[str] = Field(default_factory=list, description="전체 태그 목록")
    recent_docs: List[DocSummary] = Field(
        default_factory=list, description="최근 문서 목록 (최대 20개)"
    )
    stats_by_type: Dict[str, int] = Field(
        default_factory=dict, description="유형별 청크 수"
    )
    stats_by_visibility: Dict[str, int] = Field(
        default_factory=dict, description="공개범위별 청크 수"
    )


async def get_available_documents() -> DocContext:
    """
    현재 업로드된 문서 컨텍스트를 조회합니다.

    Returns:
        DocContext: 문서 컨텍스트

    Examples:
        >>> context = await get_available_documents()
        >>> print(context.total_docs)  # 15
        >>> print(context.doc_types)   # ["인사규정", "복무규정", ...]
    """
    log.info("문서 컨텍스트 조회 시작")

    # TODO: Redis 캐싱 추가 (Phase 4)
    # redis = get_redis()
    # cached = redis.get(CACHE_KEY)
    # if cached:
    #     return DocContext.model_validate_json(cached)

    try:
        # 1) 통계 조회 (GET /api/docs/stats)
        stats = get_doc_stats()
        log.debug("문서 통계: %s", stats)

        # 2) 전체 문서 목록 조회 (GET /api/docs/search?limit=200)
        search_result = search_docs(limit=200)
        all_docs = search_result.get("items", [])
        log.debug("전체 문서 수: %d", len(all_docs))

        # 3) 문서 요약 생성
        recent_docs: List[DocSummary] = []
        for doc in all_docs[:20]:  # 최근 20개만
            try:
                recent_docs.append(
                    DocSummary(
                        doc_id=doc.get("doc_id", ""),
                        doc_title=doc.get("doc_title", "Untitled"),
                        doc_type=doc.get("doc_type"),
                        tags=doc.get("tags", []),
                        chunk_count=doc.get("chunk_count", 0),
                        uploaded_at=doc.get("uploaded_at"),
                    )
                )
            except Exception as e:
                log.warning("문서 요약 생성 실패 (건너뜀): %s, doc=%s", e, doc)
                continue

        # 4) 태그 목록 추출 (중복 제거)
        all_tags_set = set()
        for doc in all_docs:
            doc_tags = doc.get("tags", [])
            if isinstance(doc_tags, list):
                all_tags_set.update(doc_tags)
        all_tags = sorted(list(all_tags_set))

        # 5) 문서 유형 목록 추출
        doc_types = list(stats.get("by_type", {}).keys())

        # 6) DocContext 생성
        context = DocContext(
            total_docs=stats.get("total_docs", 0),
            total_chunks=stats.get("total_chunks", 0),
            doc_types=doc_types,
            all_tags=all_tags,
            recent_docs=recent_docs,
            stats_by_type=stats.get("by_type", {}),
            stats_by_visibility=stats.get("by_visibility", {}),
        )

        log.info(
            "문서 컨텍스트 조회 완료: total_docs=%d, total_chunks=%d, tags=%d",
            context.total_docs,
            context.total_chunks,
            len(context.all_tags),
        )

        # TODO: Redis 캐싱 저장 (Phase 4)
        # redis.setex(CACHE_KEY, CACHE_TTL, context.model_dump_json())

        return context

    except Exception as e:
        log.exception("문서 컨텍스트 조회 실패: %s", e)
        # 폴백: 빈 컨텍스트 반환
        return DocContext(
            total_docs=0,
            total_chunks=0,
            doc_types=[],
            all_tags=[],
            recent_docs=[],
            stats_by_type={},
            stats_by_visibility={},
        )


async def get_doc_context_summary(context: DocContext) -> str:
    """
    문서 컨텍스트를 LLM 프롬프트용 텍스트로 변환합니다.

    Args:
        context: 문서 컨텍스트

    Returns:
        str: 프롬프트용 텍스트

    Examples:
        >>> summary = await get_doc_context_summary(context)
        >>> print(summary)
        현재 시스템에 다음 문서들이 있습니다:
        - 총 15개 문서, 450개 청크
        - 문서 유형: 인사규정, 복무규정, ...
        - 주요 태그: hr-policy, leave, conduct, ...
    """
    lines = [
        "현재 시스템에 다음 문서들이 있습니다:",
        f"- 총 {context.total_docs}개 문서, {context.total_chunks}개 청크",
    ]

    if context.doc_types:
        lines.append(f"- 문서 유형: {', '.join(context.doc_types[:10])}")

    if context.all_tags:
        lines.append(f"- 주요 태그: {', '.join(context.all_tags[:15])}")

    if context.recent_docs:
        lines.append("\n최근 업로드된 문서:")
        for i, doc in enumerate(context.recent_docs[:5], start=1):
            tags_str = ", ".join(doc.tags[:3]) if doc.tags else "태그 없음"
            lines.append(f"  {i}. {doc.doc_title} (태그: {tags_str})")

    return "\n".join(lines)
