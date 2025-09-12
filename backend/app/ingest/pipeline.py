from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

from app.models.schemas import Chunk
from app.services.embedding import embed_texts
from app.vectorstore.store import upsert_chunks
from app.services.storage import UPLOADS_DIR, publish_doc
from app.ingest.detect import detect_type
from app.ingest.chunkers import merge_blocks_to_chunks
from app.ingest.jobs import job_store
from app.services.logging import get_logger
from app.ingest.tagger import tag_query

# parsers
from app.ingest.parsers.pdf import parse_pdf
from app.ingest.parsers.docx import parse_docx
from app.ingest.parsers.txt import parse_txt
from app.ingest.parsers.html import parse_html

log = get_logger("app.ingest.pipeline")


async def process_job(
    job_id: str,
    *,
    default_doc_type: str | None = None,
    visibility: str = "org",
) -> None:
    """
    UPLOADS_DIR / job_id 하위의 파일들을 순회하며 인덱싱 파이프라인 실행.
    - router에서 job_store.start(job_id, total=accepted)를 호출해 둔 상태를 기대.
    """
    job_dir = UPLOADS_DIR / job_id
    files = sorted([p for p in job_dir.glob("*") if p.is_file()])
    log.info("process start job_id=%s files=%d dir=%s", job_id, len(files), job_dir)

    if not files:
        job_store.finish(job_id)
        log.warning("no files found for job_id=%s", job_id)
        return

    for file_path in files:
        try:
            log.info("processing job_id=%s file=%s", job_id, file_path.name)

            # 1) Parse
            blocks = _parse_by_type(file_path)
            if not blocks:
                job_store.add_error(job_id, f"{file_path.name}: no text extracted")
                job_store.inc(job_id)
                continue
            chars = sum(len(b) for b in blocks)
            log.info(
                "parsed file=%s blocks=%d chars=%d", file_path.name, len(blocks), chars
            )

            # 1.5) 문서 공개 & URL 확보 (공간 절약을 위해 move 전략)
            try:
                _, doc_url = publish_doc(file_path, strategy="move")
                log.info("published doc file=%s url=%s", file_path.name, doc_url)
            except Exception as e:
                doc_url = None
                log.warning("publish_doc failed file=%s err=%s", file_path.name, e)

            # 2) Chunk
            chunks_text = merge_blocks_to_chunks(blocks)
            avg_len = sum(len(c) for c in chunks_text) / max(1, len(chunks_text))
            log.info(
                "chunked file=%s chunks=%d avg_len=%.1f",
                file_path.name,
                len(chunks_text),
                avg_len,
            )
            if not chunks_text:
                job_store.add_error(job_id, f"{file_path.name}: no chunks after merge")
                job_store.inc(job_id)
                continue

            # 3) Metadata & tags
            stem = file_path.stem
            doc_id = f"doc_{stem}"

            base_tags: List[str] = []
            name_lower = stem.lower()
            if any(k in name_lower for k in ["연차", "휴가", "leave"]):
                base_tags.extend(["hr-policy", "leave-policy"])
            if any(k in name_lower for k in ["overtime", "야근", "초과근무"]):
                base_tags.extend(["hr-policy", "overtime"])

            try:
                gen_tags = await tag_query(stem, max_tags=6)
            except Exception as e:
                log.debug("tagger failed file=%s err=%s", file_path.name, e)
                gen_tags = []

            tags = list({*(base_tags or []), *(gen_tags or [])}) or ["hr-policy"]
            log.debug("tags file=%s tags=%s", file_path.name, tags)

            # 4) Build Chunk objects (doc_url 포함)
            chunks: List[Chunk] = []
            for i, text in enumerate(chunks_text, start=1):
                chunks.append(
                    Chunk(
                        doc_id=doc_id,
                        chunk_id=f"{doc_id}_{i:04d}",
                        doc_type=default_doc_type or "policy-manual",
                        tags=tags,
                        content=text,
                        visibility=visibility,
                        doc_title=stem,
                        doc_url=doc_url,
                    )
                )
            log.info("built chunks file=%s count=%d", file_path.name, len(chunks))
            if not chunks:
                job_store.add_error(job_id, f"{file_path.name}: no chunks built")
                job_store.inc(job_id)
                continue

            # 5) Embed + Upsert
            embs = embed_texts([c.content for c in chunks])
            dim = len(embs[0]) if embs and len(embs) > 0 else -1
            log.info("embedded file=%s vecs=%d dim≈%s", file_path.name, len(embs), dim)

            upsert_chunks(chunks, embeddings=embs)
            log.info("upserted file=%s chunks=%d", file_path.name, len(chunks))

            # 진행 수치 업데이트
            job_store.inc(job_id)

        except Exception as e:
            # Traceback 포함 로그 + 상태 저장
            log.exception("exception job_id=%s file=%s", job_id, file_path.name)
            job_store.add_error(job_id, f"{file_path.name}: {e!s}")

    job_store.finish(job_id)
    log.info("process done job_id=%s", job_id)
    # cleanup: 빈 업로드 디렉터리 제거
    try:
        if job_dir.exists() and not any(job_dir.iterdir()):
            job_dir.rmdir()
    except Exception:
        pass


# ---------- 간이 업서트 (원시 텍스트) ----------
def quick_upsert_plaintext(
    *,
    doc_id: str,
    title: str,
    text: str,
    doc_type: str = "policy-manual",
    visibility: str = "org",
    tags: Iterable[str] | None = None,
    doc_url: str | None = None,
) -> int:
    """
    단일 대용량 텍스트를 청크로 쪼개 즉시 벡터DB에 업서트. (동기)
    """
    blocks = [b for b in text.splitlines() if b.strip()]
    chunks_text = merge_blocks_to_chunks(blocks)

    if not chunks_text:
        log.warning("quick_upsert_plaintext: no chunks for doc_id=%s", doc_id)
        return 0

    tags = list(tags or []) or ["hr-policy"]
    chunks: List[Chunk] = []
    for i, c in enumerate(chunks_text, start=1):
        chunks.append(
            Chunk(
                doc_id=doc_id,
                chunk_id=f"{doc_id}_{i:04d}",
                doc_type=doc_type,
                tags=tags,
                content=c,
                visibility=visibility,
                doc_title=title,
                doc_url=doc_url,
            )
        )

    embs = embed_texts([c.content for c in chunks])
    dim = len(embs[0]) if embs and len(embs) > 0 else -1
    upsert_chunks(chunks, embeddings=embs)

    log.info(
        "quick_upsert_plaintext: upserted doc_id=%s chunks=%d dim≈%s",
        doc_id,
        len(chunks),
        dim,
    )
    return len(chunks)


# ---------- 파일 타입별 파서 선택 ----------
def _parse_by_type(file_path: Path) -> List[str]:
    ftype = detect_type(file_path)
    log.debug("detect type file=%s type=%s", file_path.name, ftype)
    try:
        if ftype == "pdf":
            return parse_pdf(file_path)
        if ftype == "docx":
            return parse_docx(file_path)
        if ftype == "txt":
            return parse_txt(file_path)
        if ftype == "html":
            return parse_html(file_path)
        # unknown: 텍스트로 시도
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        return [b.strip() for b in text.splitlines() if b.strip()]
    except Exception as e:
        log.warning("parse failed type=%s file=%s err=%s", ftype, file_path.name, e)
        return []
