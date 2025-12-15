from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional, Tuple, Dict
import re
import os
from hashlib import sha256
from datetime import datetime, timezone  # ⬅ 추가

from app.models.schemas import Chunk
from app.services.embedding import embed_texts
from app.vectorstore.store import upsert_chunks, doc_exists_by_hash, update_doc_visibility
from app.services.storage import UPLOADS_DIR, publish_doc, DOCS_DIR, save_chunk_image
from app.ingest.detect import detect_type
from app.ingest.chunkers import merge_blocks_to_chunks, chunk_by_structure
from app.ingest.jobs import job_store
from app.services.logging import get_logger
from app.ingest.tagger import tag_query

# ---- parsers --------------------------------------------------------------
from app.ingest.parsers.pdf import parse_pdf
from app.ingest.parsers.docx import parse_docx
from app.ingest.parsers.txt import parse_txt
from app.ingest.parsers.html import parse_html
from app.ingest.parsers.image_extractor import extract_images_from_pdf, extract_images_with_full_tables
from app.ingest.parsers.vision_processor import batch_process_images

# 표 추출 모듈 (pdfplumber)
try:
    from app.ingest.parsers.table_extractor import (
        extract_tables_from_pdf as extract_tables_pdfplumber,
        capture_table_images,
        merge_continuation_tables,
        capture_merged_table_images,
        merge_adjacent_tables_on_page,  # 방안 A
        is_complex_table,                # 복잡한 표 감지
        capture_full_table_region,       # 방안 C
        ExtractedTable,
        HAS_PDFPLUMBER,
    )
except ImportError:
    HAS_PDFPLUMBER = False
    extract_tables_pdfplumber = None
    capture_table_images = None
    merge_continuation_tables = None
    capture_merged_table_images = None
    merge_adjacent_tables_on_page = None
    is_complex_table = None
    capture_full_table_region = None
    ExtractedTable = None

# Vision API 폴백 (방안 B)
try:
    from app.ingest.parsers.vision_processor import process_complex_table_from_image
except ImportError:
    process_complex_table_from_image = None

log = get_logger("app.ingest.pipeline")

# P0-2.5: 구조 기반 청킹 Feature Flag
USE_STRUCTURE_CHUNKING = os.getenv("CHUNKING_MODE", "legacy").lower() == "structure"

