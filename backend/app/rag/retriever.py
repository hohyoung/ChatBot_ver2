# backend/app/rag/retriever.py
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.services.embedding import embed_query
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


def _to_chunk_out(
    chunk_id: str,
    content: str,
    meta: Dict[str, Any],
) -> ChunkOut:
    return ChunkOut(
        chunk_id=chunk_id,
        content=content,
        doc_id=meta.get("doc_id"),
        doc_type=meta.get("doc_type"),
        doc_title=meta.get("doc_title"),
        visibility=meta.get("visibility"),
        # 응답은 list가 기대되므로 tags_json → list 복원 시도, 없으면 CSV 분해
        tags=_restore_tags_list(meta),
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
    # 1) 쿼리 임베딩
    q_vec = embed_query(question)

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
        candidates.append(
            (ScoredChunk(chunk=chunk, score=final), final)
        )  # ScoredChunk는 score→final_score 자동 승격 :contentReference[oaicite:9]{index=9}

        logger.info(
            "[retrieve] cid=%s sim=%.4f ff=%.4f tb=%.4f score=%.4f tags=%s doc=%s",
            cid,
            sim,
            ff,
            tb,
            final,
            tags,
            chunk.doc_title,
        )

    candidates.sort(key=lambda x: x[1], reverse=True)
    return [sc for sc, _ in candidates[:k]]
