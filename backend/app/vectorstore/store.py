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
    """
    global _client, _collection

    if _client is None:
        _PERSIST_DIR.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=str(_PERSIST_DIR),
            # ✅ 텔레메트리 OFF
            settings=Settings(
                allow_reset=False,
                anonymized_telemetry=False,
            ),
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


def upsert_chunks(
    chunks: Iterable,
    embeddings: List[List[float]],
    *,
    common_metadata: Optional[
        Dict[str, Any]
    ] = None,  # ⬅ 추가: 모든 청크에 공통으로 붙일 메타
) -> None:
    """
    chunks: ChunkIn 리스트 (chunk_id, content, doc_id, doc_type, doc_title, visibility, tags ...)
    embeddings: 각 chunk에 대응하는 2D 리스트
    common_metadata: 각 청크 메타에 일괄 병합될 공통 메타(e.g. uploaded_at)
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

        # ✅ 페이지 정보 포함(정수 캐스팅). 비-PDF의 경우 None → 메타에서 자동 제외.
        page_start = getattr(c, "page_start", None)
        page_end = getattr(c, "page_end", None)
        try:
            page_start = int(page_start) if page_start is not None else None
        except Exception:
            page_start = None
        try:
            page_end = int(page_end) if page_end is not None else None
        except Exception:
            page_end = None

        md = {
            "chunk_id": getattr(c, "chunk_id", None),
            "doc_id": getattr(c, "doc_id", None),
            "doc_type": getattr(c, "doc_type", None),
            "doc_title": getattr(c, "doc_title", None),
            "doc_url": getattr(c, "doc_url", None),
            "doc_relpath": getattr(c, "doc_relpath", None),
            "visibility": getattr(c, "visibility", None),
            "tags": getattr(c, "tags", None),
            "doc_hash": getattr(c, "doc_hash", None),
            "owner_id": (
                None
                if getattr(c, "owner_id", None) is None
                else str(getattr(c, "owner_id"))
            ),
            "owner_username": getattr(c, "owner_username", None),
            "fb_pos": int(getattr(c, "fb_pos", 0) or 0),
            "fb_neg": int(getattr(c, "fb_neg", 0) or 0),
            # ⬇⬇⬇ 중요: 페이지 정보 저장
            "page_start": page_start,
            "page_end": page_end,
        }

        # 공통 메타(예: uploaded_at) 병합
        if common_metadata:
            md.update(common_metadata)

        # None 값은 제외(비-PDF의 page_*는 드롭됨)
        metadatas.append(
            sanitize_metadata({k: v for k, v in md.items() if v is not None})
        )

    # 디버깅(선택)
    try:
        sample = [
            {k: m.get(k) for k in ("chunk_id", "page_start", "page_end", "uploaded_at")}
            for m in metadatas[:3]
        ]
        log.debug("[VECTORSTORE] upsert metas sample: %s", sample)
    except Exception:
        pass

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
        include=["documents", "metadatas", "distances"],
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


# === 필터 헬퍼 ===
def _eq(key: str, value: Any) -> Dict[str, Any]:
    return {key: {"$eq": value}}


def _and(*conds: Dict[str, Any]) -> Dict[str, Any]:
    return {"$and": list(conds)}


def doc_exists_by_hash(
    *, doc_hash: str, owner_id: Optional[int] = None, visibility: Optional[str] = None
) -> bool:
    """
    동일 내용 문서가 이미 업서트되어 있는지 확인.
    owner_id/visibility가 주어지면 같은 소유자/가시성 범위에서만 중복으로 취급.
    """
    col = get_collection()
    conds: list[Dict[str, Any]] = [_eq("doc_hash", doc_hash)]
    if owner_id is not None:
        conds.append(_eq("owner_id", str(owner_id)))
    if visibility:
        conds.append(_eq("visibility", visibility))
    res = col.get(where=_and(*conds), include=["metadatas"])
    return bool(res and res.get("ids"))


