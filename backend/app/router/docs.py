from __future__ import annotations
import asyncio
import re
from typing import List, Optional
from fastapi import (
    APIRouter,
    Path,
    UploadFile,
    File,
    Form,
    Depends,
    HTTPException,
    status,
    Request,
    Query,
)
from pypdf import PdfReader
from app.services.idgen import new_id
from app.services.storage import save_batch, delete_files_by_relpaths, DOCS_DIR
from app.models.schemas import UploadDocsResponse, IngestJobStatus, AuthUser
from app.ingest.jobs import job_store
from app.ingest.pipeline import process_job
from app.services.logging import get_logger
from app.router.auth import current_user
from app.services.security import has_upload_permission
from urllib.parse import unquote, quote, urlparse
from pathlib import Path, Path as PPath

# ✅ 벡터스토어/피드백 유틸 임포트 (내 문서 기능)
from app.vectorstore.store import list_docs_by_owner, delete_doc_for_owner
from app.services.feedback_store import delete_many as feedback_delete_many

log = get_logger("app.router.docs")
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

    job_id = new_id("ingest")
    accepted, skipped, saved = save_batch(job_id, files)

    log.info(
        "upload received job_id=%s accepted=%d skipped=%d doc_type=%s visibility=%s files=%s",
        job_id,
        accepted,
        skipped,
        doc_type,
        visibility,
        [p.name for p in saved],
    )

    job_store.start(job_id, total=accepted)

    asyncio.create_task(
        process_job(
            job_id,
            default_doc_type=doc_type,
            visibility=visibility,
            owner_id=int(user.id),
            owner_username=user.username,
        )
    )

    return UploadDocsResponse(job_id=job_id, accepted=accepted, skipped=skipped)


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

    # 2) 실제 파일 삭제 (relpath 우선)
    rels = [r for r in (result.get("doc_relpaths") or []) if r]
    stats = {"requested": 0, "deleted": 0, "errors": []}
    if rels:
        stats = delete_files_by_relpaths(rels)

    # 3) (폴백) 과거 데이터: URL만 있는 경우 public/<name> 삭제 시도
    if (not rels) and (result.get("doc_urls")):

        fallbacks = []
        for u in result["doc_urls"]:
            # /static/docs/<name> → public/<name>
            try:
                name = u.rsplit("/", 1)[-1]
                fallbacks.append(str(PPath("public") / name))
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
                filename = PPath(unquote(path_part)).name
            except Exception as e:
                log.warning("[LOCATE] parse in_url failed: %s", e)
                filename = PPath(unquote(in_url)).name
        elif in_rel and str(in_rel).startswith("public/"):
            filename = PPath(str(in_rel)).name

        if not filename:
            log.warning("[LOCATE] no filename resolved -> return nulls")
            return {"page": None, "url": None}

        # 3) 실제 파일 경로 & 절대 URL
        pdf_path = PPath(DOCS_DIR) / filename
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
