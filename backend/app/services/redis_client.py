# backend/app/services/redis_client.py
"""
Redis 클라이언트 설정

FAQ 캐싱, OTP 저장 등에 사용됩니다.
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

# Redis 클라이언트 싱글톤
_redis_client: Optional[redis.Redis] = None


def get_redis_client() -> redis.Redis:
    """
    Redis 클라이언트를 반환합니다.
    """
    global _redis_client

    if _redis_client is None:
        try:
            _redis_client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                password=REDIS_PASSWORD,
                decode_responses=True,  # 문자열로 자동 디코딩
                socket_connect_timeout=5,
                socket_timeout=5
            )
            # 연결 테스트
            _redis_client.ping()
            logger.info(f"Redis 연결 성공: {REDIS_HOST}:{REDIS_PORT}")
        except Exception as e:
            logger.warning(f"Redis 연결 실패 (캐싱 비활성화): {e}")
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
