from __future__ import annotations

from typing import Iterable, List, Dict, Any
import json
import chromadb
from app.config import settings
from app.services.logging import get_logger

log = get_logger("app.vectorstore.store")

# Chroma 클라이언트 & 컬렉션 준비
_client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
_collection = _client.get_or_create_collection(name=settings.collection_name)


def sanitize_metadata(meta: Dict[str, Any]) -> Dict[str, Any]:
    """
    Chroma는 metadata 값으로 str/int/float/bool/None 만 허용.
    그 외(list/dict 등)는 문자열로 평탄화하고, *_json 키로 원본 JSON도 함께 저장.
    """
    out: Dict[str, Any] = {}
    for k, v in meta.items():
        # 허용 타입 그대로
        if isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = v
            continue

        # list/tuple/set → CSV + *_json
        if isinstance(v, (list, tuple, set)):
            try:
                arr = list(v)
                out[k] = ",".join(str(x) for x in arr)  # 간단 검색용
                out[f"{k}_json"] = json.dumps(arr, ensure_ascii=False)
            except Exception:
                out[k] = str(v)
            continue

        # dict → *_json
        if isinstance(v, dict):
            try:
                out[f"{k}_json"] = json.dumps(v, ensure_ascii=False)
                # 키 자체에도 넣고 싶다면 아래 라인 활성화:
                # out[k] = out[f"{k}_json"]
            except Exception:
                out[k] = str(v)
            continue

        # 기타 타입 → 문자열
        out[k] = str(v)
    return out


def upsert_chunks(chunks: Iterable, embeddings: List[List[float]]) -> None:
    chunks_list = list(chunks)
    if not chunks_list:
        log.warning("upsert_chunks: no chunks")
        return

    if embeddings and len(embeddings) != len(chunks_list):
        raise ValueError(
            f"embeddings length {len(embeddings)} != chunks {len(chunks_list)}"
        )

    ids: List[str] = []
    documents: List[str] = []
    metadatas: List[Dict[str, Any]] = []

    for c in chunks_list:
        ids.append(c.chunk_id)
        documents.append(c.content)
        metadatas.append(
            sanitize_metadata(
                {
                    "doc_id": c.doc_id,
                    "doc_type": c.doc_type,
                    "tags": c.tags,  # ← 여기서 list→CSV & tags_json 저장
                    "visibility": c.visibility,
                    "doc_title": getattr(c, "doc_title", None),
                }
            )
        )

    _collection.upsert(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        embeddings=embeddings if embeddings else None,
    )
    log.info(
        "chroma upsert ok: count=%d collection=%s", len(ids), settings.collection_name
    )


def query_by_embedding(
    query_embedding,
    *,
    n_results: int = 5,
    where: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    query_embeddings = _as_query_embeddings(query_embedding)
    res = _collection.query(
        query_embeddings=query_embeddings,
        n_results=n_results,
        where=where or {},
        include=["documents", "metadatas", "distances"],
    )
    return res


def query_by_embeddings(
    query_embedding, *, n_results: int = 5, where: dict | None = None
):
    return query_by_embedding(query_embedding, n_results=n_results, where=where)


def _as_query_embeddings(v):
    """
    v가 1개 벡터(1D)면 [v]로, 이미 배치(2D)면 그대로 반환.
    """
    # v = [] 인 경우도 안전 처리
    if isinstance(v, (list, tuple)) and v and isinstance(v[0], (list, tuple)):
        return v  # 이미 2D
    return [v]  # 1D -> 2D
