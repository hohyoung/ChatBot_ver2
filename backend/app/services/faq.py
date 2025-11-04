# backend/app/services/faq.py
"""
FAQ 자동 축적 시스템

질문 로그를 수집하고 DBSCAN 클러스터링을 통해
자주 묻는 질문(FAQ)을 자동으로 생성합니다.
"""
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional
from collections import Counter

import numpy as np
from sklearn.cluster import DBSCAN

from app.services.embedding import embed_texts
from app.services.redis_client import get_redis_client, is_redis_available
from app.db.database import SessionLocal
from app.db.models import QueryLog
from app.config import settings

logger = logging.getLogger(__name__)

# Redis 캐시 키
FAQ_CACHE_KEY = "faq:list"
FAQ_CACHE_TTL = 7 * 24 * 60 * 60  # 7일 (초)

# FAQ 캐시 파일 경로 (백업용)
FAQ_CACHE_PATH = Path("backend/data/faq_cache.json")


class FAQEntry:
    """FAQ 엔트리"""
    def __init__(self, question: str, count: int, cluster_size: int):
        self.question = question
        self.count = count  # 클러스터 내 질문 수
        self.cluster_size = cluster_size


async def log_question(
    question: str,
    answer_id: Optional[str] = None,
    user_id: Optional[int] = None
):
    """
    질문을 DB에 저장합니다.

    Args:
        question: 사용자 질문
        answer_id: 답변 ID (선택)
        user_id: 사용자 ID (선택)
    """
    db = SessionLocal()
    try:
        query_log = QueryLog(
            question=question,
            answer_id=answer_id,
            user_id=user_id
        )
        db.add(query_log)
        db.commit()

        logger.info(f"질문 로그 저장 완료: {question[:50]}...")

    except Exception as e:
        logger.error(f"질문 로그 저장 실패: {e}")
        db.rollback()
    finally:
        db.close()


async def load_recent_questions(days: int = 7) -> tuple[List[str], np.ndarray]:
    """
    최근 N일 동안의 질문을 DB에서 로드하고 임베딩을 생성합니다.

    Args:
        days: 로드할 일수

    Returns:
        (질문 리스트, 임베딩 배열)
    """
    db = SessionLocal()
    try:
        cutoff_time = datetime.utcnow() - timedelta(days=days)

        # DB에서 최근 질문 조회
        query_logs = (
            db.query(QueryLog)
            .filter(QueryLog.created_at >= cutoff_time)
            .order_by(QueryLog.created_at.desc())
            .all()
        )

        if not query_logs:
            logger.info(f"최근 {days}일 질문이 없습니다.")
            return [], np.array([])

        # 질문 텍스트 추출
        questions = [log.question for log in query_logs]

        # 임베딩 생성 (배치 처리)
        logger.info(f"최근 {days}일 질문 {len(questions)}개의 임베딩 생성 중...")
        embeddings = embed_texts(questions)

        logger.info(f"최근 {days}일 질문 로드 완료: {len(questions)}개")

        return questions, np.array(embeddings) if embeddings else np.array([])

    except Exception as e:
        logger.error(f"질문 로드 실패: {e}")
        return [], np.array([])
    finally:
        db.close()


async def cluster_questions(
    questions: List[str],
    embeddings: np.ndarray,
    eps: float = 0.3,
    min_samples: int = 3
) -> List[FAQEntry]:
    """
    DBSCAN 클러스터링으로 FAQ를 생성합니다.

    Args:
        questions: 질문 리스트
        embeddings: 임베딩 배열
        eps: DBSCAN epsilon (유사도 임계값, 기본: 0.3)
        min_samples: 클러스터 최소 샘플 수 (기본: 3)

    Returns:
        FAQ 엔트리 리스트
    """
    if len(questions) < min_samples:
        logger.warning(f"질문 수가 부족합니다: {len(questions)} < {min_samples}")
        return []

    try:
        # DBSCAN 클러스터링
        clustering = DBSCAN(eps=eps, min_samples=min_samples, metric='cosine')
        labels = clustering.fit_predict(embeddings)

        # 클러스터별 FAQ 생성
        faq_list = []

        for label in set(labels):
            if label == -1:  # 노이즈 제외
                continue

            # 클러스터에 속한 질문들
            cluster_questions = [q for i, q in enumerate(questions) if labels[i] == label]
            cluster_size = len(cluster_questions)

            # 가장 많이 나온 질문 선정 (또는 가장 짧은 질문)
            question_counter = Counter(cluster_questions)
            most_common_question = question_counter.most_common(1)[0][0]

            faq_list.append(FAQEntry(
                question=most_common_question,
                count=question_counter[most_common_question],
                cluster_size=cluster_size
            ))

        # 클러스터 크기 기준 정렬
        faq_list.sort(key=lambda x: x.cluster_size, reverse=True)

        logger.info(f"클러스터링 완료: {len(faq_list)}개 FAQ 생성")

        return faq_list

    except Exception as e:
        logger.error(f"클러스터링 실패: {e}")
        return []


