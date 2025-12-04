"""
PDF 이미지 추출 모듈 (PyMuPDF 사용)

PDF 문서에서 이미지를 추출하고 메타데이터를 수집합니다.
- 표 이미지와 일반 그림을 구분
- 페이지 번호, 위치, 크기 정보 수집
- 추출된 이미지를 임시 디렉토리에 저장
"""

from __future__ import annotations

import fitz  # PyMuPDF
from pathlib import Path
from typing import List, Tuple, Optional
from dataclasses import dataclass
from io import BytesIO
from PIL import Image

from app.services.logging import get_logger

log = get_logger("app.ingest.parsers.image_extractor")


@dataclass
class ExtractedImage:
    """추출된 이미지 메타데이터"""
    page_num: int           # 페이지 번호 (1-based)
    image_index: int        # 페이지 내 이미지 인덱스 (0-based)
    image_type: str         # "table" | "figure" | "unknown"
    bbox: Tuple[float, float, float, float]  # (x0, y0, x1, y1)
    width: int              # 이미지 너비 (픽셀)
    height: int             # 이미지 높이 (픽셀)
    image_data: bytes       # 이미지 바이너리 데이터
    image_format: str       # "png" | "jpeg" | "jpg"


def _classify_image_type(img: Image.Image) -> str:
    """
    이미지 타입 분류 (간단한 휴리스틱)

    표 특징:
    - 가로/세로 비율이 극단적이지 않음 (0.3 < ratio < 3.0)
    - 크기가 충분히 큼 (width > 200, height > 100)

    Args:
        img: PIL Image 객체

    Returns:
        "table" | "figure" | "unknown"
    """
    width, height = img.size

    # 너무 작은 이미지는 무시
    if width < 100 or height < 50:
        return "unknown"

    aspect_ratio = width / height

    # 표 휴리스틱: 적절한 비율 + 충분한 크기
    # 색상 복잡도 체크 제거 - 안티앨리어싱으로 인해 표도 색상이 많을 수 있음
    # 대신 크기와 비율로만 판단하고, Vision API가 최종 판단
    if 0.3 < aspect_ratio < 3.0 and width > 200 and height > 100:
        # 충분히 큰 이미지는 일단 표로 시도 (Vision API가 NO_TABLE 반환 가능)
        return "table"

    # 극단적인 비율 (배너, 로고 등)은 figure로 분류
    return "figure"


def extract_images_from_pdf(pdf_path: Path) -> List[ExtractedImage]:
    """
    PDF에서 모든 이미지 추출

    Args:
        pdf_path: PDF 파일 경로

    Returns:
        추출된 이미지 리스트

    Raises:
        Exception: PDF 파일 열기 실패 또는 이미지 추출 실패
    """
    extracted_images: List[ExtractedImage] = []

    try:
        doc = fitz.open(pdf_path)
        log.info(f"Opened PDF: {pdf_path.name}, pages={len(doc)}")

        for page_num in range(len(doc)):
            page = doc[page_num]
            image_list = page.get_images(full=True)

            log.debug(f"Page {page_num + 1}: found {len(image_list)} images")

            for img_index, img_info in enumerate(image_list):
                try:
                    # 이미지 참조 추출
                    xref = img_info[0]
                    base_image = doc.extract_image(xref)

                    if not base_image:
                        continue

                    image_bytes = base_image["image"]
                    image_ext = base_image["ext"]  # "png", "jpeg", etc.

                    # PIL Image로 변환하여 메타데이터 추출
                    pil_image = Image.open(BytesIO(image_bytes))
                    width, height = pil_image.size

                    # 이미지 타입 분류
                    img_type = _classify_image_type(pil_image)

                    # 이미지가 페이지 내에서 차지하는 영역 (바운딩 박스) 추출
                    # get_image_rects는 이미지의 모든 출현 위치를 반환
                    rects = page.get_image_rects(xref)
                    bbox = rects[0] if rects else (0, 0, width, height)

                    extracted_img = ExtractedImage(
                        page_num=page_num + 1,  # 1-based
                        image_index=img_index,
                        image_type=img_type,
                        bbox=(bbox.x0, bbox.y0, bbox.x1, bbox.y1) if hasattr(bbox, 'x0') else bbox,
                        width=width,
                        height=height,
                        image_data=image_bytes,
                        image_format=image_ext,
                    )

                    extracted_images.append(extracted_img)
                    log.debug(
                        f"Extracted image: page={page_num + 1}, index={img_index}, "
                        f"type={img_type}, size={width}x{height}, format={image_ext}"
                    )

                except Exception as e:
                    log.warning(
                        f"Failed to extract image: page={page_num + 1}, index={img_index}, error={e}"
                    )
                    continue

        doc.close()
        log.info(f"Extracted {len(extracted_images)} images from {pdf_path.name}")

    except Exception as e:
        log.error(f"Failed to open or process PDF: {pdf_path}, error={e}")
        raise

    return extracted_images


