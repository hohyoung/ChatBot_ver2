# backend/app/services/debug_logger.py
"""
RAG 파이프라인 상세 디버깅 로거

각 단계별로 어떤 청크들이 살아남는지 log.txt 파일에 상세히 기록합니다.
"""

from __future__ import annotations
import os
from datetime import datetime
from typing import List, Optional, Any, Dict
from pathlib import Path

# 로그 파일 경로 (backend 폴더 기준)
LOG_FILE_PATH = Path(__file__).parent.parent.parent / "log.txt"

# 전역 활성화 플래그
_enabled = True


def enable():
    """디버그 로깅 활성화"""
    global _enabled
    _enabled = True


def disable():
    """디버그 로깅 비활성화"""
    global _enabled
    _enabled = False


def clear_log():
    """로그 파일 초기화"""
    try:
        with open(LOG_FILE_PATH, "w", encoding="utf-8") as f:
            f.write("")
    except Exception:
        pass


def log(message: str, level: str = "INFO"):
    """
    로그 파일에 메시지 기록

    Args:
        message: 기록할 메시지
        level: 로그 레벨 (INFO, DEBUG, WARN, ERROR)
    """
    if not _enabled:
        return

    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        log_line = f"[{timestamp}] [{level}] {message}\n"

        with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
            f.write(log_line)
    except Exception as e:
        # 로깅 실패해도 무시
        pass


def log_section(title: str):
    """섹션 구분선 로깅"""
    log("")
    log("=" * 80)
    log(f"  {title}")
    log("=" * 80)


def log_subsection(title: str):
    """서브섹션 구분선 로깅"""
    log("")
    log("-" * 60)
    log(f"  {title}")
    log("-" * 60)


def log_query_start(question: str):
    """쿼리 시작 로깅"""
    log_section(f"새 질문 처리 시작")
    log(f"질문: {question}")
    log(f"시작 시간: {datetime.now().isoformat()}")


def log_intent_result(intent_type: str, confidence: float, reasoning: str = ""):
    """Intent 분류 결과 로깅"""
    log_subsection("1단계: Intent 분류")
    log(f"Intent 유형: {intent_type}")
    log(f"Confidence: {confidence:.2f}")
    if reasoning:
        log(f"Reasoning: {reasoning}")


def log_query_decomposition(subqueries: List[Any]):
    """쿼리 분해 결과 로깅"""
    log_subsection("2단계: 쿼리 분해")
    log(f"서브쿼리 수: {len(subqueries)}개")
    for i, sq in enumerate(subqueries, start=1):
        if hasattr(sq, 'text'):
            log(f"  [{i}] {sq.text} (focus={getattr(sq, 'focus', 'N/A')}, priority={getattr(sq, 'priority', 'N/A')})")
        else:
            log(f"  [{i}] {sq}")


def log_retrieval_start(query: str, k: int):
    """검색 시작 로깅"""
    log_subsection("3단계: 벡터 검색 (retrieve)")
    log(f"검색 쿼리: {query}")
    log(f"요청 결과 수 (k): {k}")


def log_chromadb_raw_results(raw_results: Dict[str, Any]):
    """ChromaDB 원시 결과 로깅"""
    log("")
    log("[ChromaDB 원시 결과]")

    docs = raw_results.get("documents", [[]])[0] if raw_results.get("documents") else []
    metas = raw_results.get("metadatas", [[]])[0] if raw_results.get("metadatas") else []
    dists = raw_results.get("distances", [[]])[0] if raw_results.get("distances") else []

    log(f"검색된 청크 수: {len(docs)}개")
    log("")

    for i, (doc, meta, dist) in enumerate(zip(docs, metas, dists)):
        meta = meta or {}
        chunk_id = meta.get("chunk_id", f"unknown_{i}")
        doc_title = meta.get("doc_title", "N/A")
        doc_type = meta.get("doc_type", "N/A")
        page_start = meta.get("page_start", "N/A")
        tags = meta.get("tags", "N/A")
        similarity = 1.0 - float(dist) if dist else 0.0

        content_preview = (doc or "")[:150].replace("\n", " ")

        log(f"  [{i+1}] chunk_id: {chunk_id}")
        log(f"      doc_title: {doc_title}")
        log(f"      doc_type: {doc_type}")
        log(f"      page: {page_start}")
        log(f"      tags: {tags}")
        log(f"      distance: {dist:.4f} → similarity: {similarity:.4f}")
        log(f"      content: {content_preview}...")
        log("")


