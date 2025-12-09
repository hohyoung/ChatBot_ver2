# backend/app/services/scheduler.py
"""
백그라운드 스케줄러

FAQ 자동 갱신 등의 정기 작업을 처리합니다.
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.services.faq import get_faq
from app.services.logging import get_logger

logger = get_logger(__name__)

# 스케줄러 인스턴스
_scheduler: AsyncIOScheduler = None


async def refresh_faq_task():
    """
    FAQ 갱신 작업

    매일 새벽 3시에 실행되어 FAQ를 새로 생성합니다.
    """
    try:
        faq_list = await get_faq(force_refresh=True)
        logger.debug(f"FAQ 자동 갱신: {len(faq_list)}개")
    except Exception as e:
        logger.error(f"FAQ 자동 갱신 실패: {e}")


def start_scheduler():
    """
    스케줄러를 시작합니다.
    """
    global _scheduler

    if _scheduler is not None:
        return

    _scheduler = AsyncIOScheduler()

    # FAQ 갱신 작업 스케줄링 (매일 새벽 3시)
    _scheduler.add_job(
        refresh_faq_task,
        trigger=CronTrigger(hour=3, minute=0),
        id="refresh_faq",
        name="FAQ 자동 갱신",
        replace_existing=True
    )

    _scheduler.start()
    logger.debug("스케줄러 시작")


def stop_scheduler():
    """
    스케줄러를 종료합니다.
    """
    global _scheduler

    if _scheduler is not None:
        _scheduler.shutdown()
        _scheduler = None
        logger.debug("스케줄러 종료")
