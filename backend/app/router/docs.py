from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote, unquote, urlparse

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Path as PathParam,
    Query,
    Request,
    UploadFile,
    status,
)
from pypdf import PdfReader

from app.ingest.jobs import job_store
from app.ingest.pipeline import process_job
from app.models.schemas import (
    AuthUser,
    DocSearchResponse,
    DocSearchResult,
    DocStatsResponse,
    IngestJobStatus,
    LibrarianRequest,
    LibrarianResponse,
    UploadDocsResponse,
)
from app.router.auth import current_user
from app.services.feedback_store import delete_many as feedback_delete_many
from app.services.idgen import new_id
from app.services.logging import get_logger
from app.services.security import has_upload_permission
from app.services.storage import (
    DOCS_DIR,
    delete_chunk_images_by_doc_id,
    delete_files_by_relpaths,
    save_batch,
)
from app.vectorstore.store import (
    delete_doc_for_owner,
    get_doc_stats,
    list_docs_by_owner,
    search_docs,
)

log = get_logger(__name__)
router = APIRouter()


@router.post("/upload", response_model=UploadDocsResponse, status_code=202)
async def upload_docs(
    files: List[UploadFile] = File(..., description="하나 이상 파일 업로드"),
    doc_type: Optional[str] = Form(None),
    visibility: str = Form("public"),
    user: AuthUser = Depends(current_user),
):
    if not has_upload_permission(user.security_level):
        raise HTTPException(status_code=403, detail="insufficient role for upload")

    # 팀 소속 검증: 팀에 배정된 유저만 업로드 가능
    if not user.team_id:
        raise HTTPException(
            status_code=403,
            detail="팀에 소속되어 있지 않아 문서를 업로드할 수 없습니다. 관리자에게 팀 배정을 요청하세요."
        )

    job_id = new_id("ingest")
    accepted, skipped, saved = save_batch(job_id, files)

    log.info(
        "upload received job_id=%s accepted=%d skipped=%d doc_type=%s visibility=%s team_id=%s files=%s",
        job_id,
        accepted,
        skipped,
        doc_type,
        visibility,
        user.team_id,
        [p.name for p in saved],
    )

    job_store.start(job_id, total=accepted, owner_id=int(user.id))

    asyncio.create_task(
        process_job(
            job_id,
            default_doc_type=doc_type,
            visibility=visibility,
            owner_id=int(user.id),
            owner_username=user.username,
            team_id=user.team_id,
            team_name=user.team_name,
        )
    )

    return UploadDocsResponse(job_id=job_id, accepted=accepted, skipped=skipped)


@router.get("/active-jobs")
async def get_active_jobs(user: AuthUser = Depends(current_user)):
    """
    현재 사용자의 진행 중인 업로드 작업 목록 조회.

    페이지 새로고침, 재접속, 다른 페이지 이동 후 돌아왔을 때
    진행 중인 업로드 상태를 복원하는 데 사용됩니다.
    """
    active_jobs = job_store.get_active_jobs_for_user(int(user.id))
    log.info("get_active_jobs: user_id=%s count=%d", user.id, len(active_jobs))
    return {"jobs": active_jobs}


@router.get("/{job_id}/status", response_model=IngestJobStatus)
async def ingest_status(job_id: str):
    st = job_store.get(job_id)
    log.debug(
        "status check job_id=%s status=%s processed=%s errors=%s",
        job_id,
        st.status,
        st.processed,
        st.errors,
    )
    return st


# =========================
# 내 문서: 목록/삭제
# =========================


@router.get("/my")
async def my_docs(user: AuthUser = Depends(current_user)):
    items = list_docs_by_owner(int(user.id))
    return {"items": items}


@router.delete("/my/{doc_id}")
async def delete_my_doc(doc_id: str, user: AuthUser = Depends(current_user)):
    result = delete_doc_for_owner(doc_id, int(user.id))
    deleted = int(result.get("deleted", 0))
    if deleted == 0:
        raise HTTPException(
            status_code=404, detail="문서를 찾을 수 없거나 삭제 권한이 없습니다."
        )

    # 1) 연관 피드백 삭제
    chunk_ids = result.get("chunk_ids") or []
    feedback_delete_many(chunk_ids)

    # 2) 이미지 파일 삭제
    img_stats = delete_chunk_images_by_doc_id(doc_id)
    log.info("delete_my_doc: doc_id=%s image_delete=%s", doc_id, img_stats)

    # 3) 실제 파일 삭제 (relpath 우선)
    rels = [r for r in (result.get("doc_relpaths") or []) if r]
    stats = {"requested": 0, "deleted": 0, "errors": []}
    if rels:
        stats = delete_files_by_relpaths(rels)

    # 4) (폴백) 과거 데이터: URL만 있는 경우 public/<name> 삭제 시도
    if (not rels) and (result.get("doc_urls")):

        fallbacks = []
        for u in result["doc_urls"]:
            # /static/docs/<name> → public/<name>
            try:
                name = u.rsplit("/", 1)[-1]
                fallbacks.append(str(Path("public") / name))
            except Exception:
                pass
        if fallbacks:
            fb_stats = delete_files_by_relpaths(fallbacks)
            # 간단 합산
            stats["requested"] += fb_stats["requested"]
            stats["deleted"] += fb_stats["deleted"]
            stats["errors"].extend(fb_stats["errors"])

    return {"ok": True, "deleted_chunks": deleted, "file_delete": stats}


