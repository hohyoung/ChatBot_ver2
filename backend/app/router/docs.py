from __future__ import annotations
import asyncio
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Form, Header
from app.services.idgen import new_id
from app.services.storage import save_batch
from app.models.schemas import UploadDocsResponse, IngestJobStatus
from app.config import settings
from app.ingest.jobs import job_store
from app.ingest.pipeline import process_job
from app.services.logging import get_logger

log = get_logger("app.router.docs")

router = APIRouter()


@router.post("/upload", response_model=UploadDocsResponse, status_code=202)
async def upload_docs(
    files: List[UploadFile] = File(..., description="하나 이상 파일 업로드"),
    doc_type: Optional[str] = Form(None),
    visibility: str = Form("org"),
    authorization: Optional[str] = Header(default=None),
):
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

    # 잡 시작 표시 + 비동기 작업 스케줄
    job_store.start(job_id, total=accepted)
    asyncio.create_task(
        process_job(job_id, default_doc_type=doc_type, visibility=visibility)
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
