from __future__ import annotations

import asyncio
import json
from typing import List

from openai import OpenAI
from app.config import settings
from app.services.logging import get_logger

log = get_logger("app.ingest.tagger")


def _client() -> OpenAI:
    # OPENAI_BASE_URL이 있으면 그걸 쓰고(우리가 config에서 /v1 보장),
    # 없으면 기본 api.openai.com/v1 을 사용
    if settings.openai_base_url:
        return OpenAI(
            api_key=settings.openai_api_key, base_url=settings.openai_base_url
        )
    return OpenAI(api_key=settings.openai_api_key)


async def _chat(messages, *, temperature: float = 0.2, model: str | None = None):
    client = _client()

    def _call():
        return client.chat.completions.create(
            model=(model or settings.openai_model),
            messages=messages,
            temperature=temperature,
        )

    # OpenAI SDK는 sync이므로, 비동기에서 막지 않도록 스레드로 돌림
    return await asyncio.to_thread(_call)


async def tag_query(text: str, *, max_tags: int = 6) -> List[str]:
    """
    입력 텍스트(질문/제목 등)에서 요약 태그를 생성.
    - JSON 배열 형태(["hr-policy","leave-policy"])로 받되,
      실패 시 쉼표 분리 폴백.
    """
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
        return norm[:max_tags]
    except Exception as e:
        log.debug("tag_query failed: %s", e)
        return []
