"""
OpenAI Vision API를 사용한 이미지 처리 모듈

- 표 이미지 → 마크다운 표 변환
- 그림 이미지 → 자연어 설명 생성
"""

from __future__ import annotations

import asyncio
import base64
from typing import Optional, Dict, Any
from pathlib import Path

from app.services.openai_client import get_async_client
from app.config import settings
from app.services.logging import get_logger
from app.ingest.parsers.image_extractor import ExtractedImage

log = get_logger("app.ingest.parsers.vision_processor")

# Rate limiting: 요청 간 최소 대기 시간 (초)
REQUEST_DELAY = 0.5  # 500ms 간격으로 요청


def _encode_image_to_base64(image_data: bytes) -> str:
    """이미지 바이트를 base64 문자열로 인코딩"""
    return base64.b64encode(image_data).decode('utf-8')


async def process_table_image(image: ExtractedImage, retry_count: int = 3) -> Optional[str]:
    """
    표 이미지를 마크다운 표로 변환

    Args:
        image: 추출된 표 이미지
        retry_count: 재시도 횟수 (rate limit 대응)

    Returns:
        마크다운 표 문자열, 실패 시 None

    Example output:
        | 항목 | 1년차 | 2년차 | 3년차 |
        |------|------|------|------|
        | 연차 | 11일 | 15일 | 16일 |
    """
    for attempt in range(retry_count):
        try:
            # 이미지를 base64로 인코딩
            base64_image = _encode_image_to_base64(image.image_data)
            image_url = f"data:image/{image.image_format};base64,{base64_image}"

            # Vision API 호출 (비동기)
            client = get_async_client()
            response = await client.chat.completions.create(
                model=settings.openai_model,  # gpt-4o supports vision
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "당신은 한국어 문서의 복잡한 표를 완벽하게 추출하는 전문가입니다.\n\n"
                            "## 핵심 원칙\n"
                            "**표에 보이는 모든 텍스트를 누락 없이 추출해야 합니다.**\n"
                            "이미지를 위에서 아래로, 왼쪽에서 오른쪽으로 **스캔하듯이** 모든 내용을 읽으세요.\n\n"
                            "## 복합 표 처리 (매우 중요!)\n"
                            "하나의 이미지에 여러 개의 논리적 섹션이 있을 수 있습니다:\n"
                            "- 예: '평가대상자 예외적용', '평가항목 및 비율', '감점사항'이 한 이미지에 있음\n"
                            "- 예: '업적평가', '역량평가', '공통지표'가 하위 섹션으로 존재\n"
                            "**모든 섹션을 빠짐없이 별도의 마크다운 표로 추출하세요.**\n\n"
                            "## 출력 형식\n"
                            "### [섹션명]\n"
                            "| 헤더1 | 헤더2 | 헤더3 |\n"
                            "|-------|-------|-------|\n"
                            "| 값1   | 값2   | 값3   |\n\n"
                            "### [다음 섹션명]\n"
                            "| 헤더1 | 헤더2 |\n"
                            "|-------|-------|\n"
                            "| 값1   | 값2   |\n\n"
                            "## 상세 규칙\n"
                            "1. **모든 섹션 추출**: 이미지 상단부터 하단까지 모든 섹션 헤더를 찾아 각각 별도 표로\n"
                            "2. **모든 행 추출**: 각 섹션 내 모든 행을 누락 없이 추출\n"
                            "3. **모든 열 추출**: 좌측부터 우측까지 모든 열의 값을 추출\n"
                            "4. 중첩된 하위 항목은 들여쓰기 표현 (예: '└ 인당매출액' 또는 '- 인당매출액')\n"
                            "5. 병합된 셀(rowspan/colspan)은 해당 범위의 모든 행에 값을 반복\n"
                            "6. 숫자, 단위, 특수문자(%,원,일,점 등) 정확히 보존\n"
                            "7. 빈 셀은 공백으로 유지\n"
                            "8. 계층 구조가 있으면 부모-자식 관계를 명확히 표현\n\n"
                            "## 체크리스트 (출력 전 확인)\n"
                            "□ 이미지의 모든 섹션 헤더를 찾았는가?\n"
                            "□ 각 섹션의 모든 행을 추출했는가?\n"
                            "□ 각 행의 모든 열을 추출했는가?\n"
                            "□ 이미지 하단까지 확인했는가?\n\n"
                            "## 금지사항\n"
                            "- 설명이나 부연 작성 금지\n"
                            "- 섹션 제목(### )과 마크다운 표만 출력\n"
                            "- 이미지에 표가 없으면 'NO_TABLE'만 출력\n"
                            "- **일부만 추출하는 것 금지 - 반드시 전체를 완전히 추출**"
                        )
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "이 이미지의 표를 **완전히** 마크다운으로 변환하세요.\n\n"
                                    "1. 이미지 전체를 위에서 아래까지 스캔하세요\n"
                                    "2. 모든 섹션 헤더(예: 평가대상자, 평가항목, 감점사항 등)를 찾으세요\n"
                                    "3. 각 섹션의 모든 내용을 별도 마크다운 표로 출력하세요\n"
                                    "4. 설명 없이 ### 섹션명과 표만 출력하세요"
                                )
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
                max_tokens=8000,  # 복합 표 대응을 위해 더 증가
                temperature=0.0,  # 최대 정확성
            )

            markdown_table = response.choices[0].message.content.strip()

            # NO_TABLE 응답 처리
            if markdown_table == "NO_TABLE":
                log.warning(f"No table found in image: page={image.page_num}, index={image.image_index}")
                return None

            # 마크다운 코드 블록 제거 (```markdown ... ``` 형태로 올 수 있음)
            if markdown_table.startswith("```"):
                lines = markdown_table.split("\n")
                # 첫 줄과 마지막 줄의 ``` 제거
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                markdown_table = "\n".join(lines).strip()

            # 마크다운 표 형식 검증
            if "|" not in markdown_table or "---" not in markdown_table:
                log.warning(
                    f"Invalid markdown table format: page={image.page_num}, index={image.image_index}, "
                    f"content_preview={markdown_table[:100]}"
                )
                return None

            log.info(
                f"Converted table to markdown: page={image.page_num}, index={image.image_index}, "
                f"length={len(markdown_table)}"
            )
            return markdown_table

        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "rate_limit" in error_str.lower():
                # Rate limit: 지수 백오프 대기
                wait_time = (2 ** attempt) + 1  # 2, 3, 5초
                log.warning(
                    f"Rate limit hit for table image (page={image.page_num}), "
                    f"waiting {wait_time}s before retry {attempt + 1}/{retry_count}"
                )
                await asyncio.sleep(wait_time)
                continue
            else:
                log.error(
                    f"Failed to process table image: page={image.page_num}, index={image.image_index}, error={e}"
                )
                return None

    log.error(f"Failed to process table image after {retry_count} retries: page={image.page_num}")
    return None


