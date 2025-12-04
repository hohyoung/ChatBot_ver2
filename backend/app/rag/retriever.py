# backend/app/rag/retriever.py
from __future__ import annotations
import asyncio
import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.services.embedding import embed_query, embed_query_async
from app.vectorstore.store import query_by_embedding
from app.models.schemas import ChunkOut, ScoredChunk
from app.services.feedback_store import get_boost_map

logger = logging.getLogger("app.rag.retriever")


def _similarity_from_distance(d: float) -> float:
    # chroma distance = cosine distance, similarity = 1 - distance (0~1)
    try:
        sim = 1.0 - float(d)
    except Exception:
        sim = 0.0
    return max(0.0, min(1.0, sim))


def _feedback_factor(meta: Dict[str, Any]) -> float:
    """
    간단한 확률형 선호도 → 가중치(0.5~1.5).
    p = (pos+1)/(pos+neg+2), factor = 0.5 + p
    """
    pos = int(meta.get("fb_pos", 0) or 0)
    neg = int(meta.get("fb_neg", 0) or 0)
    p = (pos + 1.0) / (pos + neg + 2.0)
    return 0.5 + p  # 0.5~1.5


def _tag_boost(meta: Dict[str, Any], query_tags: Optional[Sequence[str]]) -> float:
    """
    메타의 tags_json(list) 또는 tags(CSV)에 대해 질의 태그와의 교집합 개수로 1 + 0.05*k 부스트.
    """
    if not query_tags:
        return 1.0

    tags: List[str] = []
    if "tags_json" in meta and isinstance(meta["tags_json"], str):
        # sanitize_metadata가 JSON 문자열로 저장함
        try:
            import json

            tags = json.loads(meta["tags_json"]) or []
        except Exception:
            tags = []
    elif "tags" in meta and isinstance(meta["tags"], str):
        tags = [t.strip() for t in meta["tags"].split(",") if t.strip()]

    if not tags:
        return 1.0

    overlap = len(set(t.lower() for t in tags) & set(t.lower() for t in query_tags))
    return 1.0 + 0.05 * overlap  # 겹칠수록 소폭 가산


def _to_chunk_out(chunk_id: str, content: str, meta: Dict[str, Any]) -> ChunkOut:

    logger.debug("[RETRIEVE] meta keys=%s", list(meta.keys()))
    logger.debug(
        "[RETRIEVE] raw meta page_start=%r (%s) page_end=%r (%s)",
        meta.get("page_start"),
        type(meta.get("page_start")).__name__,
        meta.get("page_end"),
        type(meta.get("page_end")).__name__,
    )
    logger.debug(
        "[RETRIEVE] raw meta rel=%r url=%r",
        meta.get("doc_relpath"),
        meta.get("doc_url"),
    )
    # 1) relpath 정규화
    rel_raw = meta.get("doc_relpath") or meta.get("relpath")
    rel_norm = str(rel_raw).replace("\\", "/").lstrip("/") if rel_raw else None

    # 2) URL 조립용 core (public/, static/docs/ 제거)
    rel_core = None
    if rel_norm:
        rel_core = rel_norm
        for p in ("public/", "static/docs/"):
            if rel_core.startswith(p):
                rel_core = rel_core[len(p) :]

    # 3) URL 결정: rel_core 우선 → 저장된 doc_url
    url = f"/static/docs/{rel_core}" if rel_core else (meta.get("doc_url") or None)

    # 4) 안전 보정: 중복/오접두 정리
    if url:
        url = url.replace("/static/docs/public/", "/static/docs/")
        url = url.replace("/static/docs/static/docs/", "/static/docs/")

    # 5) 페이지 정보 캐스팅
    def _to_int(v):
        try:
            return int(v) if v is not None else None
        except Exception:
            return None

    p_start = _to_int(meta.get("page_start"))
    p_end = _to_int(meta.get("page_end"))

    # 이미지 메타데이터
    has_image = meta.get("has_image")
    if isinstance(has_image, str):
        has_image = has_image.lower() == "true"
    else:
        has_image = bool(has_image)

    return ChunkOut(
        chunk_id=chunk_id,
        content=content,
        doc_id=meta.get("doc_id"),
        doc_type=meta.get("doc_type"),
        doc_title=meta.get("doc_title"),
        doc_url=url,
        visibility=meta.get("visibility"),
        doc_relpath=rel_norm,  # 정규화 값 그대로
        tags=_restore_tags_list(meta),
        page_start=p_start,
        page_end=p_end,
        # 이미지 메타데이터
        has_image=has_image,
        image_type=meta.get("image_type"),
        image_url=meta.get("image_url"),
    )


def _restore_tags_list(meta: Dict[str, Any]) -> List[str]:
    if "tags_json" in meta and isinstance(meta["tags_json"], str):
        try:
            import json

            arr = json.loads(meta["tags_json"]) or []
            if isinstance(arr, list):
                return [str(x) for x in arr]
        except Exception:
            pass
    if "tags" in meta and isinstance(meta["tags"], str):
        return [t.strip() for t in meta["tags"].split(",") if t.strip()]
    return []


