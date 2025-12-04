# backend/app/rag/orchestrator.py
"""
GAR Orchestrator - Phase 1 기본 구조

GAR (Generate-Augment-Retrieve) 파이프라인의 전체 플로우를 조율합니다.

Phase 1: Intent 분류 + 문서 인덱스 + 쿼리 분해
Phase 2: 쿼리 확장 + 문서 필터링 + 다단계 검색 (추후 구현)
Phase 3: 리랭킹 (추후 구현)
Phase 4: 최적화 (추후 구현)
"""

from __future__ import annotations

import time
from typing import AsyncIterator, Tuple, List
from pydantic import BaseModel, Field

from app.services.logging import get_logger
from app.models.schemas import Chunk, ScoredChunk

# Phase 1 모듈
from app.rag.intent_classifier import classify_intent, IntentResult
from app.rag.doc_discovery import get_available_documents, DocContext
from app.rag.query_decomposer import decompose_query, SubQuery

# 기존 모듈
from app.rag.retriever import retrieve
from app.rag.generator import generate_answer_stream
from app.ingest.tagger import tag_query

log = get_logger("app.rag.orchestrator")


class GARMetrics(BaseModel):
    """GAR 파이프라인 성능 메트릭"""

    intent_classification_ms: float = 0.0
    doc_discovery_ms: float = 0.0
    query_decomposition_ms: float = 0.0
    tagging_ms: float = 0.0
    retrieval_ms: float = 0.0
    reranking_ms: float = 0.0  # Phase 3
    generation_ms: float = 0.0
    total_ms: float = 0.0


class GARContext(BaseModel):
    """GAR 파이프라인 실행 컨텍스트"""

    question: str
    intent: IntentResult
    doc_context: DocContext
    subqueries: List[SubQuery]
    used_tags: List[str] = Field(default_factory=list)
    candidates: List[ScoredChunk] = Field(default_factory=list)
    metrics: GARMetrics = Field(default_factory=GARMetrics)


async def orchestrate_gar_phase1(question: str) -> GARContext:
    """
    GAR Phase 1 실행: Intent 분류 + 문서 인덱스 + 쿼리 분해

    Args:
        question: 사용자 질문

    Returns:
        GARContext: GAR 실행 컨텍스트
    """
    log.info("=== GAR Phase 1 시작 ===")
    t_start = time.perf_counter()

    metrics = GARMetrics()

    # 1단계: Intent 분류 + 문서 인덱스 조회 (병렬)
    log.info("[1/3] Intent 분류 + 문서 인덱스 조회 (병렬)")
    t1 = time.perf_counter()

    import asyncio

    intent, doc_context = await asyncio.gather(
        classify_intent(question), get_available_documents()
    )

    t2 = time.perf_counter()
    metrics.intent_classification_ms = (t2 - t1) * 1000
    metrics.doc_discovery_ms = (t2 - t1) * 1000  # 병렬이므로 동일
    log.info(
        "[1/3] 완료: intent=%s (confidence=%.2f), docs=%d (%.1f ms)",
        intent.type,
        intent.confidence,
        doc_context.total_docs,
        metrics.intent_classification_ms,
    )

    # 2단계: 쿼리 분해
    log.info("[2/3] 쿼리 분해")
    t3 = time.perf_counter()

    subqueries = await decompose_query(question, doc_context, intent)

    t4 = time.perf_counter()
    metrics.query_decomposition_ms = (t4 - t3) * 1000
    log.info(
        "[2/3] 완료: %d개 서브쿼리 생성 (%.1f ms)",
        len(subqueries),
        metrics.query_decomposition_ms,
    )

    for i, sq in enumerate(subqueries, start=1):
        log.debug("  서브쿼리 %d: %r (focus=%r, priority=%d)", i, sq.text, sq.focus, sq.priority)

    # 3단계: 태깅 (기존 tag_query 사용)
    log.info("[3/3] 태깅")
    t5 = time.perf_counter()

    # 모든 서브쿼리 텍스트 결합하여 태깅
    combined_query = " ".join(sq.text for sq in subqueries)
    used_tags = await tag_query(combined_query, max_tags=6)

    t6 = time.perf_counter()
    metrics.tagging_ms = (t6 - t5) * 1000
    log.info("[3/3] 완료: tags=%s (%.1f ms)", used_tags, metrics.tagging_ms)

    # 전체 시간
    t_end = time.perf_counter()
    metrics.total_ms = (t_end - t_start) * 1000

    log.info("=== GAR Phase 1 완료 (%.1f ms) ===", metrics.total_ms)

    return GARContext(
        question=question,
        intent=intent,
        doc_context=doc_context,
        subqueries=subqueries,
        used_tags=used_tags,
        metrics=metrics,
    )