async def process_figure_image(image: ExtractedImage, retry_count: int = 3) -> Optional[str]:
    """
    그림 이미지의 자연어 설명 생성

    Args:
        image: 추출된 그림 이미지
        retry_count: 재시도 횟수 (rate limit 대응)

    Returns:
        그림 설명 문자열, 실패 시 None

    Example output:
        "조직도: CEO 아래 3개 부서(개발, 마케팅, 인사)로 구성된 계층 구조"
    """
    for attempt in range(retry_count):
        try:
            # 이미지를 base64로 인코딩
            base64_image = _encode_image_to_base64(image.image_data)
            image_url = f"data:image/{image.image_format};base64,{base64_image}"

            # Vision API 호출 (비동기)
            client = get_async_client()
            response = await client.chat.completions.create(
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
            error_str = str(e)
            if "429" in error_str or "rate_limit" in error_str.lower():
                # Rate limit: 지수 백오프 대기
                wait_time = (2 ** attempt) + 1  # 2, 3, 5초
                log.warning(
                    f"Rate limit hit for figure image (page={image.page_num}), "
                    f"waiting {wait_time}s before retry {attempt + 1}/{retry_count}"
                )
                await asyncio.sleep(wait_time)
                continue
            else:
                log.error(
                    f"Failed to process figure image: page={image.page_num}, index={image.image_index}, error={e}"
                )
                return None

    log.error(f"Failed to process figure image after {retry_count} retries: page={image.page_num}")
    return None


async def batch_process_images(
    images: list[ExtractedImage],
    max_concurrent: int = 2,  # Rate limit 방지를 위해 낮춤
) -> Dict[str, Any]:
    """
    여러 이미지를 병렬로 처리

    Args:
        images: 추출된 이미지 리스트
        max_concurrent: 동시 처리 개수 (API rate limit 고려, 기본값 2)

    Returns:
        {
            "tables": [(image, markdown_table), ...],
            "figures": [(image, description), ...],
            "failed": [image, ...]
        }
    """
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
            # 요청 간 지연 추가 (rate limit 방지)
            await asyncio.sleep(REQUEST_DELAY)
            result = await processor(img)
            return img, result

    # 표 처리
    log.info(f"Processing {len(table_images)} table images (max_concurrent={max_concurrent})...")
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
    log.info(f"Processing {len(figure_images)} figure images (max_concurrent={max_concurrent})...")
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


# ===========================================================================
# 방안 B: 복잡한 표 Vision API 폴백
# ===========================================================================

async def process_complex_table_from_image(
    image_data: bytes,
    image_format: str = "png",
    page_num: int = 0,
    retry_count: int = 3,
) -> Optional[str]:
    """
    복잡한 표 이미지를 Vision API로 재처리 (방안 B)

    pdfplumber가 잘못 추출한 복잡한 표를 Vision API로 다시 분석합니다.

    Args:
        image_data: 표 영역 이미지 바이너리
        image_format: 이미지 포맷 (png, jpeg)
        page_num: 페이지 번호 (로깅용)
        retry_count: 재시도 횟수

    Returns:
        마크다운 표 문자열, 실패 시 None
    """
    for attempt in range(retry_count):
        try:
            base64_image = _encode_image_to_base64(image_data)
            image_url = f"data:image/{image_format};base64,{base64_image}"

            client = get_async_client()
            response = await client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "당신은 한국어 문서의 복잡한 표를 완벽하게 추출하는 전문가입니다.\n\n"
                            "## 핵심 원칙\n"
                            "**표에 보이는 모든 텍스트를 누락 없이 추출해야 합니다.**\n"
                            "이미지를 위에서 아래로, 왼쪽에서 오른쪽으로 **스캔하듯이** 모든 내용을 읽으세요.\n\n"
                            "## 복합 표 처리 (매우 중요!)\n"
                            "하나의 이미지에 여러 개의 논리적 섹션이 있을 수 있습니다:\n"
                            "- 예: '평가대상자 예외적용', '평가항목 및 비율', '감점사항'이 한 이미지에 있음\n"
                            "- 예: '업적평가', '역량평가', '공통지표'가 하위 섹션으로 존재\n"
                            "**모든 섹션을 빠짐없이 별도의 마크다운 표로 추출하세요.**\n\n"
                            "## 출력 형식\n"
                            "### [섹션명]\n"
                            "| 헤더1 | 헤더2 | 헤더3 |\n"
                            "|-------|-------|-------|\n"
                            "| 값1   | 값2   | 값3   |\n\n"
                            "### [다음 섹션명]\n"
                            "| 헤더1 | 헤더2 |\n"
                            "|-------|-------|\n"
                            "| 값1   | 값2   |\n\n"
                            "## 상세 규칙\n"
                            "1. **모든 섹션 추출**: 이미지 상단부터 하단까지 모든 섹션 헤더를 찾아 각각 별도 표로\n"
                            "2. **모든 행 추출**: 각 섹션 내 모든 행을 누락 없이 추출\n"
                            "3. **모든 열 추출**: 좌측부터 우측까지 모든 열의 값을 추출\n"
                            "4. 중첩된 하위 항목은 들여쓰기 표현 (예: '└ 인당매출액' 또는 '- 인당매출액')\n"
                            "5. 병합된 셀(rowspan/colspan)은 해당 범위의 모든 행에 값을 반복\n"
                            "6. 숫자, 단위, 특수문자(%,원,일,점 등) 정확히 보존\n"
                            "7. 빈 셀은 공백으로 유지\n"
                            "8. 계층 구조가 있으면 부모-자식 관계를 명확히 표현\n\n"
                            "## 체크리스트 (출력 전 확인)\n"
                            "□ 이미지의 모든 섹션 헤더를 찾았는가?\n"
                            "□ 각 섹션의 모든 행을 추출했는가?\n"
                            "□ 각 행의 모든 열을 추출했는가?\n"
                            "□ 이미지 하단까지 확인했는가?\n\n"
                            "## 금지사항\n"
                            "- 설명이나 부연 작성 금지\n"
                            "- 섹션 제목(### )과 마크다운 표만 출력\n"
                            "- 이미지에 표가 없으면 'NO_TABLE'만 출력\n"
                            "- **일부만 추출하는 것 금지 - 반드시 전체를 완전히 추출**"
                        )
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "이 이미지의 표를 **완전히** 마크다운으로 변환하세요.\n\n"
                                    "1. 이미지 전체를 위에서 아래까지 스캔하세요\n"
                                    "2. 모든 섹션 헤더(예: 평가대상자, 평가항목, 감점사항 등)를 찾으세요\n"
                                    "3. 각 섹션의 모든 내용을 별도 마크다운 표로 출력하세요\n"
                                    "4. 설명 없이 ### 섹션명과 표만 출력하세요"
                                )
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
                max_tokens=8000,
                temperature=0.0,
            )

            markdown_table = response.choices[0].message.content.strip()

            if markdown_table == "NO_TABLE":
                log.warning(f"[VISION_FALLBACK] No table found: page={page_num}")
                return None

            # 마크다운 코드 블록 제거
            if markdown_table.startswith("```"):
                lines = markdown_table.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                markdown_table = "\n".join(lines).strip()

            # 마크다운 표 형식 검증
            if "|" not in markdown_table or "---" not in markdown_table:
                log.warning(f"[VISION_FALLBACK] Invalid format: page={page_num}")
                return None

            log.info(
                f"[VISION_FALLBACK] Success: page={page_num}, length={len(markdown_table)}"
            )
            return markdown_table

        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "rate_limit" in error_str.lower():
                wait_time = (2 ** attempt) + 1
                log.warning(
                    f"[VISION_FALLBACK] Rate limit: page={page_num}, "
                    f"waiting {wait_time}s, retry {attempt + 1}/{retry_count}"
                )
                await asyncio.sleep(wait_time)
                continue
            else:
                log.error(f"[VISION_FALLBACK] Error: page={page_num}, error={e}")
                return None

    log.error(f"[VISION_FALLBACK] Failed after {retry_count} retries: page={page_num}")
    return None
