from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional, Tuple
import re
from hashlib import sha256
from datetime import datetime, timezone  # ⬅ 추가

from app.models.schemas import Chunk
from app.services.embedding import embed_texts
from app.vectorstore.store import upsert_chunks, doc_exists_by_hash
from app.services.storage import UPLOADS_DIR, publish_doc, DOCS_DIR
from app.ingest.detect import detect_type
from app.ingest.chunkers import merge_blocks_to_chunks
from app.ingest.jobs import job_store
from app.services.logging import get_logger
from app.ingest.tagger import tag_query

# ---- parsers --------------------------------------------------------------
from app.ingest.parsers.pdf import parse_pdf
from app.ingest.parsers.docx import parse_docx
from app.ingest.parsers.txt import parse_txt
from app.ingest.parsers.html import parse_html

log = get_logger("app.ingest.pipeline")


# --------------------------------------------------------------------------
# 공통 헬퍼
# --------------------------------------------------------------------------
def _norm_rel_and_url(dst_path: Path) -> tuple[str, str]:
    """
    DOCS_DIR 기준 상대경로를 구해 슬래시 표준화.
    - doc_relpath: 항상 'public/<...>'
    - doc_url: 항상 '/static/docs/<...>'  (여기서 <...>은 public/ 제거한 rel_core)
    """
    try:
        rel = str(dst_path.resolve().relative_to(DOCS_DIR.resolve()))
    except Exception:
        rel = str(dst_path)

    rel = rel.replace("\\", "/").lstrip("/")

    # rel_core: URL용 (public/ 또는 static/docs/ 프리픽스를 제거)
    rel_core = rel
    for p in ("public/", "static/docs/"):
        if rel_core.startswith(p):
            rel_core = rel_core[len(p) :]

    # doc_relpath: 저장소 상대경로는 항상 public/을 유지
    doc_relpath = rel if rel.startswith("public/") else f"public/{rel_core}"
    # doc_url: 웹 경로(항상 /static/docs/<rel_core>)
    doc_url = f"/static/docs/{rel_core}"
    return doc_relpath, doc_url


def _is_pdf(ftype) -> bool:
    """detect_type 결과가 무엇이든 문자열화 해서 'pdf' 포함 여부로 판별"""
    try:
        return "pdf" in str(ftype).lower()
    except Exception:
        return False


def _debug(msg, *a):
    # 필요 시 log.debug로 바꿔도 됩니다.
    print(f"[INGEST][DEBUG] " + (str(msg) % a if a else str(msg)))


def _assert_contract(doc_relpath: str | None, doc_url: str | None):
    """계약: doc_relpath는 public/…, doc_url은 /static/docs/… (public 없음)"""
    ok = True
    if (
        not doc_url
        or not isinstance(doc_url, str)
        or not doc_url.startswith("/static/docs/")
    ):
        _debug("❌ doc_url invalid: %r", doc_url)
        ok = False
    if (
        not doc_relpath
        or not isinstance(doc_relpath, str)
        or not doc_relpath.replace("\\", "/").startswith("public/")
    ):
        _debug("❌ doc_relpath invalid: %r", doc_relpath)
        ok = False
    if ok:
        _debug("✅ contract ok: rel=%s url=%s", doc_relpath, doc_url)


# --------------------------------------------------------------------------
# PDF 전용: 페이지 정보를 보존하기 위한 헬퍼 (선택 사용)
# --------------------------------------------------------------------------
def _pdf_blocks_with_pages(file_path: Path):
    """
    PDF를 (page_no, paragraph) 블록으로 변환.
    - parse_pdf: List[str] (페이지별) 또는 str(전문) 모두 처리
    - 페이지가 분리되지 않으면 1페이지로 보고 블록 생성
    """
    pages = parse_pdf(file_path)

    # 타입 정규화
    if isinstance(pages, str):
        parts = (
            [p for p in re.split(r"\f+", pages) if p.strip()]
            if "\f" in pages
            else [pages]
        )
        pages = parts or [pages]
    elif not isinstance(pages, list):
        pages = [str(pages or "")]

    blocks = []
    for pno, text in enumerate(pages, start=1):
        t = (text or "").strip()
        if not t:
            continue
        # 빈 줄 기준 문단화 (없으면 줄 단위)
        paras = [pp.strip() for pp in re.split(r"\n\s*\n", t) if pp.strip()] or [
            ln.strip() for ln in t.splitlines() if ln.strip()
        ]
        for para in paras:
            blocks.append((pno, para))
    return blocks


