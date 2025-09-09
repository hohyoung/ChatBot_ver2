# backend/app/vectorstore/store.py
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Dict, Any, Optional
import json
import chromadb
from chromadb.config import Settings

from app.config import settings
from app.services.logging import get_logger

log = get_logger("app.vectorstore.store")

# ---- 모듈 전역 싱글톤 핸들 (lazy-init) ----
_client: Optional[chromadb.PersistentClient] = None
_collection = None

# 경로 & 컬렉션 이름
_PERSIST_DIR = Path(settings.chroma_persist_dir)
_COLLECTION_NAME = settings.collection_name


def _get_or_create_collection():
    """
    클라이언트/컬렉션을 1회만 생성해 재사용.
    - Chroma HNSW space를 'cosine'으로 명시
    - import 시점 초기화 대신 실제 사용 시점에 초기화 → 설정/경로 문제 감소
    """
    global _client, _collection

    if _client is None:
        _PERSIST_DIR.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=str(_PERSIST_DIR), settings=Settings(allow_reset=False)
        )

    if _collection is None:
        _collection = _client.get_or_create_collection(
            name=_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        log.info(
            "chroma collection ready: name=%s path=%s", _COLLECTION_NAME, _PERSIST_DIR
        )

    return _collection


# 과거 스니펫 호환용 별칭 (내가 예시로 썼던 이름)
_ensure_collection = _get_or_create_collection


# 외부에서 쓸 공식 접근자
def get_collection():
    return _get_or_create_collection()


def sanitize_metadata(meta: Dict[str, Any]) -> Dict[str, Any]:
    """
    Chroma는 metadata 값으로 str/int/float/bool/None 만 허용.
    그 외(list/dict 등)는 문자열로 평탄화하고, *_json 키로 원본 JSON도 함께 저장.
    """
    out: Dict[str, Any] = {}
    for k, v in meta.items():
        if isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = v
            continue

        if isinstance(v, (list, tuple, set)):
            try:
                arr = list(v)
                out[k] = ",".join(str(x) for x in arr)  # 간단 검색용
                out[f"{k}_json"] = json.dumps(arr, ensure_ascii=False)
            except Exception:
                out[k] = str(v)
            continue

        if isinstance(v, dict):
            try:
                out[f"{k}_json"] = json.dumps(v, ensure_ascii=False)
            except Exception:
                out[k] = str(v)
            continue

        out[k] = str(v)
    return out


def upsert_chunks(chunks: Iterable, embeddings: List[List[float]]) -> None:
    """
    chunks: ChunkIn 리스트 (chunk_id, content, doc_id, doc_type, doc_title, visibility, tags ...)
    embeddings: 각 chunk에 대응하는 2D 리스트
    """
    col = _get_or_create_collection()

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

        md = {
            "chunk_id": getattr(c, "chunk_id", None),

            "doc_id": getattr(c, "doc_id", None),
            "doc_type": getattr(c, "doc_type", None),
            "doc_title": getattr(c, "doc_title", None),
            "visibility": getattr(c, "visibility", None),
            "tags": getattr(c, "tags", None),

            "fb_pos": int(getattr(c, "fb_pos", 0) or 0),
            "fb_neg": int(getattr(c, "fb_neg", 0) or 0),
        }
        metadatas.append(
            sanitize_metadata({k: v for k, v in md.items() if v is not None})
        )

    col.upsert(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        embeddings=embeddings if embeddings else None,
    )
    log.info("chroma upsert ok: count=%d collection=%s", len(ids), _COLLECTION_NAME)


def _as_query_embeddings(v):
    """
    v가 1개 벡터(1D)면 [v]로, 이미 배치(2D)면 그대로 반환.
    """
    if isinstance(v, (list, tuple)) and v and isinstance(v[0], (list, tuple)):
        return v  # 2D
    return [v]  # 1D → 2D


def query_by_embedding(
    query_embedding,
    *,
    n_results: int = 5,
    where: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    col = _get_or_create_collection()
    query_embeddings = _as_query_embeddings(query_embedding)
    res = col.query(
        query_embeddings=query_embeddings,
        n_results=n_results,
        where=where or {},
        include=[
            
            "documents",
            "metadatas",
            "distances",
        ],  
    )
    return res


def query_by_embeddings(
    query_embeddings,
    *,
    n_results: int = 5,
    where: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    # 여러 쿼리 벡터 지원
    col = _get_or_create_collection()
    res = col.query(
        query_embeddings=_as_query_embeddings(query_embeddings),
        n_results=n_results,
        where=where or {},
        include=[ "documents", "metadatas", "distances"],
    )
    return res


# (선택) 간단한 피드백 누적 API — 나중에 라우터에서 호출해 사용
def increment_feedback(chunk_id: str, positive: bool) -> None:
    """
    특정 chunk 메타데이터의 fb_pos/fb_neg 카운터를 +1.
    """
    col = _get_or_create_collection()
    # 현재 메타 조회
    res = col.get(ids=[chunk_id], include=["metadatas"])
    if not res or not res.get("ids"):
        log.warning("increment_feedback: chunk_id not found: %s", chunk_id)
        return

    meta = (res["metadatas"][0] or {}) if res["metadatas"] else {}
    fb_pos = int(meta.get("fb_pos", 0) or 0)
    fb_neg = int(meta.get("fb_neg", 0) or 0)

    if positive:
        fb_pos += 1
    else:
        fb_neg += 1

    new_meta = {**meta, "fb_pos": fb_pos, "fb_neg": fb_neg}
    col.update(ids=[chunk_id], metadatas=[sanitize_metadata(new_meta)])
    log.info("feedback updated: %s -> fb_pos=%d fb_neg=%d", chunk_id, fb_pos, fb_neg)