# 표 추출 모드: "pdfplumber" (기본) | "vision" | "hybrid" | "off"
TABLE_EXTRACTION_MODE = os.getenv("TABLE_EXTRACTION_MODE", "hybrid").lower()


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
# 표 추출 헬퍼 (pdfplumber 기반)
# --------------------------------------------------------------------------
async def _extract_tables_hybrid(
    file_path: Path,
    doc_id: str,
) -> List[Tuple[int, int, str, str, float, Optional[bytes], str]]:
    """
    PDF에서 표를 추출 (하이브리드 방식)

    1단계: pdfplumber로 구조적 추출 시도
    2단계: 방안 A - 같은 페이지 내 인접 표 병합
    3단계: 연속 페이지 표 병합
    4단계: PyMuPDF로 표 영역 이미지 캡처
    5단계: 방안 B/C - 복잡한 표는 Vision API 폴백 + 고해상도 이미지

    반환값: List[(page_start, page_end, content_type, markdown, confidence, image_data, image_format)]
      - page_start: 시작 페이지 번호 (1-based)
      - page_end: 끝 페이지 번호 (병합 표의 경우)
      - content_type: "table"
      - markdown: 마크다운 표
      - confidence: 추출 신뢰도 (0.0 ~ 1.0)
      - image_data: 표 영역 이미지 바이너리 (원본 이미지)
      - image_format: 이미지 포맷 ("png")
    """
    table_chunks = []

    # 1단계: pdfplumber로 추출
    if HAS_PDFPLUMBER and TABLE_EXTRACTION_MODE in ("pdfplumber", "hybrid"):
        try:
            log.info(f"[TABLE] Step 1: Extracting tables with pdfplumber from {file_path.name}")
            tables = extract_tables_pdfplumber(file_path)

            if not tables:
                log.info(f"[TABLE] No tables found in {file_path.name}")
                return table_chunks

            log.info(f"[TABLE] pdfplumber found {len(tables)} tables")

            # 2단계: 방안 A - 같은 페이지 내 인접 표 병합 (매우 완화된 조건)
            if merge_adjacent_tables_on_page and len(tables) > 1:
                log.info(f"[TABLE] Step 2: Merging adjacent tables on same page (found {len(tables)} tables)...")
                # 복합 표를 제대로 병합하기 위해 매우 완화된 조건 사용
                # y_threshold=100: 100pt(약 35mm) 간격까지 인접으로 간주
                # x_overlap_ratio=0.1: 10%만 겹쳐도 인접으로 간주
                tables = merge_adjacent_tables_on_page(tables, y_threshold=100.0, x_overlap_ratio=0.1)

            # 3단계: 연속 페이지 표 병합
            if merge_continuation_tables and len(tables) > 1:
                log.info(f"[TABLE] Step 3: Checking for multi-page tables...")
                page_heights = {}
                try:
                    import fitz
                    doc = fitz.open(file_path)
                    for i in range(len(doc)):
                        page_heights[i + 1] = doc[i].rect.height
                    doc.close()
                except Exception as e:
                    log.warning(f"[TABLE] Failed to get page heights: {e}")
                    for t in tables:
                        page_heights[t.page_num] = 792

                tables = merge_continuation_tables(tables, page_heights)

            # 4단계: PyMuPDF로 표 영역 이미지 캡처
            log.info(f"[TABLE] Step 4: Capturing table images...")
            if tables and capture_merged_table_images:
                tables = capture_merged_table_images(file_path, tables, dpi=150, padding=10)
            elif tables and capture_table_images:
                tables = capture_table_images(file_path, tables, dpi=150, padding=10)

            # 5단계: 방안 B/C - 복잡한 표는 Vision API 폴백
            log.info(f"[TABLE] Step 5: Checking for complex tables (Vision fallback)...")
            for table in tables:
                if table.markdown and table.confidence >= 0.5:
                    page_end = table.page_end or table.page_num
                    final_markdown = table.markdown
                    final_image_data = table.image_data
                    final_confidence = table.confidence

                    # 복잡한 표인지 확인
                    use_vision = False
                    if is_complex_table and is_complex_table(table):
                        use_vision = True
                        log.info(
                            f"[TABLE] Complex table detected: page={table.page_num}, "
                            f"triggering Vision fallback"
                        )

                    # 방안 B: Vision API 폴백
                    if use_vision and process_complex_table_from_image and table.image_data:
                        try:
                            log.info(f"[TABLE] Running Vision API for complex table on page {table.page_num}...")

                            # 방안 C: 고해상도 이미지 캡처
                            if capture_full_table_region:
                                high_res_image = capture_full_table_region(
                                    file_path, table.page_num, table.bbox, dpi=200, padding=15
                                )
                                if high_res_image:
                                    final_image_data = high_res_image
                                    log.info(f"[TABLE] Captured high-res image for Vision API")

                            # Vision API 호출
                            vision_markdown = await process_complex_table_from_image(
                                image_data=final_image_data or table.image_data,
                                image_format="png",
                                page_num=table.page_num,
                            )

                            if vision_markdown:
                                final_markdown = vision_markdown
                                final_confidence = 0.95  # Vision 결과는 높은 신뢰도
                                log.info(
                                    f"[TABLE] Vision API success: page={table.page_num}, "
                                    f"length={len(vision_markdown)}"
                                )
                            else:
                                log.warning(
                                    f"[TABLE] Vision API failed, using pdfplumber result: "
                                    f"page={table.page_num}"
                                )

                        except Exception as e:
                            log.warning(f"[TABLE] Vision API error: {e}, using pdfplumber result")

                    table_chunks.append((
                        table.page_num,
                        page_end,
                        "table",
                        final_markdown,
                        final_confidence,
                        final_image_data,
                        table.image_format,
                    ))

                    log.info(
                        f"[TABLE] Added table: page={table.page_num}-{page_end}, "
                        f"confidence={final_confidence:.2f}, "
                        f"vision_used={use_vision and final_markdown != table.markdown}, "
                        f"has_image={final_image_data is not None}"
                    )

            log.info(f"[TABLE] Final: {len(table_chunks)} tables from {file_path.name}")

        except Exception as e:
            log.warning(f"[TABLE] Table extraction failed: {e}")
            import traceback
            log.debug(traceback.format_exc())

    return table_chunks


