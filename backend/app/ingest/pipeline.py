from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

from app.models.schemas import Chunk
from app.services.embedding import embed_texts
from app.vectorstore.store import upsert_chunks
from app.services.storage import UPLOADS_DIR
from app.ingest.detect import detect_type
from app.ingest.chunkers import merge_blocks_to_chunks
from app.ingest.jobs import job_store
from app.services.logging import get_logger

log = get_logger("app.ingest.pipeline")

# 태거가 없어도 동작하도록 폴백 제공
try:
    from app.ingest.tagger import tag_query
except Exception:
    async def tag_query(_: str, *, max_tags: int = 6) -> List[str]:
        return []


# ---------- 간이 업서트 (수동 텍스트를 바로 컬렉션에 넣고 싶을 때 사용) ----------
def quick_upsert_plaintext(
    doc_id: str,
    sentences: Iterable[str],
    *,
    doc_type: str = "hr-guideline",
    tags: List[str] | None = None,
    visibility: str = "org",
) -> int:
    sents = [s for s in sentences if isinstance(s, str) and s.strip()]
    if not sents:
        log.warning("quick_upsert_plaintext: no sentences provided doc_id=%s", doc_id)
        return 0

    chunks: List[Chunk] = []
    for i, s in enumerate(sents, start=1):
        chunks.append(
            Chunk(
                doc_id=doc_id,
                chunk_id=f"{doc_id}_{i:04d}",
                doc_type=doc_type,
                tags=tags or ["hr-policy"],
                content=s.strip(),
                visibility=visibility,
            )
        )

    embs = embed_texts([c.content for c in chunks])
    dim = (len(embs[0]) if embs and len(embs) > 0 else -1)
    upsert_chunks(chunks, embeddings=embs)

    log.info(
        "quick_upsert_plaintext: upserted doc_id=%s chunks=%d dim≈%s",
        doc_id, len(chunks), dim,
    )
    return len(chunks)


# ---------- 파일 타입별 파서 선택 ----------
def _parse_by_type(file_path: Path) -> List[str]:
    ftype = detect_type(file_path)
    log.debug("detect type file=%s type=%s", file_path.name, ftype)

    if ftype == "pdf":
        from app.ingest.parsers.pdf import parse_pdf
        blocks = parse_pdf(file_path)
    elif ftype == "docx":
        from app.ingest.parsers.docx import parse_docx
        blocks = parse_docx(file_path)
    elif ftype == "txt":
        from app.ingest.parsers.txt import parse_txt
        blocks = parse_txt(file_path)
    elif ftype == "html":
        from app.ingest.parsers.html import parse_html
        blocks = parse_html(file_path)
    else:
        # 알 수 없는 확장자면 통짜 텍스트로 읽기 시도
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        blocks = [text]

    total_chars = sum(len(b) for b in blocks)
    log.info("parsed file=%s blocks=%d chars=%d", file_path.name, len(blocks), total_chars)
    return blocks


# ---------- 업로드된 파일 처리: Detect → Parse → Chunk → Tag → Embed → Upsert ----------
async def process_job(job_id: str, *, default_doc_type: str | None = None, visibility: str = "org") -> None:
    """
    UPLOADS_DIR / job_id 하위의 파일들을 순회하며 인덱싱 파이프라인 실행.
    - router에서 job_store.start(job_id, total=accepted)를 호출해 둔 상태를 기대.
      (중복 호출해도 큰 문제는 없지만 여기서는 호출하지 않음)
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

            # 2) Chunk
            chunks_text = merge_blocks_to_chunks(blocks)
            avg_len = (sum(len(c) for c in chunks_text) / max(1, len(chunks_text)))
            log.info(
                "chunked file=%s chunks=%d avg_len=%.1f",
                file_path.name, len(chunks_text), avg_len
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

            # 4) Build Chunk objects
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
                    )
                )
            log.info("built chunks file=%s count=%d", file_path.name, len(chunks))
            if not chunks:
                job_store.add_error(job_id, f"{file_path.name}: no chunks built")
                job_store.inc(job_id)
                continue

            # 5) Embed + Upsert
            embs = embed_texts([c.content for c in chunks])
            dim = (len(embs[0]) if embs and len(embs) > 0 else -1)
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