async def orchestrate_gar_stream(
    question: str,
    use_phase2: bool = False,  # Feature Flag: Phase 2 사용 여부
    use_phase3: bool = False,  # Feature Flag: Phase 3 사용 여부 (리랭킹)
    websocket = None,  # WebSocket 연결 (진행 상태 전송용)
) -> AsyncIterator[Tuple[str, List[Chunk] | None]]:
    """
    GAR 파이프라인 전체 실행 (스트리밍).

    Phase 1: Intent 분류 + 문서 인덱스 + 쿼리 분해
    Phase 2: 쿼리 확장 + 문서 필터링 + 다단계 검색 (선택적)
    Phase 3: LLM 기반 리랭킹 (선택적)

    Args:
        question: 사용자 질문
        use_phase2: Phase 2 활성화 여부 (기본 False)
        use_phase3: Phase 3 활성화 여부 (기본 False)

    Yields:
        (token, None): 토큰 스트리밍
        ("", chunks): 최종 청크 리스트
    """
    log.info("=== GAR 파이프라인 시작 (스트리밍, Phase2=%s, Phase3=%s) ===", use_phase2, use_phase3)

    # 진행 상태 전송: 질문 의도 파악
    if websocket:
        try:
            await websocket.send_json({
                "type": "stage",
                "stage": "intent",
                "message": "무엇을 알려드릴지 생각하고 있어요"
            })
        except Exception as e:
            log.warning(f"WebSocket stage 전송 실패 (무시): {e}")

    # Phase 1: Intent + 문서 인덱스 + 쿼리 분해
    context = await orchestrate_gar_phase1(question)

    # Phase 2: 쿼리 확장 + 문서 필터링 + 다단계 검색
    t_retrieval_start = time.perf_counter()

    if use_phase2:
        # 진행 상태 전송: 검색어 확장
        if websocket:
            try:
                await websocket.send_json({
                    "type": "stage",
                    "stage": "expand",
                    "message": "더 좋은 검색어를 찾고 있어요"
                })
            except Exception as e:
                log.warning(f"WebSocket stage 전송 실패 (무시): {e}")

        log.info("=== Phase 2 시작: 쿼리 확장 + 다단계 검색 ===")

        # 필요한 모듈 임포트
        from app.rag.query_expander import QueryExpander
        from app.rag.doc_filter import DocumentFilter
        from app.rag.retriever import retrieve_multi_query

        expander = QueryExpander()
        doc_filter = DocumentFilter()

        all_chunks = []

        # 각 서브쿼리별로 처리
        for sub_query in context.subqueries:
            log.info("서브쿼리 처리: %r", sub_query.text)

            # Step 1: 쿼리 확장
            doc_titles = [d.doc_title for d in context.doc_context.recent_docs]
            expanded_queries = await expander.expand_query(
                original_query=sub_query.text,
                doc_context=doc_titles,
                max_expansions=3,
            )
            log.info("확장된 쿼리 (%d개):", len(expanded_queries))
            for idx, eq in enumerate(expanded_queries):
                log.info("  [%d] %r", idx, eq)

            # Step 2: 문서 필터 생성
            where_filter = doc_filter.build_filter_criteria(
                intent=context.intent.type,
                doc_context=doc_titles,
                tags=context.used_tags,
            )
            log.debug("문서 필터: %s", where_filter)

            # 진행 상태 전송: 문서 검색 (첫 서브쿼리에서만)
            if websocket and sub_query == context.subqueries[0]:
                try:
                    await websocket.send_json({
                        "type": "stage",
                        "stage": "search",
                        "message": "문서에서 정보를 찾는 중..."
                    })
                except Exception as e:
                    log.warning(f"WebSocket stage 전송 실패 (무시): {e}")

            # Step 3: 다단계 검색
            chunks = await retrieve_multi_query(
                queries=expanded_queries,
                k_per_query=10,
                tags=context.used_tags,
                where_filter=where_filter,
                diversify=True,
            )
            log.info("서브쿼리 검색 완료: %d개 청크", len(chunks))

            all_chunks.extend(chunks)

        # 서브쿼리별 결과 병합 및 중복 제거
        candidates = _merge_and_deduplicate(all_chunks, top_k=10)
        log.info("Phase 2 완료: 총 %d개 → 병합 후 %d개", len(all_chunks), len(candidates))

    else:
        # 기존 방식 (Phase 1만 사용)
        # 진행 상태 전송: 문서 검색
        if websocket:
            try:
                await websocket.send_json({
                    "type": "stage",
                    "stage": "search",
                    "message": "문서에서 정보를 찾는 중..."
                })
            except Exception as e:
                log.warning(f"WebSocket stage 전송 실패 (무시): {e}")

        log.info("검색 (기존 retriever 사용, Phase 2 비활성화)")
        candidates = await retrieve(question, context.used_tags, k=5)

    t_retrieval_end = time.perf_counter()
    context.metrics.retrieval_ms = (t_retrieval_end - t_retrieval_start) * 1000
    log.info("검색 완료: %d개 청크 (%.1f ms)", len(candidates), context.metrics.retrieval_ms)

    # Phase 3: LLM 기반 리랭킹 (선택적)
    if use_phase3:
        # 진행 상태 전송: 리랭킹
        if websocket:
            try:
                await websocket.send_json({
                    "type": "stage",
                    "stage": "rerank",
                    "message": "가장 정확한 부분만 골라내는 중..."
                })
            except Exception as e:
                log.warning(f"WebSocket stage 전송 실패 (무시): {e}")

        log.info("=== Phase 3 시작: LLM 기반 리랭킹 ===")
        t_rerank_start = time.perf_counter()

        from app.rag.reranker import LLMReranker

        reranker = LLMReranker(
            w_llm=0.5,  # LLM 점수 가중치
            w_feedback=0.2,  # 피드백 점수 가중치
            w_tag=0.15,  # 태그 매칭 가중치
            w_similarity=0.15,  # 유사도 가중치
            batch_size=5,  # 배치 크기
        )

        candidates = await reranker.rerank(
            question=question,
            chunks=candidates,
            query_tags=context.used_tags,
            top_k=5,  # 최종 5개 선택
        )

        t_rerank_end = time.perf_counter()
        context.metrics.reranking_ms = (t_rerank_end - t_rerank_start) * 1000

        # 메트릭 로깅
        rerank_metrics = reranker.get_metrics()
        log.info(
            "Phase 3 완료: 리랭킹 후 %d개 청크 선택 (%.1f ms)\n"
            "  캐시 적중률: %.1f%% (hits=%d, misses=%d)\n"
            "  LLM 호출: %d회",
            len(candidates),
            context.metrics.reranking_ms,
            rerank_metrics["cache_hit_rate"] * 100,
            rerank_metrics["cache_hits"],
            rerank_metrics["cache_misses"],
            rerank_metrics["llm_calls"],
        )
    else:
        log.info("Phase 3 비활성화 (리랭킹 없음)")
        context.metrics.reranking_ms = 0.0

    # 답변 생성 (스트리밍)
    # 진행 상태 전송: 답변 생성
    if websocket:
        try:
            await websocket.send_json({
                "type": "stage",
                "stage": "generate",
                "message": "답변을 정리하고 있어요"
            })
        except Exception as e:
            log.warning(f"WebSocket stage 전송 실패 (무시): {e}")

    log.info("답변 생성 시작 (스트리밍)")
    t_gen_start = time.perf_counter()

    async for token, chunks, image_refs in generate_answer_stream(question, candidates):
        if chunks is not None:
            # 스트림 종료
            t_gen_end = time.perf_counter()
            context.metrics.generation_ms = (t_gen_end - t_gen_start) * 1000
            context.metrics.total_ms = (t_gen_end - t_retrieval_start + context.metrics.total_ms)

            log.info(
                "=== GAR 파이프라인 완료 ===\n"
                "  Intent 분류: %.1f ms\n"
                "  문서 인덱스: %.1f ms\n"
                "  쿼리 분해: %.1f ms\n"
                "  태깅: %.1f ms\n"
                "  검색: %.1f ms\n"
                "  리랭킹: %.1f ms\n"
                "  생성: %.1f ms\n"
                "  총 시간: %.1f ms",
                context.metrics.intent_classification_ms,
                context.metrics.doc_discovery_ms,
                context.metrics.query_decomposition_ms,
                context.metrics.tagging_ms,
                context.metrics.retrieval_ms,
                context.metrics.reranking_ms,
                context.metrics.generation_ms,
                context.metrics.total_ms,
            )

            yield ("", chunks)
        else:
            # 토큰 스트리밍
            yield (token, None)


def _merge_and_deduplicate(
    chunks: List[ScoredChunk],
    top_k: int = 10,
) -> List[ScoredChunk]:
    """
    서브쿼리별 검색 결과 병합 및 중복 제거

    Args:
        chunks: ScoredChunk 리스트 (중복 가능)
        top_k: 최종 선택 개수

    Returns:
        병합 및 중복 제거된 ScoredChunk 리스트
    """
    unique = {}
    for chunk in chunks:
        cid = chunk.chunk.chunk_id
        if cid in unique:
            # 중복: 스코어 합산
            unique[cid].final_score = (unique[cid].final_score or 0.0) + (chunk.final_score or 0.0)
        else:
            unique[cid] = chunk

    result = list(unique.values())
    result.sort(key=lambda c: c.final_score or 0.0, reverse=True)

    log.debug(
        "[_merge_and_deduplicate] %d개 → %d개 고유 청크 → Top %d",
        len(chunks),
        len(unique),
        min(top_k, len(result)),
    )

    return result[:top_k]