def _merge_with_pages(
    blocks: List[Tuple[int, str]],
    *,
    max_chars: int = 1200,
) -> Tuple[List[str], List[Tuple[Optional[int], Optional[int]]]]:
    """
    (page_no, paragraph) 블록을 받아 페이지 범위를 보존하며 청크 병합.
    반환값: (chunks_text, page_ranges)
      - chunks_text: List[str]
      - page_ranges: List[(page_start, page_end)]  # 각 청크와 1:1 매칭
    """
    chunks: List[str] = []
    ranges: List[Tuple[Optional[int], Optional[int]]] = []

    cur = ""
    start_p: Optional[int] = None
    end_p: Optional[int] = None

    for pno, para in blocks:
        if not cur:
            start_p = pno
        if len(cur) + len(para) + 1 <= max_chars:
            cur = (cur + "\n" if cur else "") + para
            end_p = pno
        else:
            if cur:
                chunks.append(cur.strip())
                ranges.append((start_p, end_p or start_p))
            # 새 청크 시작
            cur = para.strip()
            start_p = pno
            end_p = pno

    if cur:
        chunks.append(cur.strip())
        ranges.append((start_p, end_p or start_p))

    return chunks, ranges


# --------------------------------------------------------------------------
# 업로드 잡 처리
# --------------------------------------------------------------------------
async def process_job(
    job_id: str,
    *,
    default_doc_type: Optional[str] = None,
    visibility: str = "public",
    owner_id: Optional[int] = None,
    owner_username: Optional[str] = None,
) -> None:
    """
    업로드 잡 처리 파이프라인:
      0) 콘텐츠 해시 계산 → 해시 기반 doc_id 생성 → 벡터스토어 메타로 중복 검사(소유자/가시성 범위)
      1) 파일 타입 판별/로그
      2) 청크 생성
      3) 퍼블리시(최종 저장소로 이동/복사) → relpath/url 계약 로그
      5) 태그 생성/정규화
      6) 임베딩 생성 + 업서트
      7) (성공 시) 스테이징 원본 삭제
      8) 최종적으로 job_store.finish(job_id) 호출 → 상태를 succeeded/failed로 확정
    """
    # 라우터 호환: job_dir/files 는 내부에서 계산
    job_dir = UPLOADS_DIR / job_id
    files = sorted([p for p in job_dir.glob("*") if p.is_file()])

    log.info("process start job_id=%s files=%d dir=%s", job_id, len(files), job_dir)

    had_error = False

    for file_path in files:
        try:
            log.info("processing job_id=%s file=%s", job_id, file_path.name)

            # 0) 콘텐츠 해시 선계산 & 해시 기반 doc_id 생성 (퍼블리시/파싱 전에!)
            try:
                h = sha256()
                with file_path.open("rb") as f:
                    for chunk in iter(lambda: f.read(1024 * 1024), b""):
                        if not chunk:
                            break
                        h.update(chunk)
                digest = h.hexdigest()
            except FileNotFoundError:
                log.warning("staged file disappeared before hashing: %s", file_path)
                job_store.add_error(job_id, f"{file_path.name}: staged file missing")
                job_store.inc(job_id)
                had_error = True
                continue

            doc_hash = digest  # 64자 전체 저장
            stem = file_path.stem  # 표시용 제목은 파일명 stem 유지
            doc_id = f"doc_{digest[:12]}"  # 해시 앞 12자로 식별자 생성

            # 0-1) 중복 스킵: 동일 해시(+ 같은 소유자/가시성) 문서가 이미 있으면 처리 생략
            if doc_exists_by_hash(
                doc_hash=doc_hash, owner_id=owner_id, visibility=visibility
            ):
                log.info(
                    "[DUP] skip existing doc: doc_id=%s hash=%s owner=%s vis=%s",
                    doc_id,
                    doc_hash[:12],
                    owner_id,
                    visibility,
                )
                job_store.inc(job_id)
                try:
                    if file_path.exists():
                        file_path.unlink()
                        log.info("[CLEANUP] removed staged duplicate: %s", file_path)
                except Exception:
                    pass
                # 중복은 에러로 치지 않음
                continue

            # 1) 파일 타입 판별(+확장자 백업) 및 로그
            ftype = detect_type(file_path)
            is_pdf = _is_pdf(ftype) or file_path.suffix.lower() == ".pdf"
            log.info(
                "[INGEST] file=%s detect_type=%r ext=%r is_pdf=%s",
                file_path.name,
                ftype,
                file_path.suffix,
                is_pdf,
            )

            # 2) 청크 생성
            if is_pdf:
                blocks = _pdf_blocks_with_pages(file_path)
                if not blocks:
                    job_store.add_error(job_id, f"{file_path.name}: no text extracted")
                    job_store.inc(job_id)
                    had_error = True
                    continue
                chunks_text, page_ranges = _merge_with_pages(blocks, max_chars=1200)
                # (마지막 방어선) 페이지 정보가 비거나 전부 None이면 1페이지로 보정
                if not page_ranges or all(
                    ps is None and pe is None for ps, pe in page_ranges
                ):
                    log.warning(
                        "[INGEST] %s page_ranges empty/null -> fallback to page=1",
                        file_path.name,
                    )
                    page_ranges = [(1, 1) for _ in range(len(chunks_text))]
            else:
                # (비-PDF) 기존 블록 병합 파이프라인
                blocks = _parse_by_type(file_path)
                if not blocks:
                    job_store.add_error(job_id, f"{file_path.name}: no text extracted")
                    job_store.inc(job_id)
                    had_error = True
                    continue
                chunks_text = merge_blocks_to_chunks(blocks)
                page_ranges = [(None, None)] * len(chunks_text)

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
                had_error = True
                continue

            # 3) 문서 퍼블리시 및 URL/relpath 확정 (+ 계약 로그)
            try:
                _, dst_path = publish_doc(file_path, visibility=visibility)
                doc_relpath, doc_url = _norm_rel_and_url(dst_path)
            except Exception as e:
                doc_url = None
                doc_relpath = None
                log.warning("publish_doc failed file=%s err=%s", file_path.name, e)

            log.info("[INGEST] contract rel=%r url=%r", doc_relpath, doc_url)
            _assert_contract(doc_relpath, doc_url)

            # 5) 태그 생성/정규화
            try:
                gen_tags = await tag_query(stem, max_tags=6)
            except Exception as e:
                log.debug("tagger failed file=%s err=%s", file_path.name, e)
                gen_tags = []
            tags = list({*gen_tags}) or ["hr-policy"]
            log.debug("tags file=%s tags=%s", file_path.name, tags)

            # 5') Chunk 객체 구성
            chunks: List[Chunk] = []
            for i, text in enumerate(chunks_text):
                content = (
                    text if isinstance(text, str) else getattr(text, "content", "")
                )
                p_start, p_end = (
                    page_ranges[i] if i < len(page_ranges) else (None, None)
                )
                chunks.append(
                    Chunk(
                        doc_id=doc_id,
                        doc_hash=doc_hash,  # 메타로 저장
                        chunk_id=f"{doc_id}_{i:04d}",
                        doc_type=default_doc_type or "policy-manual",
                        tags=tags,
                        content=content,
                        visibility=visibility,
                        doc_title=stem,
                        doc_url=doc_url,
                        doc_relpath=doc_relpath,
                        owner_id=owner_id,
                        owner_username=owner_username,
                        page_start=p_start if is_pdf else None,
                        page_end=p_end if is_pdf else None,
                    )
                )
            log.info("built chunks file=%s count=%d", file_path.name, len(chunks))
            if not chunks:
                job_store.add_error(job_id, f"{file_path.name}: no chunks built")
                job_store.inc(job_id)
                had_error = True
                continue

            # 6) 임베딩 + 업서트
            embs = embed_texts([c.content for c in chunks])
            dim = len(embs[0]) if embs and len(embs) > 0 else -1
            log.info("embedded file=%s vecs=%d dim≈%s", file_path.name, len(embs), dim)

            # ✅ 업로드 시각(UTC ISO8601)을 공통 메타로 저장
            uploaded_at = datetime.now(timezone.utc).isoformat()
            upsert_chunks(
                chunks, embeddings=embs, common_metadata={"uploaded_at": uploaded_at}
            )
            log.info("upserted file=%s chunks=%d", file_path.name, len(chunks))

            # 진행 수치 업데이트
            job_store.inc(job_id)

            # ✅ 성공 처리된 스테이징 원본 삭제
            try:
                if file_path.exists():
                    file_path.unlink()
                    log.info("[CLEANUP] removed staged file: %s", file_path)
            except Exception as e:
                log.warning(
                    "[CLEANUP] failed to remove staged file %s: %s", file_path, e
                )

        except Exception as e:
            log.exception("exception job_id=%s file=%s", job_id, file_path.name)
            job_store.add_error(job_id, f"{file_path.name}: {e!s}")
            job_store.inc(job_id)
            had_error = True
            # 실패 파일은 _failed/로 치우기(선택)
            try:
                failed_dir = job_dir / "_failed"
                failed_dir.mkdir(exist_ok=True)
                if file_path.exists():
                    file_path.rename(failed_dir / file_path.name)
            except Exception:
                pass

    # ✅ 최종 상태 확정 (프런트가 succeeded/failed로 전환할 수 있게)
    try:
        job_store.finish(
            job_id
        )  # 내부에서 errors 유무를 보고 상태를 정하는 구현이면 이대로 OK
        # 만약 finish(job_id, status=...) 형태라면 아래처럼 바꾸세요:
        # job_store.finish(job_id, status=("failed" if had_error else "succeeded"))
    except Exception as e:
        log.warning("job finish mark failed job_id=%s err=%s", job_id, e)

    log.info("process done job_id=%s", job_id)


