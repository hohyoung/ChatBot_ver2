from __future__ import annotations

import json
import hashlib
from typing import List, Optional

from app.services.openai_client import call_chat_completion_async
from app.config import settings
from app.services.logging import get_logger
from app.services.redis_client import get_redis_client

log = get_logger("app.ingest.tagger")

# Redis 캐시 TTL (P1-1 성능 최적화)
TAG_CACHE_TTL = 86400 * 7  # 7일


async def _chat(messages, *, temperature: float = 0.2, model: str | None = None):
    """비동기 Chat Completion 호출 (동시성 제어 포함)"""
    return await call_chat_completion_async(
        model=(model or settings.openai_model),
        messages=messages,
        temperature=temperature,
    )


def _get_cache_key(text: str, max_tags: int) -> str:
    """태그 캐시 키 생성"""
    text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
    return f"tag:{text_hash}:{max_tags}"


async def tag_query(text: str, *, max_tags: int = 6, use_cache: bool = True) -> List[str]:
    """
    입력 텍스트(질문/제목 등)에서 요약 태그를 생성 (Redis 캐싱 지원)

    Args:
        text: 태그를 생성할 텍스트
        max_tags: 최대 태그 개수
        use_cache: 캐시 사용 여부 (기본: True)

    Returns:
        태그 리스트 (예: ["hr-policy", "leave-policy"])

    Features (P1-1):
    - Redis 캐싱: 동일 텍스트 재요청 시 LLM 호출 없이 즉시 반환
    - TTL 7일: 자동 만료
    """
    # 캐시 확인
    cache_key = _get_cache_key(text, max_tags)
    redis_client = get_redis_client() if use_cache else None

    if redis_client:
        try:
            cached = redis_client.get(cache_key)
            if cached:
                tags = json.loads(cached)
                log.debug(f"[TAG] Cache hit for key {cache_key[:16]}...")
                return tags
        except Exception as e:
            log.warning(f"[TAG] Cache read failed: {e}")

    # 캐시 미스 - LLM 호출
    log.debug(f"[TAG] Cache miss for key {cache_key[:16]}... - calling LLM")

    prompt_user = f"""다음 텍스트의 주제를 나타내는 간결한 태그 {max_tags}개 이내로 만들어줘.
- 한국어/영어 혼용 가능, 소문자/하이픈 추천
- JSON 배열로만 출력(설명 금지)
텍스트:
{text}"""

    messages = [
        {
            "role": "system",
            "content": "You are a concise taxonomy/tag generator. Respond ONLY with a JSON array of strings.",
        },
        {"role": "user", "content": prompt_user},
    ]

    try:
        resp = await _chat(messages, temperature=0.0)
        content = (resp.choices[0].message.content or "").strip()

        # 마크다운 코드 블록 제거 (```json ... ``` 또는 ``` ... ```)
        if content.startswith("```"):
            lines = content.split("\n")
            # 첫 줄(```json)과 마지막 줄(```) 제거
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines).strip()

        tags = []
        try:
            tags = json.loads(content)
            if not isinstance(tags, list):
                raise ValueError("not a list")
        except Exception:
            # JSON 파싱 실패 시: 쉼표 구분 폴백
            raw = content.strip("[] \n\"'")
            tags = [t.strip().strip("\"'") for t in raw.split(",") if t.strip()]

        # 정규화: 소문자, 공백→하이픈, 중복 제거
        norm = []
        seen = set()
        for t in tags:
            if not isinstance(t, str):
                continue
            v = t.strip().lower().replace(" ", "-")
            if v and v not in seen:
                seen.add(v)
                norm.append(v)
        if not norm:
            return []

        result = norm[:max_tags]

        # 캐시 저장
        if redis_client:
            try:
                redis_client.setex(cache_key, TAG_CACHE_TTL, json.dumps(result))
                log.debug(f"[TAG] Cached tags for key {cache_key[:16]}...")
            except Exception as e:
                log.warning(f"[TAG] Cache write failed: {e}")

        return result

    except Exception as e:
        log.debug("tag_query failed: %s", e)
        return []
