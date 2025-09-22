from __future__ import annotations

from typing import List, Tuple, Any, Dict, Union

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


async def generate_answer(
    question: str, candidates: List[Union[ScoredChunk, Chunk]]
) -> Tuple[str, List[Chunk]]:
    """
    질문 + 후보 청크들로 답변 생성.
    반환: (answer_text, used_chunks)
    """
    used_chunks: List[Chunk] = _select_chunks(candidates, max_chars=6000)
    context = _build_context(used_chunks)

    system_msg = (
        "너는 회사 내부 규정 안내용 비서다. "
        "주어진 컨텍스트(문서 청크) 범위 안에서만 한국어로 정확히 답해라. "
        "근거가 불충분하면 '제공된 자료 내에서 확실하지 않습니다'라고 말하고, "
        "모호한 부분이 존재한다면 추가로 확인할 항목을 제안해라. "
        "필요시 목록이나 단계 형식으로 간결하게 정리해라."
    )

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