def list_docs_by_owner(owner_id: int) -> list[dict]:
    """
    owner_id로 내 문서 목록 조회.
    반환: [{doc_id, doc_title, visibility, doc_url, uploaded_at, chunk_count}, ...]
    """
    col = get_collection()
    res = col.get(
        where=_eq("owner_id", str(owner_id)),
        include=["metadatas"],
    )
    docs: dict[str, dict] = {}
    for meta in res.get("metadatas", []) or []:
        if not meta:
            continue
        did = meta.get("doc_id")
        if not did:
            continue
        d = docs.setdefault(
            did,
            {
                "doc_id": did,
                "doc_title": meta.get("doc_title"),
                "visibility": meta.get("visibility"),
                "doc_url": meta.get("doc_url"),
                "doc_relpath": meta.get("doc_relpath"),
                "chunk_count": 0,
                "_uploaded_at_min": None,  # 최초 업로드 시각 집계
            },
        )
        d["chunk_count"] += 1
        if not d.get("doc_url") and meta.get("doc_url"):
            d["doc_url"] = meta.get("doc_url")
        if not d.get("doc_relpath") and meta.get("doc_relpath"):
            d["doc_relpath"] = meta.get("doc_relpath")
        ua = meta.get("uploaded_at")
        if ua:
            if d["_uploaded_at_min"] is None or ua < d["_uploaded_at_min"]:
                d["_uploaded_at_min"] = ua

    out = []
    for v in docs.values():
        v["uploaded_at"] = v.pop("_uploaded_at_min", None)
        out.append(v)
    # 최신 업로드가 위로 오도록
    out.sort(key=lambda x: (x["uploaded_at"] or ""), reverse=True)
    return out


def delete_doc_for_owner(doc_id: str, owner_id: int) -> Dict[str, Any]:
    col = get_collection()
    res = col.get(
        where={
            "$and": [
                {"doc_id": {"$eq": str(doc_id)}},
                {"owner_id": {"$eq": str(owner_id)}},
            ]
        },
        include=["metadatas"],
    )
    ids = res.get("ids") or []
    metas = res.get("metadatas") or []
    if not ids:
        return {"deleted": 0, "chunk_ids": [], "doc_urls": [], "doc_relpaths": []}

    col.delete(ids=ids)

    urls = [m.get("doc_url") for m in metas if m and m.get("doc_url")]
    rels = [m.get("doc_relpath") for m in metas if m and m.get("doc_relpath")]

    return {
        "deleted": len(ids),
        "chunk_ids": ids,
        "doc_urls": urls,
        "doc_relpaths": rels,
    }


# 관리자용 함수
def list_all_docs() -> list[dict]:
    """
    모든 소유자의 문서를 doc_id 단위로 집계.
    ★★★ uploaded_at 필드를 포함하여 반환하도록 수정 ★★★
    """
    col = get_collection()
    res = col.get(include=["metadatas"])

    docs: dict[str, dict] = {}
    for meta in res.get("metadatas", []) or []:
        if not meta:
            continue
        did = meta.get("doc_id")
        if not did:
            continue

        d = docs.setdefault(
            did,
            {
                "doc_id": did,
                "doc_title": meta.get("doc_title"),
                "visibility": meta.get("visibility"),
                "owner_id": meta.get("owner_id"),
                "owner_username": meta.get("owner_username"),
                "doc_url": meta.get("doc_url"),
                "doc_relpath": meta.get("doc_relpath"),
                "chunk_count": 0,
                # _uploaded_at_min을 임시 필드로 사용하여 가장 오래된 시간을 추적
                "_uploaded_at_min": None,
            },
        )
        d["chunk_count"] += 1

        # ★★★ 핵심 수정: 가장 오래된 uploaded_at을 해당 문서의 대표 업로드 날짜로 사용 ★★★
        ua = meta.get("uploaded_at")
        if ua:
            if d["_uploaded_at_min"] is None or ua < d["_uploaded_at_min"]:
                d["_uploaded_at_min"] = ua

        # 대표 URL/relpath 미설정 시 최초 값 세팅
        if (not d.get("doc_url")) and meta.get("doc_url"):
            d["doc_url"] = meta.get("doc_url")
        if (not d.get("doc_relpath")) and meta.get("doc_relpath"):
            d["doc_relpath"] = meta.get("doc_relpath")

    # 최종적으로 _uploaded_at_min 값을 uploaded_at으로 옮기고 정렬
    out = []
    for v in docs.values():
        v["uploaded_at"] = v.pop("_uploaded_at_min", None)
        out.append(v)

    out.sort(key=lambda x: (x["uploaded_at"] or ""), reverse=True)
    return out


def delete_doc_any(doc_id: str) -> Dict[str, Any]:
    """
    소유자와 무관하게 특정 doc_id의 모든 청크 삭제.
    파일 삭제는 라우터에서 수행(여기서는 경로/URL만 반환).
    """
    col = get_collection()
    res = col.get(where={"doc_id": {"$eq": str(doc_id)}}, include=["metadatas"])
    ids = res.get("ids") or []
    metas = res.get("metadatas") or []
    if not ids:
        return {"deleted": 0, "chunk_ids": [], "doc_urls": set(), "doc_relpaths": set()}

    col.delete(ids=ids)
    urls = {m.get("doc_url") for m in metas if m and m.get("doc_url")}
    rels = {m.get("doc_relpath") for m in metas if m and m.get("doc_relpath")}
    return {
        "deleted": len(ids),
        "chunk_ids": ids,
        "doc_urls": urls,
        "doc_relpaths": rels,
    }
