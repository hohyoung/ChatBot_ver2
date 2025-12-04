# backend/app/services/redis_client.py
"""
Redis 클라이언트 설정 - P1-1 연결 풀링 적용

FAQ 캐싱, OTP 저장 등에 사용됩니다.

Features:
- ConnectionPool: 연결 재사용으로 오버헤드 감소
- 동시 연결 제한: max_connections=20 (다중 사용자 대응)
- 자동 재연결: health_check_interval=30
"""
import logging
from typing import Optional
import redis
import os

logger = logging.getLogger(__name__)

# Redis 연결 설정
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

# 연결 풀 설정 (P1-1 성능 최적화)
REDIS_MAX_CONNECTIONS = int(os.getenv("REDIS_MAX_CONNECTIONS", "20"))

# 연결 풀 싱글톤
_redis_pool: Optional[redis.ConnectionPool] = None
_redis_client: Optional[redis.Redis] = None


def _get_pool() -> Optional[redis.ConnectionPool]:
    """Redis 연결 풀 반환 (지연 초기화)"""
    global _redis_pool

    if _redis_pool is None:
        try:
            _redis_pool = redis.ConnectionPool(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                password=REDIS_PASSWORD,
                decode_responses=True,
                max_connections=REDIS_MAX_CONNECTIONS,
                socket_connect_timeout=5,
                socket_timeout=5,
                # 연결 상태 확인 (30초마다 PING)
                health_check_interval=30,
            )
            logger.info(
                f"[Redis] 연결 풀 생성: host={REDIS_HOST}, "
                f"max_connections={REDIS_MAX_CONNECTIONS}"
            )
        except Exception as e:
            logger.warning(f"[Redis] 연결 풀 생성 실패: {e}")
            _redis_pool = None

    return _redis_pool


def get_redis_client() -> Optional[redis.Redis]:
    """
    Redis 클라이언트를 반환합니다 (연결 풀 사용).

    Returns:
        redis.Redis 또는 None (Redis 불가 시)
    """
    global _redis_client

    if _redis_client is None:
        pool = _get_pool()
        if pool is None:
            logger.debug("[Redis] 연결 풀 없음 (파일 캐시 사용)")
            return None

        try:
            _redis_client = redis.Redis(connection_pool=pool)
            # 연결 테스트
            _redis_client.ping()
            logger.debug("[Redis] 클라이언트 연결됨 (풀 사용)")
        except Exception as e:
            logger.debug(f"[Redis] 연결 실패: {e} (파일 캐시 사용)")
            _redis_client = None

    return _redis_client


def is_redis_available() -> bool:
    """
    Redis 사용 가능 여부를 확인합니다.
    """
    client = get_redis_client()
    if client is None:
        return False

    try:
        client.ping()
        return True
    except:
        return False


def get_pool_stats() -> dict:
    """
    Redis 연결 풀 통계 반환 (모니터링용)

    Returns:
        {
            "max_connections": 최대 연결 수,
            "status": 연결 상태
        }
    """
    pool = _get_pool()
    if pool is None:
        return {"status": "unavailable"}

    try:
        # redis-py의 ConnectionPool 내부 구조 확인
        stats = {
            "status": "connected",
            "max_connections": pool.max_connections,
        }

        # _created_connections는 int (생성된 연결 수)
        if hasattr(pool, '_created_connections'):
            stats["created_connections"] = pool._created_connections

        return stats
    except Exception as e:
        return {"status": "error", "error": str(e)}
