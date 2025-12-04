"""
OpenAI 클라이언트 관리 - P0-7 라운드로빈 + 동시성 제어

사용법:
    # 동기 호출 (권장하지 않음)
    from app.services.openai_client import get_client
    client = get_client()
    response = client.chat.completions.create(...)

    # 비동기 호출 (권장)
    from app.services.openai_client import get_async_client, call_openai_async

    # 방법 1: 직접 비동기 클라이언트 사용
    client = get_async_client()
    response = await client.chat.completions.create(...)

    # 방법 2: 동시성 제어가 포함된 래퍼 사용 (권장)
    response = await call_openai_async(
        "chat.completions.create",
        model="gpt-4o",
        messages=[...]
    )
"""

from __future__ import annotations
import asyncio
import threading
from typing import Dict, Any, Optional, Callable, TypeVar
from functools import wraps
from openai import OpenAI, AsyncOpenAI

from app.config import settings
from app.services.logging import get_logger

log = get_logger(__name__)

T = TypeVar("T")

# =============================================================================
# 동시성 제어 - Semaphore
# =============================================================================

# 동시 OpenAI API 호출 제한 (기본값: 5)
# 환경 변수로 조정 가능: OPENAI_MAX_CONCURRENT=10
import os
MAX_CONCURRENT_CALLS = int(os.getenv("OPENAI_MAX_CONCURRENT", "5"))

# 전역 Semaphore (비동기 호출용)
_api_semaphore: Optional[asyncio.Semaphore] = None
_semaphore_lock = threading.Lock()


def _get_semaphore() -> asyncio.Semaphore:
    """이벤트 루프별 Semaphore 반환 (지연 초기화)"""
    global _api_semaphore
    if _api_semaphore is None:
        with _semaphore_lock:
            if _api_semaphore is None:
                _api_semaphore = asyncio.Semaphore(MAX_CONCURRENT_CALLS)
                log.info(
                    f"[OpenAI] Initialized semaphore with max_concurrent={MAX_CONCURRENT_CALLS}"
                )
    return _api_semaphore


async def with_concurrency_limit(coro):
    """동시성 제한을 적용하여 코루틴 실행"""
    semaphore = _get_semaphore()
    async with semaphore:
        return await coro


class OpenAIClientPool:
    """
    OpenAI 클라이언트 풀 - 라운드로빈 방식

    여러 API 키를 순환하며 부하 분산:
    - 질문1 → 키1
    - 질문2 → 키2
    - 질문3 → 키3
    - 질문4 → 키1 (순환)
    """

    def __init__(self, api_keys: list[str], base_url: str | None = None):
        if not api_keys:
            raise ValueError("At least one API key is required")

        self.api_keys = api_keys
        self.base_url = base_url
        self.current_index = 0
        self.lock = threading.Lock()

        # 키별 사용량 통계
        self.usage_stats: Dict[str, Dict[str, int]] = {
            key: {"requests": 0, "errors": 0, "rate_limits": 0}
            for key in api_keys
        }

        # 클라이언트 풀 생성
        self.clients = [
            OpenAI(api_key=key, base_url=base_url) if base_url else OpenAI(api_key=key)
            for key in api_keys
        ]

        log.info(
            f"[OpenAIClientPool] Initialized with {len(api_keys)} API keys "
            f"(base_url={base_url or 'default'})"
        )

    def get_client(self) -> OpenAI:
        """
        라운드로빈 방식으로 다음 클라이언트 반환

        Returns:
            OpenAI 클라이언트
        """
        with self.lock:
            client = self.clients[self.current_index]
            key_suffix = self.api_keys[self.current_index][-8:]  # 마지막 8자리만

            # 사용량 증가
            self.usage_stats[self.api_keys[self.current_index]]["requests"] += 1

            # 다음 인덱스로 이동 (순환)
            self.current_index = (self.current_index + 1) % len(self.clients)

            log.debug(
                f"[OpenAIClientPool] Serving client with key ...{key_suffix} "
                f"(next: {self.current_index})"
            )

            return client

    def record_error(self, client: OpenAI, is_rate_limit: bool = False):
        """
        에러 기록 (통계용)

        Args:
            client: 에러가 발생한 클라이언트
            is_rate_limit: 429 Rate Limit 에러 여부
        """
        with self.lock:
            for i, c in enumerate(self.clients):
                if c is client:
                    key = self.api_keys[i]
                    self.usage_stats[key]["errors"] += 1
                    if is_rate_limit:
                        self.usage_stats[key]["rate_limits"] += 1
                    break

    def get_stats(self) -> Dict[str, Dict[str, int]]:
        """
        키별 사용량 통계 조회

        Returns:
            키별 통계 딕셔너리
        """
        with self.lock:
            # 키의 마지막 8자리만 표시
            return {
                f"...{key[-8:]}": stats.copy()
                for key, stats in self.usage_stats.items()
            }

    def print_stats(self):
        """통계 출력 (디버깅용)"""
        stats = self.get_stats()
        log.info("[OpenAIClientPool] Usage Statistics:")
        for key_suffix, data in stats.items():
            log.info(
                f"  Key {key_suffix}: "
                f"requests={data['requests']}, "
                f"errors={data['errors']}, "
                f"rate_limits={data['rate_limits']}"
            )


# 싱글턴 풀 생성
_pool = OpenAIClientPool(
    api_keys=settings.openai_api_keys, base_url=settings.openai_base_url
)