async def retrieve(
    question: str, tags: Optional[List[str]] = None, k: int = 5
) -> List[ScoredChunk]:
    # 1) 쿼리 임베딩 (비동기 - 동시성 제어 포함)
    q_vec = await embed_query_async(question)

    # 2) Chroma 질의
    raw = query_by_embedding(
        q_vec,
        n_results=max(k * 2, 10),
        where={"visibility": {"$in": ["org", "public"]}},
    )  # :contentReference[oaicite:3]{index=3}

    docs_rows = raw.get("documents", []) or []
    metas_rows = raw.get("metadatas", []) or []
    dists_rows = raw.get("distances", []) or []
    if not docs_rows:
        return []

    docs = docs_rows[0] if len(docs_rows) > 0 else []
    metas = metas_rows[0] if len(metas_rows) > 0 else []
    dists = dists_rows[0] if len(dists_rows) > 0 else []

    # [NEW] 2.5) 후보 chunk_id들을 모아서 파일 기반 부스트 맵을 한 번에 조회
    chunk_ids: List[str] = []
    for i, meta in enumerate(metas):
        m = meta or {}
        cid = (
            m.get("chunk_id") or f"chunk_{i:04d}"
        )  # ids 미포함 환경 폴백 :contentReference[oaicite:4]{index=4}
        chunk_ids.append(cid)
    boost_map = get_boost_map(
        chunk_ids, query_tags=tags
    )  # 파일 기반 factor 조회 :contentReference[oaicite:5]{index=5}

    # 3) 재랭크
    candidates: List[tuple[ScoredChunk, float]] = []
    for i, (doc, meta, dist) in enumerate(zip(docs, metas, dists)):
        meta = meta or {}
        cid = meta.get("chunk_id") or f"chunk_{i:04d}"

        sim = _similarity_from_distance(
            dist
        )  # 0~1 유사도 :contentReference[oaicite:6]{index=6}
        ff_meta = _feedback_factor(
            meta
        )  # 메타 기반 폴백 계산 :contentReference[oaicite:7]{index=7}
        ff = float(boost_map.get(cid, ff_meta))  # [NEW] 파일기반 factor 우선 적용
        tb = _tag_boost(
            meta, tags
        )  # 태그 교집합 부스트 :contentReference[oaicite:8]{index=8}
        final = sim * ff * tb

        chunk = _to_chunk_out(chunk_id=cid, content=doc, meta=meta)
        #chunk.focus_sentence = _pick_focus_sentence(question, chunk.content)
        candidates.append(
            (ScoredChunk(chunk=chunk, score=final), final)
        )  # ScoredChunk는 score→final_score 자동 승격 :contentReference[oaicite:9]{index=9}

        logger.debug(
            "[retrieve] cid=%s score=%.3f doc=%s",
            cid,
            final,
            chunk.doc_title,
        )

    candidates.sort(key=lambda x: x[1], reverse=True)
    return [sc for sc, _ in candidates[:k]]


# ====================================================================
# Phase 2: Multi-Query Retrieval (GAR 파이프라인)
# ====================================================================