# --------------------------------------------------------------------------
# 간이 업서트 (원시 텍스트)
# --------------------------------------------------------------------------
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
        return 0

    tags_list = list(tags or [])

    chunks: List[Chunk] = []
    for i, content in enumerate(chunks_text, start=1):
        chunks.append(
            Chunk(
                doc_id=doc_id,
                chunk_id=f"{doc_id}_{i:04d}",
                doc_type=doc_type,
                tags=tags_list,
                content=content,
                visibility=visibility,
                doc_title=title,
                doc_url=doc_url,
                doc_relpath=None,
                owner_id=None,
                owner_username=None,
                page_start=None,
                page_end=None,
            )
        )

    embs = embed_texts([c.content for c in chunks])
    # 여기서는 업로드 시각을 지금 시각으로 기록
    uploaded_at = datetime.now(timezone.utc).isoformat()
    upsert_chunks(chunks, embeddings=embs, common_metadata={"uploaded_at": uploaded_at})
    return len(chunks)


# --------------------------------------------------------------------------
# 파일 타입별 파서 선택 (비-PDF 경로에서 사용)
# --------------------------------------------------------------------------
def _parse_by_type(file_path: Path) -> List[str]:
    ftype = detect_type(file_path)
    log.debug("detect type file=%s type=%s", file_path.name, ftype)
    try:
        if _is_pdf(ftype):
            pages = parse_pdf(file_path)
            # parse_pdf가 문자열을 돌려줄 가능성도 대비
            if isinstance(pages, str):
                parts = re.split(r"\f+", pages)
                return [p.strip() for p in parts if p and p.strip()]
            return pages  # 보통은 List[str] (페이지별 텍스트)
        if isinstance(ftype, str) and "docx" in ftype.lower():
            return parse_docx(file_path)
        if isinstance(ftype, str) and "txt" in ftype.lower():
            return parse_txt(file_path)
        if isinstance(ftype, str) and "html" in ftype.lower():
            return parse_html(file_path)
        # unknown: 텍스트로 시도
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        return [b.strip() for b in text.splitlines() if b.strip()]
    except Exception as e:
        log.warning("parse failed type=%s file=%s err=%s", ftype, file_path.name, e)
        return []
