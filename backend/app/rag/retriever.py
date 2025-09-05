from __future__ import annotations

from typing import List, Dict, Any
from app.services.embedding import embed_texts
from app.vectorstore.store import query_by_embeddings
from app.models.schemas import Chunk, ScoredChunk  # 경로 수정!
from app.services.logging import get_logger

log = get_logger("app.rag.retriever")


def _similarity_from_distance(d: float | None) -> float | None:
    if d is None:
        return None
    try:
        d = float(d)
    except Exception:
        return None
    # cosine distance ~ [0, 2] 가정 → 간단 변환
    return max(0.0, 1.0 - min(1.0, d))


async def retrieve(
    question: str, tags: List[str] | None = None, k: int = 5
) -> List[ScoredChunk]:
    # 1) 질문 임베딩
    q_vec = embed_texts([question])[0]

    # 2) 접근 가능한 문서 필터
    where: Dict[str, Any] = {"$or": [{"visibility": "org"}, {"visibility": "public"}]}

    # 3) 벡터 검색
    res = query_by_embeddings(q_vec, n_results=max(10, k), where=where)

    ids = (res.get("ids") or [[]])[0]
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]

    out: List[ScoredChunk] = []

    # ScoredChunk가 실제로 갖고 있는 필드 확인 (pydantic v2)
    sc_fields = set(ScoredChunk.model_fields.keys())

    for i, cid in enumerate(ids):
        meta: Dict[str, Any] = metas[i] if i < len(metas) else {}
        content = docs[i] if i < len(docs) else ""
        dist = float(dists[i]) if i < len(dists) and dists[i] is not None else None

        # tags 문자열 → 리스트 복원
        raw_tags = meta.get("tags")
        if isinstance(raw_tags, str):
            tag_list = [t.strip() for t in raw_tags.split(",") if t.strip()]
        elif isinstance(raw_tags, list):
            tag_list = [str(t) for t in raw_tags]
        else:
            tag_list = []

        chunk = Chunk(
            chunk_id=cid,
            doc_id=meta.get("doc_id"),
            doc_type=meta.get("doc_type"),
            doc_title=meta.get("doc_title"),
            tags=tag_list,
            visibility=meta.get("visibility"),
            content=content,
        )

        sc_kwargs: Dict[str, Any] = {"chunk": chunk}
        # 있는 필드만 넣기
        if "distance" in sc_fields:
            sc_kwargs["distance"] = dist
        sim = _similarity_from_distance(dist)
        if "similarity" in sc_fields:
            sc_kwargs["similarity"] = sim
        if "score" in sc_fields:
            sc_kwargs["score"] = (
                sim  # score를 쓰는 스키마라면 similarity 개념을 그대로 전달
            )

        out.append(ScoredChunk(**sc_kwargs))

    # 정렬 기준: score > similarity > (1 - distance)
    def sort_key(sc: ScoredChunk) -> float:
        if "score" in sc_fields:
            v = getattr(sc, "score", None)
            if isinstance(v, (int, float)):
                return float(v)
        if "similarity" in sc_fields:
            v = getattr(sc, "similarity", None)
            if isinstance(v, (int, float)):
                return float(v)
        if "distance" in sc_fields:
            v = getattr(sc, "distance", None)
            if isinstance(v, (int, float)):
                return 1.0 - max(0.0, min(1.0, float(v)))
        return 0.0

    out.sort(key=sort_key, reverse=True)
    return out[:k]
