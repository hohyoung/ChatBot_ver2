"""
OpenAI Vision API를 사용한 이미지 처리 모듈

- 표 이미지 → 마크다운 표 변환
- 그림 이미지 → 자연어 설명 생성
"""

from __future__ import annotations

import base64
from typing import Optional, Dict, Any
from pathlib import Path

from app.services.openai_client import get_client
from app.config import settings
from app.services.logging import get_logger
from app.ingest.parsers.image_extractor import ExtractedImage

log = get_logger("app.ingest.parsers.vision_processor")


def _encode_image_to_base64(image_data: bytes) -> str:
    """이미지 바이트를 base64 문자열로 인코딩"""
    return base64.b64encode(image_data).decode('utf-8')


async def process_table_image(image: ExtractedImage) -> Optional[str]:
    """
    표 이미지를 마크다운 표로 변환

    Args:
        image: 추출된 표 이미지

    Returns:
        마크다운 표 문자열, 실패 시 None

    Example output:
        | 항목 | 1년차 | 2년차 | 3년차 |
        |------|------|------|------|
        | 연차 | 11일 | 15일 | 16일 |
    """
    try:
        # 이미지를 base64로 인코딩
        base64_image = _encode_image_to_base64(image.image_data)
        image_url = f"data:image/{image.image_format};base64,{base64_image}"

        # Vision API 호출
        client = get_client()
        response = client.chat.completions.create(
            model=settings.openai_model,  # gpt-4o supports vision
            messages=[
                {
                    "role": "system",
                    "content": (
                        "당신은 이미지에서 표를 추출하는 전문가입니다. "
                        "이미지 내 표를 정확하게 마크다운 표 형식으로 변환하세요.\n\n"
                        "규칙:\n"
                        "1. 표의 모든 셀 내용을 빠짐없이 추출\n"
                        "2. 헤더 행과 데이터 행을 구분\n"
                        "3. 표준 마크다운 표 형식 사용\n"
                        "4. 숫자, 단위, 특수문자 정확히 보존\n"
                        "5. 병합된 셀은 적절히 처리\n\n"
                        "출력은 마크다운 표만 작성하고, 추가 설명은 불필요합니다."
                    )
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "다음 이미지의 표를 마크다운 형식으로 변환해주세요:"
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": image_url,
                                "detail": "high"  # 고해상도 분석
                            }
                        }
                    ]
                }
            ],
            max_tokens=1500,
            temperature=0.1,  # 정확성 우선
        )

        markdown_table = response.choices[0].message.content.strip()

        # 마크다운 표 형식 검증 (간단한 체크)
        if "|" not in markdown_table or "---" not in markdown_table:
            log.warning(f"Invalid markdown table format: page={image.page_num}, index={image.image_index}")
            return None

        log.info(
            f"Converted table to markdown: page={image.page_num}, index={image.image_index}, "
            f"length={len(markdown_table)}"
        )
        return markdown_table

    except Exception as e:
        log.error(
            f"Failed to process table image: page={image.page_num}, index={image.image_index}, error={e}"
        )
        return None


async def process_figure_image(image: ExtractedImage) -> Optional[str]:
    """
    그림 이미지의 자연어 설명 생성

    Args:
        image: 추출된 그림 이미지

    Returns:
        그림 설명 문자열, 실패 시 None

    Example output:
        "조직도: CEO 아래 3개 부서(개발, 마케팅, 인사)로 구성된 계층 구조"
    """
    try:
        # 이미지를 base64로 인코딩
        base64_image = _encode_image_to_base64(image.image_data)
        image_url = f"data:image/{image.image_format};base64,{base64_image}"

        # Vision API 호출
        client = get_client()
        response = client.chat.completions.create(
            model=settings.openai_model,  # gpt-4o supports vision
            messages=[
                {
                    "role": "system",
                    "content": (
                        "당신은 문서 내 그림을 분석하는 전문가입니다. "
                        "그림의 내용을 간결하고 정확하게 설명하세요.\n\n"
                        "규칙:\n"
                        "1. 그림의 핵심 내용을 1-3문장으로 요약\n"
                        "2. 차트/다이어그램의 경우 유형과 주요 데이터 명시\n"
                        "3. 조직도/프로세스도의 경우 구조와 흐름 설명\n"
                        "4. 불필요한 수식어 제거, 사실 중심 서술\n"
                        "5. 한국어로 작성"
                    )
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "다음 이미지의 내용을 간결하게 설명해주세요:"
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": image_url,
                                "detail": "high"
                            }
                        }
                    ]
                }
            ],
            max_tokens=500,
            temperature=0.2,
        )

        description = response.choices[0].message.content.strip()

        log.info(
            f"Generated figure description: page={image.page_num}, index={image.image_index}, "
            f"length={len(description)}"
        )
        return description

    except Exception as e:
        log.error(
            f"Failed to process figure image: page={image.page_num}, index={image.image_index}, error={e}"
        )
        return None


async def batch_process_images(
    images: list[ExtractedImage],
    max_concurrent: int = 5,
) -> Dict[str, Any]:
    """
    여러 이미지를 병렬로 처리

    Args:
        images: 추출된 이미지 리스트
        max_concurrent: 동시 처리 개수 (API rate limit 고려)

    Returns:
        {
            "tables": [(image, markdown_table), ...],
            "figures": [(image, description), ...],
            "failed": [image, ...]
        }
    """
    import asyncio

    results = {
        "tables": [],
        "figures": [],
        "failed": []
    }

    # 이미지 타입별 분류
    table_images = [img for img in images if img.image_type == "table"]
    figure_images = [img for img in images if img.image_type == "figure"]

    # 세마포어를 사용하여 동시 요청 수 제한
    semaphore = asyncio.Semaphore(max_concurrent)

    async def process_with_semaphore(img: ExtractedImage, processor):
        async with semaphore:
            result = await processor(img)
            return img, result

    # 표 처리
    log.info(f"Processing {len(table_images)} table images...")
    table_tasks = [
        process_with_semaphore(img, process_table_image)
        for img in table_images
    ]
    table_results = await asyncio.gather(*table_tasks, return_exceptions=True)

    for item in table_results:
        if isinstance(item, Exception):
            log.error(f"Table processing exception: {item}")
            continue
        img, markdown = item
        if markdown:
            results["tables"].append((img, markdown))
        else:
            results["failed"].append(img)

    # 그림 처리
    log.info(f"Processing {len(figure_images)} figure images...")
    figure_tasks = [
        process_with_semaphore(img, process_figure_image)
        for img in figure_images
    ]
    figure_results = await asyncio.gather(*figure_tasks, return_exceptions=True)

    for item in figure_results:
        if isinstance(item, Exception):
            log.error(f"Figure processing exception: {item}")
            continue
        img, description = item
        if description:
            results["figures"].append((img, description))
        else:
            results["failed"].append(img)

    log.info(
        f"Batch processing complete: tables={len(results['tables'])}, "
        f"figures={len(results['figures'])}, failed={len(results['failed'])}"
    )

    return results
