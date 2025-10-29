from __future__ import annotations

from typing import List, Tuple, Any, Dict, Union, AsyncIterator

from app.services.openai_client import get_client
from app.config import settings
from app.services.logging import get_logger
from app.models.schemas import Chunk, ScoredChunk  # ← 경로 주의!

log = get_logger("app.rag.generator")


def _score_of(sc: Union[ScoredChunk, Chunk]) -> float:
    """정렬 점수 통일: ScoredChunk면 score/similarity/(1-distance) 우선순위 사용, Chunk면 0."""
    if isinstance(sc, ScoredChunk):
        # pydantic v2: hasattr로 접근
        if hasattr(sc, "score") and isinstance(sc.score, (int, float)):
            return float(sc.score)
        if hasattr(sc, "similarity") and isinstance(sc.similarity, (int, float)):
            return float(sc.similarity)
        if hasattr(sc, "distance") and isinstance(sc.distance, (int, float)):
            d = max(0.0, min(1.0, float(sc.distance)))
            return 1.0 - d
    return 0.0


def _as_chunk(x: Union[ScoredChunk, Chunk]) -> Chunk:
    """ScoredChunk → Chunk, 이미 Chunk면 그대로."""
    if isinstance(x, ScoredChunk):
        return x.chunk
    return x


def _select_chunks(
    candidates: List[Union[ScoredChunk, Chunk]], max_chars: int = 6000
) -> List[Chunk]:
    """
    컨텍스트에 넣을 청크 선별.
    - 점수 높은 순으로 정렬
    - max_chars를 넘지 않는 선에서 누적
    반환은 항상 List[Chunk]
    """
    # 정렬 (점수 높은 순)
    ordered = sorted(candidates, key=_score_of, reverse=True)

    picked: List[Chunk] = []
    total = 0
    for c in ordered:
        ch = _as_chunk(c)
        text = ch.content or ""
        l = len(text)
        if l == 0:
            continue
        if total + l > max_chars and picked:
            break
        picked.append(ch)
        total += l

    return picked


def _build_context(chunks: List[Chunk]) -> str:
    """프롬프트에 넣을 컨텍스트 문자열 구성."""
    lines: List[str] = []
    for i, ch in enumerate(chunks, start=1):
        title = ch.doc_title or ch.doc_id or "Untitled"
        lines.append(
            f"[{i}] {title} (doc_type={ch.doc_type}, visibility={ch.visibility}, tags={','.join(ch.tags or [])})"
        )
        lines.append(ch.content.strip())
        lines.append("")  # 빈 줄
    return "\n".join(lines).strip()


def _get_system_prompt() -> str:
    """
    챗봇 페르소나 시스템 프롬프트.
    페르소나: 사내 규정 안내 전문가 (Knowledge Navigator)
    """
    return (
        "당신은 **사내 규정 안내 전문가(Knowledge Navigator)**입니다.\n"
        "사내 문서와 규정을 기반으로 직원들에게 정확하고 유용한 정보를 제공하는 것이 목표입니다.\n\n"

        "## 응답 원칙\n"
        "1. **근거 기반**: 제공된 문서의 내용만을 근거로 답변하세요. 추측이나 외부 지식을 사용하지 마세요.\n"
        "2. **조항 명시**: 관련 규정이나 조항이 있다면 반드시 명시하세요 (예: '제10조', '제2항').\n"
        "3. **친절하고 명확하게**: 전문 용어를 쉽게 풀어서 설명하고, 구조적으로 정리해서 답변하세요.\n"
        "4. **마크다운 활용**: 마크다운 문법을 사용하여 가독성 높은 답변을 작성하세요.\n"
        "5. **불확실성 인정**: 근거가 불충분하면 솔직히 인정하고, 추가로 확인할 방법을 안내하세요.\n\n"

        "## 마크다운 출력 가이드\n"
        "- **제목**: 답변의 핵심 결론을 첫 문장으로 제시 (제목 마크다운 불필요)\n"
        "- **목록**: 여러 항목은 `-` 또는 `1.`로 구조화\n"
        "- **강조**: 핵심 용어나 수치만 **굵게** 표시 (과도한 강조 금지)\n"
        "- **조항**: 관련 조항은 `제10조`, `제2항`처럼 명시\n"
        "- **표**: 비교가 필요하면 마크다운 표 사용\n\n"

        "## 예시\n"
        "질문: '연차는 몇 일인가요?'\n"
        "답변:\n"
        "입사 2년차의 경우 연차는 **15일**입니다.\n\n"
        "연차 일수는 근속 연수에 따라 다음과 같이 부여됩니다:\n"
        "- 1년 미만: **11일**\n"
        "- 1~2년: **15일**\n"
        "- 3~4년: **16일**\n"
        "- 5년 이상: 2년마다 1일 가산 (최대 25일)\n\n"
        "관련 규정: **제10조 (연차휴가)**"
    )


async def generate_answer(
    question: str, candidates: List[Union[ScoredChunk, Chunk]]
) -> Tuple[str, List[Chunk]]:
    """
    질문 + 후보 청크들로 답변 생성.
    반환: (answer_text, used_chunks)
    """
    used_chunks: List[Chunk] = _select_chunks(candidates, max_chars=6000)
    context = _build_context(used_chunks)

    system_msg = _get_system_prompt()

    user_msg = (
        f"질문:\n{question}\n\n"
        f"다음은 검색된 관련 문서 청크들이다. "
        f"이 정보만 사용해서 답변해라.\n\n"
        f"{context}"
    )

    client = get_client()
    # Chat Completions (v1 엔드포인트 사용)
    resp = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.2,
    )
    answer = resp.choices[0].message.content.strip() if resp.choices else ""

    return answer, used_chunks


async def generate_answer_stream(
    question: str, candidates: List[Union[ScoredChunk, Chunk]]
) -> AsyncIterator[Tuple[str, List[Chunk] | None]]:
    """
    질문 + 후보 청크들로 답변을 스트리밍 생성.

    Yields:
        (token, None) - 토큰 단위 스트리밍
        ("", used_chunks) - 최종 청크 리스트 (스트림 끝)
    """
    used_chunks: List[Chunk] = _select_chunks(candidates, max_chars=6000)
    context = _build_context(used_chunks)

    system_msg = _get_system_prompt()
    user_msg = (
        f"질문:\n{question}\n\n"
        f"다음은 검색된 관련 문서 청크들이다. "
        f"이 정보만 사용해서 답변해라.\n\n"
        f"{context}"
    )

    client = get_client()

    # 스트리밍 모드로 호출
    stream = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.2,
        stream=True,  # 스트리밍 활성화
    )

    # 토큰 단위로 yield
    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            token = chunk.choices[0].delta.content
            yield (token, None)

    # 스트림 종료 시 청크 리스트 반환
    yield ("", used_chunks)
