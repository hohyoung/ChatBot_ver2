# backend/app/rag/query_decomposer.py
"""
Query Decomposer - GAR Phase 1

복합 질문을 여러 서브쿼리로 분해합니다.
- 각 서브쿼리는 하나의 의도만 포함
- 문서 컨텍스트를 활용하여 검색 최적화
- 최대 5개까지 분해 (정확도 우선)
"""

from __future__ import annotations

import asyncio
import json
from typing import List
from pydantic import BaseModel, Field

from app.services.openai_client import get_client
from app.config import settings
from app.services.logging import get_logger
from app.rag.intent_classifier import IntentResult
from app.rag.doc_discovery import DocContext, get_doc_context_summary

log = get_logger("app.rag.query_decomposer")


class SubQuery(BaseModel):
    """서브쿼리"""

    text: str = Field(..., description="서브쿼리 텍스트")
    focus: str = Field(..., description="서브쿼리의 핵심 초점")
    priority: int = Field(
        default=1, ge=1, le=3, description="우선순위 (1=최우선, 3=보조)"
    )


async def decompose_query(
    question: str, doc_context: DocContext, intent: IntentResult
) -> List[SubQuery]:
    """
    질문을 여러 서브쿼리로 분해합니다.

    Args:
        question: 원래 질문
        doc_context: 문서 컨텍스트
        intent: 의도 분류 결과

    Returns:
        List[SubQuery]: 서브쿼리 목록 (최대 5개)

    Examples:
        >>> subqueries = await decompose_query(
        ...     "연차는 몇 일이고 어떻게 신청하나요?",
        ...     doc_context,
        ...     intent
        ... )
        >>> len(subqueries)
        2
        >>> subqueries[0].text
        "연차 일수 규정"
    """
    log.info("쿼리 분해 시작: question=%r, intent=%s", question, intent.type)

    # doc_request는 분해 불필요
    if intent.type == "doc_request":
        log.info("doc_request는 분해 불필요, 원문 그대로 반환")
        return [
            SubQuery(
                text=question,
                focus="문서 검색",
                priority=1,
            )
        ]

    # 단순 질문 (50자 미만, 의문사 1개)은 분해 불필요
    if len(question) < 50 and question.count("?") <= 1:
        has_multiple_intents = any(
            keyword in question
            for keyword in ["그리고", "하고", ",", "또", "및", "과"]
        )
        if not has_multiple_intents:
            log.info("단순 질문, 분해 불필요")
            return [
                SubQuery(
                    text=question,
                    focus=_extract_focus(question),
                    priority=1,
                )
            ]

    # 문서 컨텍스트 요약
    doc_summary = await get_doc_context_summary(doc_context)

    # 시스템 프롬프트
    system_prompt = f"""{doc_summary}

당신은 사용자 질문을 검색에 최적화된 서브쿼리로 분해하는 전문가입니다.

**서브쿼리 생성 원칙:**
1. 각 서브쿼리는 **하나의 의도**만 포함
2. 검색하기 쉬운 **구체적인 키워드** 포함
3. 현재 문서 컨텍스트에 있는 유형/태그 활용
4. 최대 5개까지만 생성 (과도한 분해 금지)
5. 원문의 핵심 의도를 놓치지 않도록 주의

**우선순위 부여:**
- priority=1: 필수 정보 (질문의 핵심)
- priority=2: 중요 정보 (보조 설명)
- priority=3: 선택 정보 (참고 사항)

**출력 형식 (JSON 배열만 출력):**
[
  {{
    "text": "서브쿼리 텍스트",
    "focus": "핵심 초점 (2-3 단어)",
    "priority": 1
  }},
  ...
]

**예시:**

질문: "연차는 몇 일이고 어떻게 신청하나요?"
출력:
[
  {{"text": "연차 일수 규정", "focus": "일수", "priority": 1}},
  {{"text": "연차 신청 절차", "focus": "신청", "priority": 1}}
]

질문: "병가 신청하려는데 필요한 서류랑 기한 알려줘"
출력:
[
  {{"text": "병가 신청 필요 서류", "focus": "서류", "priority": 1}},
  {{"text": "병가 신청 기한", "focus": "기한", "priority": 1}}
]

질문: "재택근무 규정은?"
출력:
[
  {{"text": "재택근무 규정", "focus": "재택근무", "priority": 1}}
]
"""

    user_prompt = f"""사용자 질문: "{question}"

이 질문을 검색에 최적화된 서브쿼리로 분해하세요.
JSON 배열만 출력하세요."""

    try:
        # LLM 호출
        client = get_client()

        def _call():
            return client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,  # 약간의 창의성 허용
            )

        response = await asyncio.to_thread(_call)
        content = response.choices[0].message.content.strip()

        log.debug("쿼리 분해 LLM 응답: %s", content)

        # JSON 파싱
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()

        subqueries_raw = json.loads(content)

        # Pydantic 검증
        if not isinstance(subqueries_raw, list):
            raise ValueError("응답이 JSON 배열이 아님")

        subqueries = [SubQuery(**sq) for sq in subqueries_raw]

        # 최대 5개 제한
        if len(subqueries) > 5:
            log.warning("서브쿼리 5개 초과 (%d개), 상위 5개만 사용", len(subqueries))
            subqueries = subqueries[:5]

        # 빈 결과 → 원문 그대로
        if not subqueries:
            log.warning("서브쿼리 생성 실패, 원문 그대로 반환")
            subqueries = [
                SubQuery(text=question, focus=_extract_focus(question), priority=1)
            ]

        log.info("쿼리 분해 완료: %d개 서브쿼리 생성", len(subqueries))
        for i, sq in enumerate(subqueries, start=1):
            log.debug(
                "  %d. text=%r, focus=%r, priority=%d", i, sq.text, sq.focus, sq.priority
            )

        return subqueries

    except json.JSONDecodeError as e:
        log.error("쿼리 분해 JSON 파싱 실패: %s, content=%r", e, content)
        return [SubQuery(text=question, focus=_extract_focus(question), priority=1)]

    except Exception as e:
        log.exception("쿼리 분해 실패: %s", e)
        return [SubQuery(text=question, focus=_extract_focus(question), priority=1)]


def _extract_focus(question: str) -> str:
    """
    질문에서 핵심 초점을 추출합니다 (간단한 휴리스틱).

    Args:
        question: 질문

    Returns:
        str: 핵심 초점 (2-3 단어)

    Examples:
        >>> _extract_focus("연차는 몇 일인가요?")
        "연차 일수"
        >>> _extract_focus("병가 신청 방법은?")
        "병가 신청"
    """
    # 의문사 제거
    for word in ["몇", "어떻게", "언제", "무엇", "왜", "누가", "어디서", "어느"]:
        question = question.replace(word, "")

    # 조사 제거
    for josa in ["은", "는", "이", "가", "을", "를", "의", "에", "에서", "으로", "로"]:
        question = question.replace(josa, " ")

    # 특수문자 제거
    for char in ["?", "!", ".", ","]:
        question = question.replace(char, "")

    # 공백 정리 및 앞 3단어 추출
    words = [w.strip() for w in question.split() if w.strip()]
    focus_words = words[:3] if len(words) >= 3 else words

    return " ".join(focus_words) if focus_words else "정보"