# --------------------------------------------------------------------------
# 이미지 처리 헬퍼 (P0-2)
# --------------------------------------------------------------------------
async def _process_pdf_images(
    file_path: Path,
    doc_id: str,
    skip_tables: bool = False,
) -> List[Tuple[int, str, str, str, Optional[bytes], str]]:
    """
    PDF에서 이미지를 추출하고 Vision API로 처리.

    Args:
        file_path: PDF 파일 경로
        doc_id: 문서 ID
        skip_tables: True면 표 이미지 처리 스킵 (pdfplumber로 처리한 경우)

    반환값: List[(page_num, image_type, image_content, description, image_data, image_format)]
      - page_num: 페이지 번호 (1-based)
      - image_type: "table" | "figure"
      - image_content: 마크다운 표 또는 그림 설명
      - description: 로그용 설명
      - image_data: 이미지 바이너리 데이터 (저장용)
      - image_format: 이미지 포맷 (png, jpeg 등)
    """
    try:
        # 1) 이미지 추출 (표 이미지는 전체 영역으로 확장 캡처)
        log.info(f"[IMAGE] Extracting images from {file_path.name}")
        # extract_images_with_full_tables: 표 이미지를 페이지 렌더링으로 전체 영역 캡처
        extracted_images = extract_images_with_full_tables(file_path)

        if not extracted_images:
            log.info(f"[IMAGE] No images found in {file_path.name}")
            return []

        # skip_tables 옵션: 표 이미지 제외 (pdfplumber로 이미 처리한 경우)
        if skip_tables:
            original_count = len(extracted_images)
            extracted_images = [img for img in extracted_images if img.image_type != "table"]
            log.info(
                f"[IMAGE] Skipping table images: {original_count} -> {len(extracted_images)} images"
            )

        if not extracted_images:
            return []

        log.info(f"[IMAGE] Found {len(extracted_images)} images in {file_path.name}")

        # 2) Vision API로 배치 처리
        log.info(f"[IMAGE] Processing images with Vision API...")
        results = await batch_process_images(extracted_images, max_concurrent=3)

        # 3) 결과 변환 (이미지 바이너리 데이터 포함)
        image_chunks = []

        # 표 처리 (skip_tables=False인 경우에만)
        if not skip_tables:
            for img, markdown in results.get("tables", []):
                image_chunks.append((
                    img.page_num,
                    "table",
                    markdown,
                    f"Table {img.image_index} on page {img.page_num}",
                    img.image_data,  # 이미지 바이너리
                    img.image_format,  # 이미지 포맷
                ))

        # 그림 처리
        for img, description in results.get("figures", []):
            image_chunks.append((
                img.page_num,
                "figure",
                description,
                f"Figure {img.image_index} on page {img.page_num}",
                img.image_data,  # 이미지 바이너리
                img.image_format,  # 이미지 포맷
            ))

        log.info(
            f"[IMAGE] Processed {len(image_chunks)} images: "
            f"{len(results.get('tables', []))} tables, "
            f"{len(results.get('figures', []))} figures, "
            f"{len(results.get('failed', []))} failed"
        )

        return image_chunks

    except Exception as e:
        log.error(f"[IMAGE] Failed to process images from {file_path.name}: {e}")
        return []


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
    team_id: Optional[int] = None,
    team_name: Optional[str] = None,
) -> None:
    """
    업로드 잡 처리 파이프라인:
      0) 콘텐츠 해시 계산 → 해시 기반 doc_id 생성 → 벡터스토어 메타로 중복 검사(소유자/가시성 범위)
      1) 파일 타입 판별/로그
      2) 청크 생성
      3) 퍼블리시(최종 저장소로 이동/복사) → relpath/url 계약 로그
      5) 태그 생성/정규화
      6) 임베딩 생성 + 업서트 (visibility="pending"으로 임시 저장)
      7) (성공 시) 스테이징 원본 삭제
      8) 최종적으로 job_store.finish(job_id) 호출 → 상태를 succeeded/failed로 확정
      9) 성공한 문서들의 visibility를 pending → 원래 값으로 변경

    Note:
      - 업로드 중인 문서는 visibility="pending"으로 저장되어 검색에서 제외됨
      - 모든 파일 처리 완료 후에야 원래 visibility로 전환됨
    """
    # 라우터 호환: job_dir/files 는 내부에서 계산
    job_dir = UPLOADS_DIR / job_id
    files = sorted([p for p in job_dir.glob("*") if p.is_file()])

    log.info("process start job_id=%s files=%d dir=%s", job_id, len(files), job_dir)

    had_error = False
    # 성공적으로 upsert된 doc_id 목록 (나중에 visibility 전환용)
    successful_doc_ids: List[str] = []

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
            # P0-2.5: 구조 기반 청킹 or 기존 방식
            structure_metadata = []  # 구조 메타데이터 저장용
            use_structure = USE_STRUCTURE_CHUNKING  # 지역 변수로 복사

            if is_pdf:
                # P0-2.5: 구조 기반 청킹 시도
                if use_structure:
                    log.info(f"[INGEST] Using structure-based chunking for {file_path.name}")
                    try:
                        chunks_text, page_ranges, structure_metadata = chunk_by_structure(
                            file_path,
                            max_chars=2000
                        )

                        if chunks_text:
                            log.info(
                                f"[INGEST] Structure chunking success: "
                                f"{len(chunks_text)} chunks from {file_path.name}"
                            )
                        else:
                            # 구조 분석 실패 시 기존 방식으로 폴백
                            log.warning(
                                f"[INGEST] Structure chunking failed for {file_path.name}, "
                                f"falling back to legacy chunking"
                            )
                            use_structure = False  # 이 파일만 기존 방식으로
                    except Exception as e:
                        log.error(
                            f"[INGEST] Structure chunking error for {file_path.name}: {e}, "
                            f"falling back to legacy chunking"
                        )
                        chunks_text = []

                # 기존 방식 (구조 분석 실패 시 또는 Feature Flag OFF)
                if not use_structure or not chunks_text:
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

                # 2-1) 표 추출 (pdfplumber 하이브리드)
                table_chunks_data = []
                pdfplumber_table_pages = set()  # pdfplumber로 추출한 표가 있는 페이지

                if TABLE_EXTRACTION_MODE != "off":
                    table_chunks_data = await _extract_tables_hybrid(file_path, doc_id)
                    pdfplumber_table_pages = {t[0] for t in table_chunks_data}
                    log.info(
                        f"[INGEST] pdfplumber tables: {len(table_chunks_data)} on pages {pdfplumber_table_pages}"
                    )

                # 2-2) PDF 이미지 처리 (P0-2)
                # pdfplumber로 표를 이미 추출한 경우 Vision에서 표 이미지 스킵
                skip_vision_tables = len(table_chunks_data) > 0 and TABLE_EXTRACTION_MODE == "pdfplumber"
                image_chunks_data = await _process_pdf_images(
                    file_path, doc_id, skip_tables=skip_vision_tables
                )

                # 이미지 청크 정보 저장 (나중에 Chunk 객체 생성 시 사용)
                # image_metadata: Dict[int, Tuple[str, str, Optional[str]]]
                # chunk_index -> (img_type, img_content, img_url)
                image_metadata: Dict[int, Tuple[str, str, Optional[str]]] = {}

                # pdfplumber 표 청크 추가 (이미지 캡처 포함, 병합 표 지원)
                for table_data in table_chunks_data:
                    # 튜플 언패킹: (page_start, page_end, content_type, markdown, confidence, image_data, image_format)
                    page_start, page_end, content_type, markdown, confidence, img_data, img_format = table_data
                    chunk_idx = len(chunks_text)
                    chunks_text.append(markdown)
                    # 병합 표의 경우 page_start ~ page_end 범위 저장
                    page_ranges.append((page_start, page_end))

                    # 표 영역 이미지 저장
                    img_url = None
                    if img_data:
                        try:
                            _, img_url = save_chunk_image(
                                image_data=img_data,
                                doc_id=doc_id,
                                chunk_index=chunk_idx,
                                image_type="table",
                                image_format=img_format or "png",
                            )
                            log.info(f"[TABLE] Saved table image: {img_url}")
                        except Exception as e:
                            log.warning(f"[TABLE] Failed to save table image: {e}")

                    image_metadata[chunk_idx] = ("table", markdown, img_url)
                    is_merged = page_start != page_end
                    log.debug(
                        f"[INGEST] Added table chunk: idx={chunk_idx}, pages={page_start}-{page_end}, "
                        f"merged={is_merged}, has_image={img_url is not None}"
                    )

                # 이미지 청크를 텍스트 청크와 병합 (이미지 파일 저장)
                for page_num, img_type, img_content, img_desc, img_data, img_format in image_chunks_data:
                    chunk_idx = len(chunks_text)
                    chunks_text.append(img_content)
                    page_ranges.append((page_num, page_num))

                    # 이미지 파일 저장 및 URL 생성
                    img_url = None
                    if img_data:
                        try:
                            _, img_url = save_chunk_image(
                                image_data=img_data,
                                doc_id=doc_id,
                                chunk_index=chunk_idx,
                                image_type=img_type,
                                image_format=img_format or "png",
                            )
                            log.info(f"[IMAGE] Saved image: {img_url}")
                        except Exception as e:
                            log.warning(f"[IMAGE] Failed to save image: {e}")

                    image_metadata[chunk_idx] = (img_type, img_content, img_url)

                log.info(
                    f"[INGEST] Total chunks after images: {len(chunks_text)} "
                    f"(text + {len(image_chunks_data)} images)"
                )

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
                image_metadata = {}  # 비-PDF는 이미지 없음

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

                # 이미지 메타데이터 확인 (P0-2)
                has_image = i in image_metadata
                img_type = None
                img_content = None
                img_url = None
                if has_image:
                    img_type, img_content, img_url = image_metadata[i]

                # 구조 메타데이터 확인 (P0-2.5)
                struct_meta = structure_metadata[i] if i < len(structure_metadata) else {}

                chunks.append(
                    Chunk(
                        doc_id=doc_id,
                        doc_hash=doc_hash,  # 메타로 저장
                        chunk_id=f"{doc_id}_{i:04d}",
                        doc_type=default_doc_type or "policy-manual",
                        tags=tags,
                        content=content,
                        # ✅ 업로드 중에는 "pending"으로 저장 → 검색에서 제외
                        # 모든 파일 처리 완료 후 원래 visibility로 전환
                        visibility="pending",
                        doc_title=stem,
                        doc_url=doc_url,
                        doc_relpath=doc_relpath,
                        owner_id=owner_id,
                        owner_username=owner_username,
                        page_start=p_start if is_pdf else None,
                        page_end=p_end if is_pdf else None,
                        # 이미지 메타데이터 (P0-2)
                        has_image=has_image,
                        image_type=img_type,
                        image_content=img_content,
                        image_url=img_url,  # 원본 이미지 URL
                        # 구조 메타데이터 (P0-2.5)
                        section_title=struct_meta.get("section_title"),
                        article_number=struct_meta.get("article_number"),
                        hierarchy_level=struct_meta.get("hierarchy_level"),
                        parent_article=struct_meta.get("parent_article"),
                        is_complete_article=struct_meta.get("is_complete_article"),
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
            # target_visibility: 최종 전환할 visibility 값도 함께 저장 (나중에 전환 시 참조)
            uploaded_at = datetime.now(timezone.utc).isoformat()
            common_meta = {
                "uploaded_at": uploaded_at,
                "target_visibility": visibility,  # pending → 이 값으로 전환 예정
            }
            # 팀 정보 추가 (팀별 문서 격리)
            if team_id is not None:
                common_meta["team_id"] = str(team_id)
            if team_name:
                common_meta["team_name"] = team_name

            upsert_chunks(
                chunks,
                embeddings=embs,
                common_metadata=common_meta,
            )
            log.info("upserted file=%s chunks=%d (pending)", file_path.name, len(chunks))

            # ✅ 성공한 doc_id 기록 (나중에 visibility 전환용)
            successful_doc_ids.append(doc_id)

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

    # ✅ 성공한 문서들의 visibility를 pending → 원래 값으로 전환
    # 이 시점부터 검색 결과에 포함됨
    if successful_doc_ids:
        log.info(
            "[VISIBILITY] Transitioning %d docs from pending to target visibility",
            len(successful_doc_ids)
        )
        for doc_id in successful_doc_ids:
            try:
                updated = update_doc_visibility(doc_id, visibility)
                log.debug(
                    "[VISIBILITY] doc_id=%s -> %s (%d chunks)",
                    doc_id, visibility, updated
                )
            except Exception as e:
                log.warning(
                    "[VISIBILITY] Failed to update doc_id=%s: %s", doc_id, e
                )

    # ✅ 빈 업로드 폴더 정리
    try:
        if job_dir.exists() and job_dir.is_dir():
            # 폴더 내 파일이 없으면 삭제 (하위 폴더 포함)
            remaining = list(job_dir.rglob("*"))
            if not remaining or all(p.is_dir() for p in remaining):
                import shutil
                shutil.rmtree(job_dir, ignore_errors=True)
                log.info("[CLEANUP] removed empty job folder: %s", job_dir)
    except Exception as e:
        log.debug("[CLEANUP] failed to remove job folder %s: %s", job_dir, e)

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
