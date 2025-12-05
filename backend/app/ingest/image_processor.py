"""
이미지 처리 모듈

PDF에서 이미지를 추출하고 Vision API로 처리하는 기능 제공.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

from app.services.logging import get_logger

log = get_logger("app.ingest.image_processor")

# 이미지 추출 모듈
try:
    from app.ingest.parsers.image_extractor import extract_images_with_full_tables
except ImportError:
    extract_images_with_full_tables = None

# Vision API 처리
try:
    from app.ingest.parsers.vision_processor import batch_process_images
except ImportError:
    batch_process_images = None


async def process_pdf_images(
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
    if not extract_images_with_full_tables or not batch_process_images:
        log.warning("[IMAGE] Image processing modules not available")
        return []

    try:
        # 1) 이미지 추출 (표 이미지는 전체 영역으로 확장 캡처)
        log.info(f"[IMAGE] Extracting images from {file_path.name}")
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
