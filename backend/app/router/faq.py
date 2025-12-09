# backend/app/router/faq.py
"""
FAQ API 엔드포인트
"""
from typing import List
from fastapi import APIRouter, Query

from app.services.faq import get_faq
from app.services.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.get("/")
async def get_faq_list(
    force_refresh: bool = Query(False, description="강제 새로고침 여부")
) -> List[dict]:
    """
    FAQ 목록을 반환합니다.

    - 캐시된 FAQ가 있으면 캐시를 반환
    - 없으면 자동으로 생성
    - force_refresh=true 시 강제로 재생성

    Returns:
        [
            {
                "question": "연차는 몇 일인가요?",
                "count": 15
            },
            ...
        ]
    """
    faq_list = await get_faq(force_refresh=force_refresh)
    logger.debug(f"FAQ 반환: {len(faq_list)}개")
    return faq_list