def save_extracted_images(
    images: List[ExtractedImage],
    output_dir: Path,
    doc_id: str,
) -> List[Path]:
    """
    추출된 이미지를 파일로 저장

    Args:
        images: 추출된 이미지 리스트
        output_dir: 저장할 디렉토리
        doc_id: 문서 ID (파일명에 사용)

    Returns:
        저장된 이미지 파일 경로 리스트
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    saved_paths: List[Path] = []

    for img in images:
        # 파일명 생성: doc_id_p{page}_i{index}_{type}.{ext}
        filename = f"{doc_id}_p{img.page_num:03d}_i{img.image_index:02d}_{img.image_type}.{img.image_format}"
        output_path = output_dir / filename

        try:
            output_path.write_bytes(img.image_data)
            saved_paths.append(output_path)
            log.debug(f"Saved image: {output_path}")
        except Exception as e:
            log.warning(f"Failed to save image: {filename}, error={e}")
            continue

    log.info(f"Saved {len(saved_paths)} images to {output_dir}")
    return saved_paths


def filter_images_by_type(
    images: List[ExtractedImage],
    image_type: str,
) -> List[ExtractedImage]:
    """
    특정 타입의 이미지만 필터링

    Args:
        images: 추출된 이미지 리스트
        image_type: "table" | "figure" | "unknown"

    Returns:
        필터링된 이미지 리스트
    """
    return [img for img in images if img.image_type == image_type]


def capture_table_region_by_rendering(
    pdf_path: Path,
    page_num: int,
    bbox: Tuple[float, float, float, float],
    dpi: int = 200,
    padding: int = 20,
    extend_to_bottom: bool = True,
) -> Optional[bytes]:
    """
    페이지 렌더링을 통해 표 영역 캡처 (임베드 이미지 대체)

    PDF에 삽입된 이미지가 표의 일부분만 포함할 경우,
    페이지를 렌더링하여 전체 표 영역을 캡처합니다.

    Args:
        pdf_path: PDF 파일 경로
        page_num: 페이지 번호 (1-based)
        bbox: 기준 영역 (x0, y0, x1, y1)
        dpi: 렌더링 해상도
        padding: 여백 (points)
        extend_to_bottom: True면 페이지 하단까지 확장

    Returns:
        PNG 이미지 바이너리, 실패 시 None
    """
    try:
        doc = fitz.open(pdf_path)
        page_idx = page_num - 1

        if page_idx < 0 or page_idx >= len(doc):
            log.warning(f"[RENDER] Invalid page number: {page_num}")
            doc.close()
            return None

        page = doc[page_idx]
        x0, y0, x1, y1 = bbox

        # 여백 적용
        x0 = max(0, x0 - padding)
        y0 = max(0, y0 - padding)
        x1 = min(page.rect.width, x1 + padding)

        # 하단 확장 옵션
        if extend_to_bottom:
            # 페이지 하단에서 약간의 여백만 남기고 확장
            y1 = min(page.rect.height - 20, page.rect.height)
        else:
            y1 = min(page.rect.height, y1 + padding)

        clip_rect = fitz.Rect(x0, y0, x1, y1)

        # 고해상도 렌더링
        zoom = dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=matrix, clip=clip_rect)

        image_data = pix.tobytes("png")
        doc.close()

        log.info(
            f"[RENDER] Captured table region: page={page_num}, "
            f"bbox=({x0:.0f},{y0:.0f},{x1:.0f},{y1:.0f}), "
            f"size={len(image_data)} bytes"
        )
        return image_data

    except Exception as e:
        log.error(f"[RENDER] Failed to capture table region: {e}")
        return None


def extract_images_with_full_tables(pdf_path: Path) -> List[ExtractedImage]:
    """
    PDF에서 이미지 추출 + 표 영역 전체 캡처

    임베드된 이미지가 표의 일부만 포함할 경우,
    페이지 렌더링으로 전체 표 영역을 캡처하여 대체합니다.

    Args:
        pdf_path: PDF 파일 경로

    Returns:
        추출된 이미지 리스트 (표 이미지는 전체 영역으로 대체됨)
    """
    extracted_images: List[ExtractedImage] = []

    try:
        doc = fitz.open(pdf_path)
        log.info(f"[FULL_TABLE] Opened PDF: {pdf_path.name}, pages={len(doc)}")

        for page_idx in range(len(doc)):
            page = doc[page_idx]
            page_num = page_idx + 1
            image_list = page.get_images(full=True)

            log.debug(f"[FULL_TABLE] Page {page_num}: found {len(image_list)} images")

            for img_index, img_info in enumerate(image_list):
                try:
                    xref = img_info[0]
                    base_image = doc.extract_image(xref)

                    if not base_image:
                        continue

                    original_bytes = base_image["image"]
                    image_ext = base_image["ext"]

                    # PIL Image로 메타데이터 추출
                    pil_image = Image.open(BytesIO(original_bytes))
                    width, height = pil_image.size

                    # 이미지 타입 분류
                    img_type = _classify_image_type(pil_image)

                    # 이미지 위치 (바운딩 박스) 추출
                    rects = page.get_image_rects(xref)
                    if not rects:
                        continue
                    rect = rects[0]
                    bbox = (rect.x0, rect.y0, rect.x1, rect.y1)

                    # 표 타입이면 페이지 렌더링으로 전체 영역 캡처
                    final_image_data = original_bytes
                    final_format = image_ext
                    final_width = width
                    final_height = height

                    if img_type == "table":
                        log.info(
                            f"[FULL_TABLE] Table detected at page={page_num}, "
                            f"attempting full region capture..."
                        )

                        # 표 영역 확장 캡처 (y0부터 페이지 하단까지)
                        rendered = capture_table_region_by_rendering(
                            pdf_path=pdf_path,
                            page_num=page_num,
                            bbox=bbox,
                            dpi=200,
                            padding=10,
                            extend_to_bottom=True,
                        )

                        if rendered:
                            final_image_data = rendered
                            final_format = "png"
                            # 새 이미지 크기 확인
                            rendered_img = Image.open(BytesIO(rendered))
                            final_width, final_height = rendered_img.size
                            log.info(
                                f"[FULL_TABLE] Replaced with rendered image: "
                                f"{width}x{height} -> {final_width}x{final_height}"
                            )

                    extracted_img = ExtractedImage(
                        page_num=page_num,
                        image_index=img_index,
                        image_type=img_type,
                        bbox=bbox,
                        width=final_width,
                        height=final_height,
                        image_data=final_image_data,
                        image_format=final_format,
                    )

                    extracted_images.append(extracted_img)
                    log.debug(
                        f"[FULL_TABLE] Extracted: page={page_num}, index={img_index}, "
                        f"type={img_type}, size={final_width}x{final_height}"
                    )

                except Exception as e:
                    log.warning(
                        f"[FULL_TABLE] Failed to extract image: "
                        f"page={page_num}, index={img_index}, error={e}"
                    )
                    continue

        doc.close()
        log.info(f"[FULL_TABLE] Extracted {len(extracted_images)} images from {pdf_path.name}")

    except Exception as e:
        log.error(f"[FULL_TABLE] Failed to process PDF: {pdf_path}, error={e}")
        raise

    return extracted_images
