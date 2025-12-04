# backend/app/services/embedding.py
"""
임베딩 서비스 - P1-1 성능 최적화 + 비동기 지원

Features:
- LRU 캐싱 (In-Memory): 동일 텍스트 재사용 시 API 호출 없이 즉시 반환
- 최대 10,000개 캐싱 (~600MB 메모리)
- 비동기 임베딩 API (동시성 제어 포함)
"""

from typing import List, Optional
from functools import lru_cache
import hashlib
import asyncio
import threading

from app.services.openai_client import (
    get_client,
    call_embedding_async,
    call_embeddings_batch_async,
)
from app.config import settings
from app.services.logging import get_logger

log = get_logger(__name__)

_client_singleton = get_client()

# 캐시용 락 (비동기 환경에서 동시 캐시 접근 방지)
_cache_lock = threading.Lock()


# LRU 캐시: 텍스트 → 임베딩 해시 → 임베딩 벡터
# 튜플로 변환하여 해시 가능하게 만듦
@lru_cache(maxsize=10000)
def _embed_single_cached(text_hash: str, text: str, model: str) -> tuple:
    """
    단일 텍스트 임베딩 (캐싱) - 동기 버전

    Args:
        text_hash: 텍스트 해시 (캐시 키용)
        text: 실제 텍스트
        model: 임베딩 모델명

    Returns:
        임베딩 벡터 (tuple)
    """
    log.debug(f"[EMBEDDING] Cache miss for hash {text_hash[:8]}... - calling API")

    resp = _client_singleton.embeddings.create(
        model=model,
        input=[text],
    )

    embedding = resp.data[0].embedding
    return tuple(embedding)  # 리스트 → 튜플 (해시 가능)


# 비동기 캐시 저장소 (LRU 캐시와 별도)
_async_cache: dict[str, tuple] = {}
_async_cache_order: list[str] = []  # LRU 순서 추적
_async_cache_maxsize = 10000


def _get_text_hash(text: str) -> str:
    """텍스트 해시 생성 (캐시 키용)"""
    return hashlib.md5(text.encode('utf-8')).hexdigest()


def embed_texts(
    texts: List[str],
    model: Optional[str] = None,
    dimensions: Optional[int] = None,
) -> List[List[float]]:
    """
    여러 텍스트를 한 번에 임베딩 (캐싱 지원)

    Args:
        texts: 임베딩할 텍스트 리스트
        model: 임베딩 모델 (기본: settings.openai_embed_model)
        dimensions: 차원 수 (선택)

    Returns:
        임베딩 벡터 리스트
    """
    if not texts:
        return []

    model_name = model or settings.openai_embed_model

    # dimensions 지원하지 않으면 캐싱 없이 직접 호출
    if dimensions:
        log.debug("[EMBEDDING] Using dimensions parameter - bypassing cache")
        resp = _client_singleton.embeddings.create(
            model=model_name,
            input=texts,
            dimensions=dimensions,
        )
        return [d.embedding for d in resp.data]

    # 캐싱 사용
    embeddings = []
    cache_hits = 0
    cache_misses = 0

    for text in texts:
        text_hash = _get_text_hash(text)
        embedding_tuple = _embed_single_cached(text_hash, text, model_name)
        embeddings.append(list(embedding_tuple))  # 튜플 → 리스트

        # 캐시 적중 여부 확인 (LRU 캐시 내부 통계)
        cache_info = _embed_single_cached.cache_info()
        if cache_info.hits > cache_hits + cache_misses:
            cache_hits += 1
        else:
            cache_misses += 1

    if len(texts) > 1:
        log.debug(f"임베딩 {len(texts)}개: hit={cache_hits}, miss={cache_misses}")

    return embeddings


def embed_query(text: str, model: Optional[str] = None) -> List[float]:
    """
    질의 한 건 임베딩 (캐싱 지원)

    Args:
        text: 임베딩할 텍스트
        model: 임베딩 모델

    Returns:
        임베딩 벡터
    """
    embs = embed_texts([text], model=model)
    return embs[0] if embs else []


def get_cache_stats() -> dict:
    """
    임베딩 캐시 통계 조회

    Returns:
        {
            "hits": 캐시 적중 횟수,
            "misses": 캐시 미스 횟수,
            "maxsize": 최대 캐시 크기,
            "currsize": 현재 캐시 항목 수
        }
    """
    info = _embed_single_cached.cache_info()
    return {
        "hits": info.hits,
        "misses": info.misses,
        "maxsize": info.maxsize,
        "currsize": info.currsize,
        "hit_rate": info.hits / (info.hits + info.misses) if (info.hits + info.misses) > 0 else 0.0
    }


