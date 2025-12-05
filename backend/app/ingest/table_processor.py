"""
표 추출 모듈 (하이브리드 방식)

pdfplumber + Vision API 폴백을 사용한 PDF 표 추출 기능 제공.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional, Tuple

from app.services.logging import get_logger

log = get_logger("app.ingest.table_processor")

# 표 추출 모드: "pdfplumber" (기본) | "vision" | "hybrid" | "off"
TABLE_EXTRACTION_MODE = os.getenv("TABLE_EXTRACTION_MODE", "hybrid").lower()

# 표 추출 모듈 (pdfplumber)
try:
    from app.ingest.parsers.table_extractor import (
        extract_tables_from_pdf as extract_tables_pdfplumber,
        capture_table_images,
        merge_continuation_tables,
        capture_merged_table_images,
        merge_adjacent_tables_on_page,
        is_complex_table,
        capture_full_table_region,
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


async def extract_tables_hybrid(
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