async def retrieve_multi_query(
    queries: List[str],
    k_per_query: int = 10,
    tags: Optional[List[str]] = None,
    where_filter: Optional[dict] = None,
    diversify: bool = True,
) -> List[ScoredChunk]:
    """
    다단계 검색: 여러 쿼리로 검색 후 병합 (GAR Phase 2)

    전략:
    1. 각 쿼리별로 k_per_query개씩 검색
    2. 쿼리 순서에 따른 가중치 적용 (첫 쿼리=원본이 가장 중요)
    3. 중복 청크 스코어 합산 (여러 쿼리에서 나오면 중요)
    4. 다양성 보정 (같은 문서에서 너무 많이 선택 방지)
    5. 정규화 및 정렬

    Args:
        queries: 확장된 쿼리 리스트 (첫 번째가 원본)
        k_per_query: 쿼리당 검색 개수 (기본 10)
        tags: 쿼리 태그 (기존 호환)
        where_filter: ChromaDB where 필터 (doc_filter.py에서 생성)
        diversify: 다양성 보정 여부 (기본 True)

    Returns:
        병합 및 재정렬된 ScoredChunk 리스트

    Example:
        >>> queries = ["2024년 연차", "2024년 휴가 일수", "신입사원 연차"]
        >>> results = await retrieve_multi_query(
        ...     queries=queries,
        ...     k_per_query=10,
        ...     tags=["vacation", "2024"],
        ...     where_filter={"tags": {"$contains": "vacation"}},
        ... )
        >>> len(results)  # 최대 10개 반환
        10
    """
    logger.debug(f"[multi_query] 시작: {len(queries)}개 쿼리")

    all_results: Dict[str, Tuple[ScoredChunk, float]] = {}  # chunk_id → (chunk, score)

    # Step 1: 각 쿼리별로 검색 (P1-1: 병렬화)
    # 임베딩 생성을 병렬로 처리 (비동기 API 사용 - 동시성 제어 포함)
    from app.services.embedding import embed_query_parallel

    # 모든 쿼리의 임베딩을 병렬로 생성
    query_vectors = await embed_query_parallel(queries)

    # 각 쿼리별로 검색
    for i, (query, q_vec) in enumerate(zip(queries, query_vectors)):
        # 쿼리 순서에 따른 가중치 (첫 쿼리=원본이 가장 중요)
        query_weight = 1.0 - (i * 0.1)  # 1.0, 0.9, 0.8, 0.7
        if query_weight < 0.5:
            query_weight = 0.5  # 최소 0.5

        logger.debug(
            "[retrieve_multi_query] 쿼리 %d/%d (weight=%.2f): %r",
            i + 1,
            len(queries),
            query_weight,
            query,
        )

        # ChromaDB 검색
        raw = query_by_embedding(
            q_vec,
            n_results=k_per_query,
            where=where_filter or {"visibility": {"$in": ["org", "public"]}},
        )

        # 결과 파싱 (기존 retrieve() 로직 재사용)
        docs_rows = raw.get("documents", []) or []
        metas_rows = raw.get("metadatas", []) or []
        dists_rows = raw.get("distances", []) or []

        if not docs_rows:
            logger.debug("[retrieve_multi_query] 쿼리 %d: 결과 없음", i + 1)
            continue

        docs = docs_rows[0] if len(docs_rows) > 0 else []
        metas = metas_rows[0] if len(metas_rows) > 0 else []
        dists = dists_rows[0] if len(dists_rows) > 0 else []

        # Step 2: 각 결과에 대해 스코어 계산 및 병합
        for j, (doc, meta, dist) in enumerate(zip(docs, metas, dists)):
            meta = meta or {}
            cid = meta.get("chunk_id") or f"chunk_{j:04d}"

            # 스코어 계산 (기존 retrieve() 로직 재사용)
            sim = _similarity_from_distance(dist)
            ff = _feedback_factor(meta)
            tb = _tag_boost(meta, tags)
            base_score = sim * ff * tb

            # 쿼리 가중치 적용
            weighted_score = base_score * query_weight

            if cid in all_results:
                # 중복: 스코어 합산 (여러 쿼리에서 나오면 더 중요)
                existing_chunk, existing_score = all_results[cid]
                all_results[cid] = (existing_chunk, existing_score + weighted_score)
                logger.debug(
                    "[retrieve_multi_query] 중복 청크: %s (기존=%.4f, 추가=%.4f, 합=%.4f)",
                    cid,
                    existing_score,
                    weighted_score,
                    existing_score + weighted_score,
                )
            else:
                # 신규
                chunk = _to_chunk_out(chunk_id=cid, content=doc, meta=meta)
                scored_chunk = ScoredChunk(
                    chunk=chunk,
                    final_score=weighted_score,
                    similarity=sim,
                    reasons=[f"query_{i}"],  # 어떤 쿼리에서 나왔는지 기록
                )
                all_results[cid] = (scored_chunk, weighted_score)

    # Step 3: 스코어 정규화 (0~1 범위)
    chunks_and_scores = list(all_results.values())
    if not chunks_and_scores:
        logger.warning("[retrieve_multi_query] 모든 쿼리에서 결과 없음")
        return []

    max_score = max(score for _, score in chunks_and_scores)
    normalized_chunks = []
    for chunk, score in chunks_and_scores:
        # max_score가 0이면 모든 청크에 1.0 부여
        chunk.final_score = score / max_score if max_score > 0 else 1.0
        normalized_chunks.append(chunk)

    logger.debug(f"[multi_query] 병합: {len(normalized_chunks)}개 고유 청크")

    # Step 4: 다양성 보정 (같은 문서에서 너무 많이 선택 방지)
    if diversify:
        normalized_chunks = _diversify_results(normalized_chunks, max_per_doc=3)

    # Step 5: 정렬 및 상위 k개 반환
    normalized_chunks.sort(key=lambda c: c.final_score or 0.0, reverse=True)
    result = normalized_chunks[:k_per_query]

    logger.debug(f"[multi_query] 완료: {len(result)}개 반환")

    return result


def _diversify_results(
    chunks: List[ScoredChunk],
    max_per_doc: int = 3,
) -> List[ScoredChunk]:
    """
    같은 문서에서 너무 많이 선택되지 않도록 조정

    Args:
        chunks: ScoredChunk 리스트 (스코어 순 정렬 권장)
        max_per_doc: 같은 문서에서 최대 선택 개수

    Returns:
        다양성 보정된 ScoredChunk 리스트
    """
    doc_counts: Dict[str, int] = {}
    diversified = []

    for chunk in sorted(chunks, key=lambda c: c.final_score or 0.0, reverse=True):
        doc_id = chunk.chunk.doc_id

        if doc_counts.get(doc_id, 0) < max_per_doc:
            diversified.append(chunk)
            doc_counts[doc_id] = doc_counts.get(doc_id, 0) + 1

    logger.debug(
        "[_diversify_results] %d개 → %d개 (문서별 최대 %d개)",
        len(chunks),
        len(diversified),
        max_per_doc,
    )
    return diversified

