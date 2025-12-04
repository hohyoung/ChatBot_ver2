"""
재시도 로직 - P0-7

OpenAI API 호출 시 429/5xx 에러에 대한 자동 재시도

사용법:
    from app.services.retry import retry_with_backoff

    @retry_with_backoff(max_retries=3)
    async def call_openai():
        return await openai_client.chat.completions.create(...)

    result = await call_openai()
"""

from __future__ import annotations
import asyncio
import time
from typing import Callable, TypeVar, Any
from functools import wraps

from openai import RateLimitError, APIError, APIConnectionError

from app.services.logging import get_logger

log = get_logger(__name__)

T = TypeVar("T")


def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    retry_on: tuple = (RateLimitError, APIConnectionError, APIError),
):
    """
    지수 백오프 재시도 데코레이터

    Args:
        max_retries: 최대 재시도 횟수 (기본: 3)
        initial_delay: 초기 지연 시간 (초, 기본: 1.0)
        max_delay: 최대 지연 시간 (초, 기본: 60.0)
        backoff_factor: 백오프 계수 (기본: 2.0)
        retry_on: 재시도할 예외 타입 튜플

    Example:
        @retry_with_backoff(max_retries=5)
        async def call_api():
            return await client.chat.completions.create(...)
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> T:
            delay = initial_delay

            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except retry_on as e:
                    if attempt == max_retries - 1:
                        # 마지막 시도 실패 시 예외 발생
                        log.error(
                            f"[Retry] Failed after {max_retries} attempts: {e}"
                        )
                        raise

                    # 429 Rate Limit 또는 5xx 에러만 재시도
                    should_retry = False

                    if isinstance(e, RateLimitError):
                        should_retry = True
                        error_type = "RateLimitError (429)"
                    elif isinstance(e, (APIConnectionError, APIError)):
                        # 5xx 서버 에러만 재시도
                        if hasattr(e, "status_code") and e.status_code >= 500:
                            should_retry = True
                            error_type = f"ServerError ({e.status_code})"
                        else:
                            raise
                    else:
                        raise

                    if should_retry:
                        sleep_time = min(delay, max_delay)
                        log.warning(
                            f"[Retry] {error_type} encountered. "
                            f"Retrying in {sleep_time:.1f}s "
                            f"(attempt {attempt + 1}/{max_retries})"
                        )

                        await asyncio.sleep(sleep_time)
                        delay *= backoff_factor

                except Exception as e:
                    # 예상하지 못한 예외는 즉시 발생
                    log.error(f"[Retry] Unexpected error: {e}")
                    raise

            raise RuntimeError("Retry logic error")  # 도달 불가

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> T:
            delay = initial_delay

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except retry_on as e:
                    if attempt == max_retries - 1:
                        log.error(
                            f"[Retry] Failed after {max_retries} attempts: {e}"
                        )
                        raise

                    should_retry = False

                    if isinstance(e, RateLimitError):
                        should_retry = True
                        error_type = "RateLimitError (429)"
                    elif isinstance(e, (APIConnectionError, APIError)):
                        if hasattr(e, "status_code") and e.status_code >= 500:
                            should_retry = True
                            error_type = f"ServerError ({e.status_code})"
                        else:
                            raise
                    else:
                        raise

                    if should_retry:
                        sleep_time = min(delay, max_delay)
                        log.warning(
                            f"[Retry] {error_type} encountered. "
                            f"Retrying in {sleep_time:.1f}s "
                            f"(attempt {attempt + 1}/{max_retries})"
                        )

                        time.sleep(sleep_time)
                        delay *= backoff_factor

                except Exception as e:
                    log.error(f"[Retry] Unexpected error: {e}")
                    raise

            raise RuntimeError("Retry logic error")

        # async 함수인지 확인
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator
