# backend/app/rag/intent_classifier.py
"""
Intent Classifier - GAR Phase 1

사용자 질문의 의도를 분류합니다.
- doc_request: 문서 검색 요청
- info_request: 정보 질의
- multi_step: 복합 질의
"""

from __future__ import annotations

import asyncio
import json
from typing import Literal
from pydantic import BaseModel, Field

from app.services.openai_client import get_client
from app.config import settings
from app.services.logging import get_logger

log = get_logger("app.rag.intent_classifier")

IntentType = Literal["doc_request", "info_request", "multi_step"]


class IntentResult(BaseModel):
    """Intent 분류 결과"""

    type: IntentType = Field(..., description="의도 타입")
    confidence: float = Field(..., ge=0.0, le=1.0, description="분류 확신도 (0~1)")
    reasoning: str = Field(..., description="분류 근거")


async def classify_intent(question: str) -> IntentResult:
    """
    질문의 의도를 분류합니다.

    Args:
        question: 사용자 질문

    Returns:
        IntentResult: 의도 분류 결과
            - doc_request: 문서 검색 요청
            - info_request: 정보 질의
            - multi_step: 복합 질의

    Examples:
        >>> await classify_intent("연차 관련 문서 찾아줘")
        IntentResult(type="doc_request", confidence=0.95, ...)

        >>> await classify_intent("연차는 몇 일인가요?")
        IntentResult(type="info_request", confidence=0.92, ...)

        >>> await classify_intent("연차 문서 찾고 내용 요약해줘")
        IntentResult(type="multi_step", confidence=0.88, ...)
    """
    log.info("Intent 분류 시작: question=%r", question)

    # 시스템 프롬프트: Few-shot 예시 기반
    system_prompt = """당신은 사용자 질문의 의도를 분류하는 전문가입니다.

사용자 질문을 다음 3가지 의도 중 하나로 분류하세요:

1. **doc_request** (문서 검색 요청)
   - 특징: 문서 자체를 찾거나 열람하려는 요청
   - 키워드: "문서 찾아", "어디서 볼 수 있나", "관련 문서", "문서 목록"
   - 예시:
     - "연차 관련 문서 찾아줘"
     - "인사규정 문서 어디서 볼 수 있어?"
     - "복무규정 보고 싶어"

2. **info_request** (정보 질의)
   - 특징: 특정 정보나 답변을 얻으려는 질문
   - 키워드: "몇", "어떻게", "언제", "무엇", "왜"
   - 예시:
     - "연차는 몇 일인가요?"
     - "병가는 어떻게 신청하나요?"
     - "재택근무 규정은 어떻게 되나요?"

3. **multi_step** (복합 질의)
   - 특징: 문서 검색 + 정보 질의가 결합된 요청
   - 키워드: "찾고 ~해줘", "보고 ~알려줘"
   - 예시:
     - "연차 문서 찾고 내용 요약해줘"
     - "복무규정 보고 핵심만 알려줘"
     - "인사규정 문서에서 승진 관련 내용 찾아줘"

**출력 형식 (JSON만 출력):**
{
  "type": "doc_request" | "info_request" | "multi_step",
  "confidence": 0.0 ~ 1.0,
  "reasoning": "분류 근거 설명"
}

**분류 기준:**
- confidence ≥ 0.7: 확신 있음
- confidence < 0.7: 재시도 또는 안전 모드 (info_request)
- 불명확한 경우 info_request로 분류
"""

    user_prompt = f"""사용자 질문: "{question}"

이 질문의 의도를 분류하세요."""

    try:
        # LLM 호출 (async)
        client = get_client()

        def _call():
            return client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,  # 결정론적 출력
            )

        response = await asyncio.to_thread(_call)
        content = response.choices[0].message.content.strip()

        log.debug("Intent 분류 LLM 응답: %s", content)

        # JSON 파싱
        if content.startswith("```"):
            # 마크다운 코드 블록 제거
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()

        result_dict = json.loads(content)

        # Pydantic 검증
        result = IntentResult(**result_dict)

        # confidence < 0.7 → 재시도 또는 안전 모드
        if result.confidence < 0.7:
            log.warning(
                "Intent 분류 확신도 낮음 (%.2f < 0.7), 안전 모드로 전환 (info_request)",
                result.confidence,
            )
            # 안전 모드: info_request로 처리
            result = IntentResult(
                type="info_request",
                confidence=0.5,
                reasoning=f"확신도 낮음 ({result.confidence:.2f}), 안전 모드: {result.reasoning}",
            )

        log.info(
            "Intent 분류 완료: type=%s, confidence=%.2f, reasoning=%r",
            result.type,
            result.confidence,
            result.reasoning,
        )

        return result

    except json.JSONDecodeError as e:
        log.error("Intent 분류 JSON 파싱 실패: %s, content=%r", e, content)
        # 폴백: info_request
        return IntentResult(
            type="info_request",
            confidence=0.3,
            reasoning=f"JSON 파싱 실패, 폴백 모드: {str(e)}",
        )

    except Exception as e:
        log.exception("Intent 분류 실패: %s", e)
        # 폴백: info_request
        return IntentResult(
            type="info_request",
            confidence=0.3,
            reasoning=f"분류 실패, 폴백 모드: {str(e)}",
        )