async def generate_faq(
    min_questions: int = 20,
    top_n: int = 10,
    days: int = 7
) -> List[dict]:
    """
    FAQ를 생성하고 캐시합니다.

    Args:
        min_questions: FAQ 생성에 필요한 최소 질문 수 (기본: 20)
        top_n: 반환할 최대 FAQ 수 (기본: 10)
        days: 분석할 기간 (일) (기본: 7일)

    Returns:
        FAQ 리스트 [{"question": str, "count": int}, ...]
    """
    try:
        # 최근 질문 로드
        questions, embeddings = await load_recent_questions(days=days)

        if len(questions) < min_questions:
            logger.info(
                f"FAQ 생성을 위한 질문 수 부족: {len(questions)} < {min_questions}"
            )
            return []

        # 클러스터링
        faq_entries = await cluster_questions(questions, embeddings)

        # Top-N FAQ 선택
        top_faq = faq_entries[:top_n]

        # 결과 포맷
        result = [
            {
                "question": entry.question,
                "count": entry.cluster_size
            }
            for entry in top_faq
        ]

        # 캐시 저장
        cache_data = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "faq": result
        }

        FAQ_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(FAQ_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)

        logger.info(f"FAQ 생성 완료: {len(result)}개")

        return result

    except Exception as e:
        logger.error(f"FAQ 생성 실패: {e}")
        return []


async def get_cached_faq(max_age_days: int = 7) -> Optional[List[dict]]:
    """
    캐시된 FAQ를 반환합니다.

    Args:
        max_age_days: 캐시 최대 유효 기간 (일)

    Returns:
        FAQ 리스트 또는 None
    """
    if not FAQ_CACHE_PATH.exists():
        return None

    try:
        with open(FAQ_CACHE_PATH, "r", encoding="utf-8") as f:
            cache_data = json.load(f)

        # 캐시 유효성 확인
        generated_at = datetime.fromisoformat(cache_data["generated_at"].rstrip("Z"))
        age = datetime.utcnow() - generated_at

        if age.days > max_age_days:
            logger.info(f"캐시가 만료되었습니다: {age.days}일 경과")
            return None

        logger.info(f"캐시된 FAQ 반환: {len(cache_data['faq'])}개")
        return cache_data["faq"]

    except Exception as e:
        logger.error(f"캐시 로드 실패: {e}")
        return None


async def get_faq(force_refresh: bool = False) -> List[dict]:
    """
    FAQ를 반환합니다. 캐시가 있으면 캐시를 사용하고, 없으면 생성합니다.

    우선순위:
    1. Redis 캐시 (TTL 7일)
    2. 파일 캐시 (백업)
    3. 새로 생성

    Args:
        force_refresh: 강제 새로고침 여부

    Returns:
        FAQ 리스트
    """
    # 강제 새로고침이 아니면 캐시 사용
    if not force_refresh:
        # 1) Redis 캐시 확인
        if is_redis_available():
            try:
                redis_client = get_redis_client()
                cached_json = redis_client.get(FAQ_CACHE_KEY)

                if cached_json:
                    logger.info("Redis 캐시에서 FAQ 로드")
                    return json.loads(cached_json)
            except Exception as e:
                logger.warning(f"Redis 캐시 읽기 실패: {e}")

        # 2) 파일 캐시 확인
        cached = await get_cached_faq()
        if cached is not None:
            return cached

    # 3) 캐시가 없거나 강제 새로고침이면 새로 생성
    faq_list = await generate_faq()

    # Redis에 캐시 저장
    if faq_list and is_redis_available():
        try:
            redis_client = get_redis_client()
            redis_client.setex(
                FAQ_CACHE_KEY,
                FAQ_CACHE_TTL,
                json.dumps(faq_list, ensure_ascii=False)
            )
            logger.info(f"Redis에 FAQ 캐시 저장 (TTL={FAQ_CACHE_TTL}초)")
        except Exception as e:
            logger.warning(f"Redis 캐시 저장 실패: {e}")

    return faq_list