# 청크에서 문서 탐색


def _normalize_for_match(s: str) -> str:
    # 공백/개행 제거하고 비교 (한글 PDF는 공백이 자주 끼므로)
    return re.sub(r"\s+", "", s or "")


@router.get("/locate")
def locate_in_pdf(
    request: Request,
    # ✅ alias 허용: 프론트가 url 또는 doc_url로 보낼 수 있도록
    doc_url: str | None = Query(
        None,
        alias="doc_url",
        description="absolute or relative URL like /static/docs/file.pdf",
    ),
    url: str | None = Query(None, alias="url"),
    # ✅ alias 허용: relpath 또는 doc_relpath
    doc_relpath: str | None = Query(
        None, alias="doc_relpath", description="e.g., public/file.pdf (fallback)"
    ),
    relpath: str | None = Query(None, alias="relpath"),
    q: str | None = Query(None, description="snippet to find in pdf"),
):
    """
    PDF 내에서 q 문장이 포함된 페이지를 찾아 절대 URL을 반환.
    실패해도 url은 최대한 절대경로로 돌려주며, filename 추정 실패시만 null/null.
    """
    try:
        # ---------- 입력 로그 ----------
        log.info(
            "[LOCATE] in: doc_url=%r url=%r doc_relpath=%r relpath=%r q.len=%s",
            doc_url,
            url,
            doc_relpath,
            relpath,
            (len(q) if q else 0),
        )

        # 1) 우선순위 병합
        in_url = doc_url or url
        in_rel = doc_relpath or relpath

        # 2) 파일명 복원
        filename = None
        if in_url:
            try:
                parsed = urlparse(in_url)
                path_part = parsed.path if parsed.scheme else in_url
                filename = Path(unquote(path_part)).name
            except Exception as e:
                log.warning("[LOCATE] parse in_url failed: %s", e)
                filename = Path(unquote(in_url)).name
        elif in_rel and str(in_rel).startswith("public/"):
            filename = Path(str(in_rel)).name

        if not filename:
            log.warning("[LOCATE] no filename resolved -> return nulls")
            return {"page": None, "url": None}

        # 3) 실제 파일 경로 & 절대 URL
        pdf_path = Path(DOCS_DIR) / filename
        base = str(request.base_url).rstrip("/")  # http://127.0.0.1:8000
        abs_url_base = f"{base}/static/docs/{quote(filename)}"

        log.info(
            "[LOCATE] resolved filename=%s exists=%s abs_url_base=%s",
            filename,
            pdf_path.exists(),
            abs_url_base,
        )

        # 4) 파일이 없거나 PDF가 아니면, 페이지 탐색 없이 절대 URL만 반환
        if not filename.lower().endswith(".pdf") or not pdf_path.exists():
            return {"page": None, "url": abs_url_base}

        # 5) q가 없으면 기본 URL
        target = _normalize_for_match(q or "")
        if not target:
            return {"page": None, "url": abs_url_base}

        # 6) 페이지 탐색
        with pdf_path.open("rb") as f:
            reader = PdfReader(f)
            for idx, page in enumerate(reader.pages, start=1):
                text = page.extract_text() or ""
                if target in _normalize_for_match(text):
                    out = {"page": idx, "url": f"{abs_url_base}#page={idx}"}
                    log.info("[LOCATE] hit page=%s -> %s", idx, out["url"])
                    return out

        # 7) 미스매치면 기본 URL
        log.info("[LOCATE] no hit, return base")
        return {"page": None, "url": abs_url_base}

    except Exception as e:
        log.exception("[LOCATE] error: %s", e)
        return {"page": None, "url": None}


# =========================
# P0-4: 문서 검색 및 통계
# =========================