def log_retrieval_scoring(chunk_id: str, doc_title: str, similarity: float,
                          feedback_factor: float, final_score: float,
                          content_preview: str = ""):
    """검색 결과 스코어링 로깅"""
    log(f"  스코어링: {chunk_id}")
    log(f"    doc_title: {doc_title}")
    log(f"    similarity: {similarity:.4f}")
    log(f"    feedback_factor: {feedback_factor:.4f}")
    log(f"    final_score: {final_score:.4f} = sim({similarity:.4f}) × fb({feedback_factor:.4f})")
    if content_preview:
        log(f"    content: {content_preview[:100]}...")


def log_retrieval_result(scored_chunks: List[Any]):
    """검색 최종 결과 로깅"""
    log("")
    log("[검색 결과 정렬 후 (final_score 기준)]")
    log(f"총 {len(scored_chunks)}개 청크 반환")

    for i, sc in enumerate(scored_chunks):
        chunk = sc.chunk if hasattr(sc, 'chunk') else sc
        score = sc.final_score if hasattr(sc, 'final_score') else getattr(sc, 'score', 0)

        chunk_id = getattr(chunk, 'chunk_id', 'N/A')
        doc_title = getattr(chunk, 'doc_title', 'N/A')
        content = getattr(chunk, 'content', '')[:100].replace("\n", " ")

        log(f"  [{i+1}] score={score:.4f} | {chunk_id} | {doc_title}")
        log(f"      content: {content}...")


def log_reranking_start(question: str, chunks_count: int):
    """리랭킹 시작 로깅"""
    log_subsection("4단계: LLM 리랭킹 (rerank)")
    log(f"질문: {question}")
    log(f"리랭킹 대상 청크 수: {chunks_count}개")


def log_reranking_llm_scores(scores: Dict[int, float], chunks: List[Any]):
    """리랭킹 LLM 점수 로깅"""
    log("")
    log("[LLM 관련성 평가 점수]")

    for idx, score in sorted(scores.items()):
        if idx < len(chunks):
            chunk = chunks[idx].chunk if hasattr(chunks[idx], 'chunk') else chunks[idx]
            chunk_id = getattr(chunk, 'chunk_id', 'N/A')
            doc_title = getattr(chunk, 'doc_title', 'N/A')
            log(f"  [{idx}] LLM점수={score:.2f} | {chunk_id} | {doc_title}")


def log_reranking_final_scores(chunks: List[Any]):
    """리랭킹 최종 점수 로깅"""
    log("")
    log("[리랭킹 최종 점수 (정렬 후)]")

    for i, sc in enumerate(chunks):
        chunk = sc.chunk if hasattr(sc, 'chunk') else sc
        final_score = getattr(sc, 'final_score', 0)
        reasons = getattr(sc, 'reasons', [])

        chunk_id = getattr(chunk, 'chunk_id', 'N/A')
        doc_title = getattr(chunk, 'doc_title', 'N/A')
        content = getattr(chunk, 'content', '')[:80].replace("\n", " ")

        log(f"  [{i+1}] final_score={final_score:.4f} | {chunk_id} | {doc_title}")
        if reasons:
            log(f"      점수 구성: {reasons[-1] if reasons else 'N/A'}")
        log(f"      content: {content}...")


def log_generation_input(question: str, selected_chunks: List[Any]):
    """답변 생성 입력 로깅"""
    log_subsection("5단계: 답변 생성 (generate)")
    log(f"질문: {question}")
    log(f"사용할 청크 수: {len(selected_chunks)}개")
    log("")
    log("[LLM에 전달되는 청크들]")

    for i, chunk in enumerate(selected_chunks, start=1):
        chunk_id = getattr(chunk, 'chunk_id', 'N/A')
        doc_title = getattr(chunk, 'doc_title', 'N/A')
        content = getattr(chunk, 'content', '')[:200].replace("\n", " ")

        log(f"  [{i}] {chunk_id} | {doc_title}")
        log(f"      content: {content}...")


def log_generation_result(answer: str):
    """답변 생성 결과 로깅"""
    log("")
    log("[생성된 답변]")
    log(answer[:500] + ("..." if len(answer) > 500 else ""))


def log_query_end(total_time_ms: float = 0):
    """쿼리 처리 완료 로깅"""
    log("")
    log_section("질문 처리 완료")
    if total_time_ms > 0:
        log(f"총 처리 시간: {total_time_ms:.1f}ms")
    log(f"완료 시간: {datetime.now().isoformat()}")
    log("")
    log("")