def clear_cache():
    """임베딩 캐시 초기화"""
    global _async_cache, _async_cache_order
    _embed_single_cached.cache_clear()
    with _cache_lock:
        _async_cache.clear()
        _async_cache_order.clear()
    log.info("[EMBEDDING] Cache cleared (sync + async)")


# =============================================================================
# 비동기 임베딩 API (권장)
# =============================================================================

def _async_cache_get(text_hash: str) -> Optional[tuple]:
    """비동기 캐시에서 조회"""
    with _cache_lock:
        if text_hash in _async_cache:
            # LRU 순서 업데이트
            if text_hash in _async_cache_order:
                _async_cache_order.remove(text_hash)
            _async_cache_order.append(text_hash)
            return _async_cache[text_hash]
    return None


def _async_cache_set(text_hash: str, embedding: tuple):
    """비동기 캐시에 저장"""
    global _async_cache, _async_cache_order
    with _cache_lock:
        # 캐시 크기 초과 시 오래된 항목 제거
        while len(_async_cache) >= _async_cache_maxsize and _async_cache_order:
            oldest = _async_cache_order.pop(0)
            _async_cache.pop(oldest, None)

        _async_cache[text_hash] = embedding
        _async_cache_order.append(text_hash)


async def embed_query_async(text: str, model: Optional[str] = None) -> List[float]:
    """
    비동기 질의 임베딩 (캐싱 + 동시성 제어)

    Args:
        text: 임베딩할 텍스트
        model: 임베딩 모델

    Returns:
        임베딩 벡터
    """
    model_name = model or settings.openai_embed_model
    text_hash = _get_text_hash(text)

    # 캐시 확인
    cached = _async_cache_get(text_hash)
    if cached is not None:
        log.debug(f"[EMBEDDING-ASYNC] Cache hit for hash {text_hash[:8]}...")
        return list(cached)

    # API 호출 (동시성 제어 포함)
    log.debug(f"[EMBEDDING-ASYNC] Cache miss for hash {text_hash[:8]}... - calling API")
    embedding = await call_embedding_async(text, model=model_name)

    # 캐시 저장
    _async_cache_set(text_hash, tuple(embedding))

    return embedding


async def embed_texts_async(
    texts: List[str],
    model: Optional[str] = None,
) -> List[List[float]]:
    """
    비동기 다중 텍스트 임베딩 (캐싱 + 동시성 제어)

    Args:
        texts: 임베딩할 텍스트 리스트
        model: 임베딩 모델

    Returns:
        임베딩 벡터 리스트
    """
    if not texts:
        return []

    model_name = model or settings.openai_embed_model

    # 캐시 확인 및 미스 목록 생성
    results: List[Optional[List[float]]] = [None] * len(texts)
    uncached_indices: List[int] = []
    uncached_texts: List[str] = []

    for i, text in enumerate(texts):
        text_hash = _get_text_hash(text)
        cached = _async_cache_get(text_hash)
        if cached is not None:
            results[i] = list(cached)
        else:
            uncached_indices.append(i)
            uncached_texts.append(text)

    cache_hits = len(texts) - len(uncached_texts)
    log.debug(f"[EMBEDDING-ASYNC] {len(texts)} texts: cache_hits={cache_hits}, misses={len(uncached_texts)}")

    # 미스된 텍스트만 API 호출
    if uncached_texts:
        embeddings = await call_embeddings_batch_async(uncached_texts, model=model_name)

        for idx, embedding in zip(uncached_indices, embeddings):
            results[idx] = embedding
            # 캐시 저장
            text_hash = _get_text_hash(texts[idx])
            _async_cache_set(text_hash, tuple(embedding))

    return results


async def embed_query_parallel(
    texts: List[str],
    model: Optional[str] = None,
) -> List[List[float]]:
    """
    여러 쿼리를 병렬로 임베딩 (각각 독립적으로 처리)

    Args:
        texts: 임베딩할 텍스트 리스트
        model: 임베딩 모델

    Returns:
        임베딩 벡터 리스트 (입력 순서 유지)
    """
    if not texts:
        return []

    tasks = [embed_query_async(text, model=model) for text in texts]
    return await asyncio.gather(*tasks)


def get_async_cache_stats() -> dict:
    """
    비동기 캐시 통계 조회

    Returns:
        캐시 통계 딕셔너리
    """
    with _cache_lock:
        return {
            "currsize": len(_async_cache),
            "maxsize": _async_cache_maxsize,
        }