@router.get("/search", response_model=DocSearchResponse)
async def search_documents(
    keyword: Optional[str] = Query(None, description="문서명/내용 키워드"),
    tags: Optional[str] = Query(None, description="태그 (콤마 구분)"),
    doc_type: Optional[str] = Query(None, description="문서 유형"),
    owner_username: Optional[str] = Query(None, description="업로더"),
    visibility: Optional[str] = Query(None, description="공개 범위"),
    year: Optional[int] = Query(None, description="업로드 연도"),
    limit: int = Query(50, ge=1, le=200, description="최대 결과 수"),
    offset: int = Query(0, ge=0, description="오프셋"),
    user: AuthUser = Depends(current_user),
):
    """
    문서 검색 API (필터 지원).

    쿼리 파라미터:
    - keyword: 문서 제목 키워드
    - tags: 태그 (콤마 구분, 예: "hr-policy,vacation")
    - doc_type: 문서 유형 필터
    - owner_username: 업로더 필터
    - visibility: 공개 범위 (public, org, private)
    - year: 업로드 연도 (예: 2025)
    - limit: 최대 결과 수 (기본: 50)
    - offset: 페이지네이션 오프셋 (기본: 0)
    """
    # 태그 파싱 (콤마 구분 → 리스트)
    tag_list = None
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    result = search_docs(
        keyword=keyword,
        tags=tag_list,
        doc_type=doc_type,
        owner_username=owner_username,
        visibility=visibility,
        year=year,
        limit=limit,
        offset=offset,
    )

    # DocSearchResult로 변환
    items = [DocSearchResult(**item) for item in result["items"]]

    log.info(
        "search_documents: keyword=%r tags=%r total=%d returned=%d",
        keyword,
        tag_list,
        result["total"],
        len(items),
    )

    return DocSearchResponse(
        items=items,
        total=result["total"],
        limit=limit,
        offset=offset,
    )


@router.get("/stats", response_model=DocStatsResponse)
async def document_statistics(user: AuthUser = Depends(current_user)):
    """
    전체 문서 통계 반환.

    반환:
    - total_docs: 전체 문서 수
    - total_chunks: 전체 청크 수
    - by_type: 문서 유형별 청크 수
    - by_visibility: 공개 범위별 청크 수
    - by_owner: 업로더별 청크 수
    - recent_uploads: 최근 7일 내 업로드 청크 수
    """
    stats = get_doc_stats()
    log.info("document_statistics: total_docs=%d total_chunks=%d", stats["total_docs"], stats["total_chunks"])
    return DocStatsResponse(**stats)


@router.post("/librarian", response_model=LibrarianResponse)
async def chatbot_librarian(
    request: LibrarianRequest,
    user: AuthUser = Depends(current_user),
):
    """
    챗봇 사서: 현재 업로드된 문서 중에서 사용자 요청에 가장 적합한 문서를 찾아줍니다.

    예시:
    - 문서: ["니체철학", "가고시마 맛집", "사내규정"]
    - 쿼리: "연차 신청하려고 하는데 참고할만한 문서를 찾아"
    - 응답: ["사내규정"]
    """
    import json
    from openai import OpenAI
    from app.config import settings

    log.info("librarian query: %r", request.query)

    try:
        # 1) 현재 업로드된 모든 문서 조회
        result = search_docs(limit=200)
        all_docs = result.get("items", [])

        if not all_docs:
            return LibrarianResponse(
                selected_doc_ids=[],
                selected_titles=[],
                explanation="현재 업로드된 문서가 없습니다.",
            )

        # 2) 문서 리스트 생성 (doc_id -> doc_title 매핑)
        doc_map = {}  # {doc_title: doc_id}
        doc_list = []
        for doc in all_docs:
            title = doc.get("doc_title") or doc.get("doc_id")
            doc_id = doc.get("doc_id")
            doc_map[title] = doc_id
            doc_list.append(title)

        log.info("librarian: %d documents available", len(doc_list))

        # 3) LLM에게 문서 리스트와 쿼리 전달
        from app.services.openai_client import get_client
        client = get_client()

        prompt = f"""당신은 문서를 찾아주는 사서입니다. 현재 업로드된 문서 목록과 사용자의 요청을 보고, 가장 적합한 문서를 선택하세요.

**현재 문서 목록:**
{chr(10).join(f"{i+1}. {title}" for i, title in enumerate(doc_list))}

**사용자 요청:** "{request.query}"

**지시사항:**
- 사용자 요청에 가장 적합한 문서 제목을 선택하세요 (1개 이상 가능)
- 문서 목록에 없는 제목은 선택하지 마세요
- JSON 형식으로 응답하세요: {{"selected_titles": ["제목1", "제목2"], "explanation": "선택 이유"}}

**예시:**
문서: ["니체철학", "가고시마 맛집", "사내규정"]
요청: "연차 신청하려고 하는데 참고할만한 문서를 찾아"
응답: {{"selected_titles": ["사내규정"], "explanation": "연차 신청은 사내 규정에 명시되어 있습니다."}}

JSON만 응답하세요."""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "당신은 문서를 찾아주는 사서입니다. JSON만 응답하세요."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=300,
        )

        content = response.choices[0].message.content.strip()
        log.info("librarian LLM response: %s", content)

        # 4) JSON 파싱
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()

        parsed = json.loads(content)
        selected_titles = parsed.get("selected_titles", [])
        explanation = parsed.get("explanation", "")

        # 5) 제목을 doc_id로 변환
        selected_doc_ids = []
        valid_titles = []
        for title in selected_titles:
            if title in doc_map:
                selected_doc_ids.append(doc_map[title])
                valid_titles.append(title)
            else:
                log.warning("librarian: title not found in doc_map: %r", title)

        result = LibrarianResponse(
            selected_doc_ids=selected_doc_ids,
            selected_titles=valid_titles,
            explanation=explanation or f'"{request.query}" 요청에 적합한 문서를 찾았습니다.',
        )

        log.info("librarian result: %d documents selected", len(selected_doc_ids))
        return result

    except Exception as e:
        log.exception("librarian error: %s", e)
        # 에러 시 빈 결과 반환
        return LibrarianResponse(
            selected_doc_ids=[],
            selected_titles=[],
            explanation=f"문서 검색 중 오류가 발생했습니다: {str(e)}",
        )