def get_client() -> OpenAI:
    """
    라운드로빈 OpenAI 클라이언트 반환

    Returns:
        OpenAI 클라이언트 (자동 순환)
    """
    return _pool.get_client()


def get_pool() -> OpenAIClientPool:
    """
    클라이언트 풀 반환 (통계 조회용)

    Returns:
        OpenAIClientPool 인스턴스
    """
    return _pool


# 비동기 클라이언트 (vision_processor 등에서 사용)
_async_clients: list[AsyncOpenAI] = []
_async_index = 0
_async_lock = threading.Lock()


def get_async_client() -> AsyncOpenAI:
    """
    라운드로빈 비동기 OpenAI 클라이언트 반환

    Returns:
        AsyncOpenAI 클라이언트 (자동 순환)
    """
    global _async_clients, _async_index

    # 지연 초기화
    if not _async_clients:
        with _async_lock:
            if not _async_clients:
                _async_clients = [
                    AsyncOpenAI(api_key=key, base_url=settings.openai_base_url)
                    if settings.openai_base_url
                    else AsyncOpenAI(api_key=key)
                    for key in settings.openai_api_keys
                ]
                log.info(f"[AsyncOpenAI] Initialized {len(_async_clients)} async clients")

    with _async_lock:
        client = _async_clients[_async_index]
        _async_index = (_async_index + 1) % len(_async_clients)
        return client


# =============================================================================
# 비동기 API 래퍼 (동시성 제어 포함)
# =============================================================================

async def call_chat_completion_async(
    *,
    model: str = None,
    messages: list,
    stream: bool = False,
    **kwargs
) -> Any:
    """
    비동기 Chat Completion API 호출 (동시성 제어 포함)

    Args:
        model: 모델명 (기본값: settings.openai_model)
        messages: 메시지 리스트
        stream: 스트리밍 여부
        **kwargs: 추가 파라미터

    Returns:
        ChatCompletion 응답 또는 AsyncStream
    """
    client = get_async_client()
    model = model or settings.openai_model

    async def _call():
        return await client.chat.completions.create(
            model=model,
            messages=messages,
            stream=stream,
            **kwargs
        )

    # 스트리밍은 Semaphore 획득 후 반환 (스트림 종료까지 유지됨)
    if stream:
        semaphore = _get_semaphore()
        await semaphore.acquire()
        try:
            return await _call()
        except Exception:
            semaphore.release()
            raise
        # 주의: 스트리밍의 경우 호출자가 스트림 소비 후 release 필요
    else:
        return await with_concurrency_limit(_call())


async def call_embedding_async(
    text: str,
    *,
    model: str = None,
) -> list[float]:
    """
    비동기 Embedding API 호출 (동시성 제어 포함)

    Args:
        text: 임베딩할 텍스트
        model: 임베딩 모델명 (기본값: settings.embedding_model)

    Returns:
        임베딩 벡터 (1536차원)
    """
    client = get_async_client()
    model = model or getattr(settings, "embedding_model", "text-embedding-3-small")

    async def _call():
        response = await client.embeddings.create(
            model=model,
            input=text
        )
        return response.data[0].embedding

    return await with_concurrency_limit(_call())


async def call_embeddings_batch_async(
    texts: list[str],
    *,
    model: str = None,
    batch_size: int = 20,
) -> list[list[float]]:
    """
    비동기 Embedding 배치 호출 (동시성 제어 + 배치 처리)

    Args:
        texts: 임베딩할 텍스트 리스트
        model: 임베딩 모델명
        batch_size: 배치 크기 (기본값: 20)

    Returns:
        임베딩 벡터 리스트
    """
    client = get_async_client()
    model = model or getattr(settings, "embedding_model", "text-embedding-3-small")

    all_embeddings = []

    # 배치로 분할
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]

        async def _call_batch(batch_texts):
            response = await client.embeddings.create(
                model=model,
                input=batch_texts
            )
            return [item.embedding for item in response.data]

        batch_embeddings = await with_concurrency_limit(_call_batch(batch))
        all_embeddings.extend(batch_embeddings)

    return all_embeddings


class StreamingContextManager:
    """스트리밍 응답용 컨텍스트 매니저 (Semaphore 자동 해제)"""

    def __init__(self, stream, semaphore: asyncio.Semaphore):
        self.stream = stream
        self.semaphore = semaphore

    async def __aenter__(self):
        return self.stream

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.semaphore.release()
        return False

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return await self.stream.__anext__()
        except StopAsyncIteration:
            self.semaphore.release()
            raise


async def call_chat_completion_stream_async(
    *,
    model: str = None,
    messages: list,
    **kwargs
) -> StreamingContextManager:
    """
    비동기 Chat Completion 스트리밍 (Semaphore 자동 해제)

    사용법:
        async for chunk in await call_chat_completion_stream_async(messages=[...]):
            token = chunk.choices[0].delta.content
            ...
        # 자동으로 Semaphore 해제됨

    Returns:
        StreamingContextManager (async iterator)
    """
    client = get_async_client()
    model = model or settings.openai_model

    semaphore = _get_semaphore()
    await semaphore.acquire()

    try:
        stream = await client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            **kwargs
        )
        return StreamingContextManager(stream, semaphore)
    except Exception:
        semaphore.release()
        raise


def get_concurrency_stats() -> dict:
    """동시성 통계 반환"""
    semaphore = _get_semaphore()
    return {
        "max_concurrent": MAX_CONCURRENT_CALLS,
        "available_slots": semaphore._value if hasattr(semaphore, '_value') else "unknown",
        "pool_stats": _pool.get_stats(),
    }