# ===== 디버그: 검색 테스트 =====
@router.get("/debug/search")
async def debug_search(
    q: str = Query(..., description="검색 쿼리"),
    k: int = Query(20, description="검색 개수"),
):
    """
    디버깅용: 검색 쿼리가 어떤 청크를 찾는지 확인
    벡터 유사도 점수와 함께 반환
    """
    try:
        from app.services.embedding import embed_query
        from app.vectorstore.store import query_by_embedding

        # 임베딩 생성
        q_vec = embed_query(q)

        # ChromaDB 검색
        raw = query_by_embedding(
            q_vec,
            n_results=k,
            where={"visibility": {"$in": ["org", "public"]}},
        )

        docs = raw.get("documents", [[]])[0]
        metas = raw.get("metadatas", [[]])[0]
        dists = raw.get("distances", [[]])[0]

        results = []
        for i, (doc, meta, dist) in enumerate(zip(docs, metas, dists)):
            similarity = 1.0 - (dist / 2.0)  # cosine distance (0~2) → similarity (0~1)
            results.append({
                "rank": i + 1,
                "chunk_id": meta.get("chunk_id"),
                "doc_title": meta.get("doc_title"),
                "similarity": round(similarity, 4),
                "distance": round(dist, 4),
                "content_preview": doc[:300] + "..." if len(doc) > 300 else doc,
            })

        return {
            "query": q,
            "total_results": len(results),
            "results": results,
        }

    except Exception as e:
        log.exception("debug_search error: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"검색 테스트 실패: {str(e)}"
        )


# ===== 디버그: 전체 문서 목록 조회 =====
@router.get("/debug/docs")
async def debug_list_docs():
    """
    디버깅용: ChromaDB에 저장된 모든 문서 제목 목록 조회
    """
    try:
        from app.vectorstore.store import _get_or_create_collection

        collection = _get_or_create_collection()
        results = collection.get(include=["metadatas"])

        # 문서 제목 중복 제거
        doc_titles = set()
        for meta in results["metadatas"]:
            if meta and "doc_title" in meta:
                doc_titles.add(meta["doc_title"])

        return {
            "total_documents": len(doc_titles),
            "documents": sorted(list(doc_titles))
        }
    except Exception as e:
        log.exception("debug_list_docs error: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"문서 목록 조회 실패: {str(e)}"
        )


# ===== 디버그: 문서 청크 조회 =====
@router.get("/debug/chunks/{doc_title}")
async def debug_get_chunks(
    doc_title: str = PathParam(..., description="문서 제목"),
):
    """
    디버깅용: 특정 문서의 모든 청크 조회 (인증 불필요)
    표가 어떻게 저장되었는지 확인 가능
    """
    try:
        from app.vectorstore.store import _get_or_create_collection

        collection = _get_or_create_collection()
        results = collection.get(
            where={"doc_title": doc_title},
            include=["documents", "metadatas"]
        )

        if not results["ids"]:
            raise HTTPException(
                status_code=404,
                detail=f"문서 '{doc_title}'을 찾을 수 없습니다."
            )

        chunks = []
        for chunk_id, content, meta in zip(
            results["ids"],
            results["documents"],
            results["metadatas"]
        ):
            chunks.append({
                "chunk_id": chunk_id,
                "page_start": meta.get("page_start"),
                "page_end": meta.get("page_end"),
                "tags": meta.get("tags"),
                "content": content,
            })

        return {
            "doc_title": doc_title,
            "total_chunks": len(chunks),
            "chunks": chunks,
        }

    except HTTPException:
        raise
    except Exception as e:
        log.exception("debug_get_chunks error: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"청크 조회 실패: {str(e)}"
        )
