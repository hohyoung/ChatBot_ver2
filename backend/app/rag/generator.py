from __future__ import annotations

import re
from typing import List, Tuple, Any, Dict, Union, AsyncIterator, Optional

from app.services.openai_client import (
    get_client,
    get_async_client,
    call_chat_completion_async,
    call_chat_completion_stream_async,
    _get_semaphore,
)
from app.config import settings
from app.services.logging import get_logger
from app.models.schemas import Chunk, ScoredChunk  # ← 경로 주의!

log = get_logger("app.rag.generator")


def _filter_actually_used_chunks(
    answer: str,
    chunks: List[Chunk],
    min_overlap_ratio: float = 0.15,
) -> List[Chunk]:
    """
    LLM 답변에서 실제로 사용된 청크만 필터링.

    전략:
    1. 청크의 핵심 키워드/문구가 답변에 등장하는지 확인
    2. 청크 내용과 답변의 n-gram 오버랩 비율 계산
    3. 특정 임계값 이상인 청크만 반환

    Args:
        answer: LLM이 생성한 답변
        chunks: LLM에 전달된 청크 목록
        min_overlap_ratio: 최소 오버랩 비율 (기본 0.15 = 15%)

    Returns:
        실제 답변에 사용된 것으로 판단되는 청크 목록
    """
    if not answer or not chunks:
        return chunks

    # 답변 정규화 (공백, 특수문자 정리)
    answer_normalized = re.sub(r'\s+', ' ', answer.lower().strip())

    used_chunks = []

    for chunk in chunks:
        content = chunk.content or ""
        if not content.strip():
            continue

        # 청크 내용 정규화
        content_normalized = re.sub(r'\s+', ' ', content.lower().strip())

        # 1) 핵심 문구 매칭 (3단어 이상 연속 일치)
        # 청크에서 의미있는 문구 추출 (숫자+단위, 조항명 등)
        phrases = _extract_key_phrases(content)
        phrase_match = any(
            phrase.lower() in answer_normalized
            for phrase in phrases
            if len(phrase) >= 4  # 최소 4자 이상
        )

        # 2) 단어 오버랩 계산
        chunk_words = set(re.findall(r'[가-힣a-zA-Z0-9]+', content_normalized))
        answer_words = set(re.findall(r'[가-힣a-zA-Z0-9]+', answer_normalized))

        if chunk_words:
            overlap = chunk_words & answer_words
            # 불용어 제외 (조사, 일반 용어)
            stopwords = {'는', '은', '이', '가', '을', '를', '의', '에', '로', '와', '과',
                         '및', '등', '것', '수', '때', '경우', '대해', '관련', '해당',
                         'the', 'a', 'an', 'is', 'are', 'of', 'to', 'in', 'for'}
            meaningful_overlap = overlap - stopwords
            meaningful_chunk_words = chunk_words - stopwords

            if meaningful_chunk_words:
                overlap_ratio = len(meaningful_overlap) / len(meaningful_chunk_words)
            else:
                overlap_ratio = 0.0
        else:
            overlap_ratio = 0.0

        # 3) 조항/규정 번호 매칭 (예: "제10조", "제3항")
        regulation_pattern = r'제\s*\d+\s*[조항호]'
        chunk_regulations = set(re.findall(regulation_pattern, content))
        answer_regulations = set(re.findall(regulation_pattern, answer))
        regulation_match = bool(chunk_regulations & answer_regulations)

        # 4) 숫자+단위 매칭 (예: "15일", "80%", "1년")
        number_pattern = r'\d+(?:\.\d+)?(?:일|개월|년|%|원|시간|분)'
        chunk_numbers = set(re.findall(number_pattern, content))
        answer_numbers = set(re.findall(number_pattern, answer))
        number_match = bool(chunk_numbers & answer_numbers)

        # 종합 판단
        is_used = (
            phrase_match or
            regulation_match or
            number_match or
            overlap_ratio >= min_overlap_ratio
        )

        if is_used:
            used_chunks.append(chunk)
            log.debug(
                f"[FILTER] 사용됨: {chunk.chunk_id} "
                f"(phrase={phrase_match}, reg={regulation_match}, "
                f"num={number_match}, overlap={overlap_ratio:.2f})"
            )
        else:
            log.debug(
                f"[FILTER] 미사용: {chunk.chunk_id} "
                f"(phrase={phrase_match}, reg={regulation_match}, "
                f"num={number_match}, overlap={overlap_ratio:.2f})"
            )

    # 최소 1개는 반환 (fallback)
    if not used_chunks and chunks:
        used_chunks = [chunks[0]]
        log.warning("[FILTER] 사용된 청크 없음, 첫 번째 청크를 fallback으로 사용")

    log.info(f"[FILTER] {len(chunks)}개 청크 → {len(used_chunks)}개 실제 사용")

    return used_chunks


def _extract_key_phrases(text: str, min_len: int = 4, max_phrases: int = 20) -> List[str]:
    """
    텍스트에서 핵심 문구 추출.
    - 조항명 (제N조, 제N항)
    - 숫자+단위 (15일, 80%)
    - 고유명사/전문용어 (연차휴가, 출장비 등)
    """
    phrases = []

    # 1) 조항명
    regulations = re.findall(r'제\s*\d+\s*[조항호][의\s]*\d*', text)
    phrases.extend(regulations)

    # 2) 숫자+단위 표현
    numbers = re.findall(r'\d+(?:\.\d+)?(?:일|개월|년|%|원|시간|분|명|개|회)', text)
    phrases.extend(numbers)

    # 3) 한글 복합어 (2어절 이상)
    # 예: "연차휴가", "출장비", "인사위원회"
    compound_words = re.findall(r'[가-힣]{2,}(?:휴가|규정|위원회|수당|비용|지원|신청|승인|기준)', text)
    phrases.extend(compound_words)

    # 4) 괄호 안 용어
    parenthetical = re.findall(r'\(([^)]{2,20})\)', text)
    phrases.extend(parenthetical)

    # 중복 제거 및 길이 필터
    unique_phrases = []
    seen = set()
    for p in phrases:
        p_clean = p.strip()
        if p_clean and len(p_clean) >= min_len and p_clean not in seen:
            seen.add(p_clean)
            unique_phrases.append(p_clean)
            if len(unique_phrases) >= max_phrases:
                break

    return unique_phrases


def _score_of(sc: Union[ScoredChunk, Chunk]) -> float:
    """정렬 점수 통일: ScoredChunk면 final_score/score/similarity/(1-distance) 우선순위 사용, Chunk면 0."""
    if isinstance(sc, ScoredChunk):
        # pydantic v2: hasattr로 접근
        # 1. final_score (reranker에서 설정하는 최종 점수)
        if hasattr(sc, "final_score") and isinstance(sc.final_score, (int, float)):
            return float(sc.final_score)
        # 2. score (deprecated, 하위 호환용)
        if hasattr(sc, "score") and isinstance(sc.score, (int, float)):
            return float(sc.score)
        # 3. similarity
        if hasattr(sc, "similarity") and isinstance(sc.similarity, (int, float)):
            return float(sc.similarity)
        # 4. distance → similarity로 변환
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
    candidates: List[Union[ScoredChunk, Chunk]],
    max_chars: int = 6000,
    min_score: float = 0.05,  # 최소 관련성 점수
    max_docs: int = 3,  # 최대 문서 수
    max_chunks_per_doc: int = 2,  # 문서당 최대 청크 수
) -> List[Chunk]:
    """
    컨텍스트에 넣을 청크 선별.
    - 점수가 min_score 미만인 청크는 제외
    - 문서 단위로 최대 max_docs개만 선택
    - 각 문서에서 최대 max_chunks_per_doc개 청크 선택 (표/본문 모두 포함)
    - 점수 높은 순으로 정렬 후 max_chars 제한
    반환은 항상 List[Chunk]
    """
    # [DEBUG] 입력된 모든 후보 청크 로깅
    log.info(f"[_select_chunks] ===== 후보 청크 목록 ({len(candidates)}개) =====")
    for i, c in enumerate(candidates):
        ch = _as_chunk(c)
        score = _score_of(c)
        content_preview = (ch.content or "")[:100].replace("\n", " ")
        log.info(f"[_select_chunks] 후보 {i+1}: chunk_id={ch.chunk_id}, doc_title={ch.doc_title}, score={score:.4f}")
        log.info(f"[_select_chunks]   내용 미리보기: {content_preview}...")

    # 1단계: 최소 점수 필터링
    filtered = []
    for c in candidates:
        score = _score_of(c)
        if score >= min_score:
            filtered.append((c, score))
        else:
            ch = _as_chunk(c)
            log.info(f"[_select_chunks] 점수 미달로 제외: chunk_id={ch.chunk_id}, score={score:.4f} < {min_score}")

    if not filtered:
        # 필터링 후 청크가 없으면, 가장 점수 높은 것 하나라도 포함
        if candidates:
            best = max(candidates, key=_score_of)
            filtered = [(best, _score_of(best))]
            log.warning(f"[_select_chunks] 모든 청크가 점수 미달, 최고 점수 청크 1개 사용")

    # 2단계: 점수 순 정렬
    filtered.sort(key=lambda x: x[1], reverse=True)

    # 3단계: 문서 단위 청크 제한 (각 문서에서 max_chunks_per_doc개까지 허용)
    log.info(f"[_select_chunks] ===== 문서 단위 청크 선택 시작 (max_chunks_per_doc={max_chunks_per_doc}) =====")
    doc_chunk_count: Dict[str, int] = {}  # doc_id → 선택된 청크 수
    deduplicated = []
    for c, score in filtered:
        ch = _as_chunk(c)
        doc_id = ch.doc_id
        current_count = doc_chunk_count.get(doc_id, 0)

        if current_count < max_chunks_per_doc:
            # 이 문서에서 아직 max_chunks_per_doc개 미만 선택됨
            doc_chunk_count[doc_id] = current_count + 1
            deduplicated.append((ch, score))
            content_preview = (ch.content or "")[:80].replace("\n", " ")
            log.info(f"[_select_chunks] 선택됨: chunk_id={ch.chunk_id}, score={score:.4f} (문서 내 {current_count + 1}번째)")
            log.info(f"[_select_chunks]   내용: {content_preview}...")

            # max_docs 문서 수 제한 확인
            if len(doc_chunk_count) >= max_docs and all(
                cnt >= max_chunks_per_doc for cnt in doc_chunk_count.values()
            ):
                log.info(f"[_select_chunks] max_docs={max_docs} 문서에서 각각 최대 청크 도달, 중단")
                break
        else:
            content_preview = (ch.content or "")[:80].replace("\n", " ")
            log.info(f"[_select_chunks] 제외됨 (문서당 {max_chunks_per_doc}개 초과): chunk_id={ch.chunk_id}, doc_id={doc_id}, score={score:.4f}")
            log.info(f"[_select_chunks]   내용: {content_preview}...")

    # 4단계: max_chars 제한 적용
    picked: List[Chunk] = []
    total = 0
    for ch, score in deduplicated:
        text = ch.content or ""
        l = len(text)
        if l == 0:
            continue
        if total + l > max_chars and picked:
            break
        picked.append(ch)
        total += l
        log.debug(f"[_select_chunks] 선택: {ch.doc_title} (score={score:.3f}, chars={l})")

    log.info(f"[_select_chunks] {len(candidates)}개 후보 → {len(picked)}개 선택 (min_score={min_score}, max_docs={max_docs})")

    return picked


def _build_context(chunks: List[Chunk]) -> Tuple[str, List[Dict[str, str]]]:
    """
    프롬프트에 넣을 컨텍스트 문자열 구성.

    Returns:
        (context_string, image_refs)
        - context_string: 컨텍스트 문자열
        - image_refs: [{"ref": "[이미지1]", "url": "/static/images/...", "type": "table/figure"}]
    """
    lines: List[str] = []
    image_refs: List[Dict[str, str]] = []
    img_counter = 1

    for i, ch in enumerate(chunks, start=1):
        title = ch.doc_title or ch.doc_id or "Untitled"
        header = f"[{i}] {title} (doc_type={ch.doc_type}, visibility={ch.visibility}, tags={','.join(ch.tags or [])})"

        # 이미지가 있는 청크인 경우 이미지 참조 추가
        if getattr(ch, 'has_image', False) and getattr(ch, 'image_url', None):
            img_type = getattr(ch, 'image_type', 'image')
            img_ref = f"[이미지{img_counter}]"
            image_refs.append({
                "ref": img_ref,
                "url": ch.image_url,
                "type": img_type,
                "doc_title": title,
                "page": getattr(ch, 'page_start', None),
            })
            header += f" {img_ref} 📊원본이미지있음"
            img_counter += 1

        lines.append(header)
        lines.append(ch.content.strip())
        lines.append("")  # 빈 줄

    return "\n".join(lines).strip(), image_refs


def _get_system_prompt(image_refs: List[Dict[str, str]] = None) -> str:
    """
    챗봇 페르소나 시스템 프롬프트.
    페르소나: 친절한 사내 규정 상담원

    Args:
        image_refs: 이미지 참조 리스트 [{"ref": "[이미지1]", "url": "...", "type": "table"}]
    """
    base_prompt = (
        "당신은 회사의 **친절한 규정 상담원**입니다.\n"
        "직원분들이 편하게 질문할 수 있도록 따뜻하고 친근한 말투로 안내해 드리는 것이 목표예요.\n\n"

        "## 말투 가이드\n"
        "- 존댓말을 사용하되, 딱딱하지 않고 부드럽게 말해주세요.\n"
        "- '~입니다', '~됩니다' 대신 '~예요', '~이에요', '~드려요' 같은 표현을 사용하세요.\n"
        "- 공감과 배려의 표현을 적절히 넣어주세요. (예: '궁금하셨죠?', '도움이 되셨으면 좋겠어요')\n"
        "- 너무 과하게 친근하거나 가볍지 않게, 전문성은 유지하면서 따뜻하게 답변하세요.\n\n"

        "## ⚠️ 가장 중요한 원칙: 환각 금지\n"
        "**반드시 제공된 문서 내용만 사용하세요. 문서에 없는 내용은 절대 만들어내지 마세요.**\n"
        "- 문서에 명시적으로 있는 정보만 답변하세요.\n"
        "- '일반적으로', '보통', '대개' 같은 추측성 표현으로 없는 정보를 만들지 마세요.\n"
        "- 문서에 해당 내용이 없으면 '제공된 문서에서 해당 정보를 찾을 수 없어요'라고 솔직히 말하세요.\n"
        "- 담당 부서나 담당자 연락처가 문서에 있다면 해당 부서에 문의하도록 안내하세요.\n\n"

        "## 응답 원칙\n"
        "1. **근거 필수**: 답변의 모든 내용은 제공된 문서에서 직접 인용 가능해야 해요.\n"
        "2. **조항 안내**: 관련 규정이나 조항이 있다면 자연스럽게 안내해 드려요. (예: '제10조에 따르면~')\n"
        "3. **쉬운 설명**: 전문 용어는 쉽게 풀어서 설명해 드려요.\n"
        "4. **구조화**: 내용이 많을 때는 읽기 쉽게 정리해서 알려드려요.\n"
        "5. **불확실성**: 정보가 부족하면 '문서에서 확인되지 않아요'라고 솔직히 말씀드리고, 담당 부서 문의를 안내해요.\n\n"

        "## 🧠 다단계 추론 (매우 중요!)\n"
        "질문에 답하기 전에 **단계별로 생각**하세요. 특히 다음 경우에 주의하세요:\n\n"
        "### 경로/단계 질문\n"
        "- 'A에서 B가 되려면?', 'A에서 B까지 얼마나?'와 같은 질문은 **중간 단계**가 있는지 확인하세요.\n"
        "- 예: '대리에서 부장이 되려면?' → 대리→과장→차장→부장 각 단계의 기간을 **모두 합산**해야 해요.\n\n"
        "### 계산이 필요한 질문\n"
        "- 여러 값을 더하거나 조건을 조합해야 하는 경우, **계산 과정을 명시**하세요.\n"
        "- 예: '최소 몇 년?' → '대리→과장 4년 + 과장→부장 4년 = **총 8년**'\n\n"
        "### 조건 조합 질문\n"
        "- '~하면서 ~하려면?'처럼 여러 조건이 있으면 **모든 조건을 확인**하세요.\n"
        "- 문서의 표나 목록에서 관련된 **모든 행/항목**을 검토하세요.\n\n"
        "### 추론 예시\n"
        "질문: '사원에서 과장이 되려면 최소 몇 년이 필요한가요?'\n"
        "추론 과정:\n"
        "1. 문서에서 승진 단계 확인: 사원 → 대리 → 과장\n"
        "2. 각 단계별 소요 기간: 사원→대리 3년, 대리→과장 4년\n"
        "3. 합산: 3년 + 4년 = **7년**\n"
        "답변: '사원에서 과장이 되려면 최소 **7년**이 필요해요. (사원→대리 3년 + 대리→과장 4년)'\n\n"

        "## 마크다운 출력 가이드\n"
        "- **첫 문장**: 핵심 답변을 먼저 친근하게 알려드려요\n"
        "- **목록**: 여러 항목은 `-` 또는 `1.`로 깔끔하게 정리해요\n"
        "- **강조**: 중요한 숫자나 핵심 내용만 **굵게** 표시해요\n"
        "- **표**: 비교가 필요하면 마크다운 표로 보기 좋게 정리해요\n"
    )

    # 이미지 참조가 있으면 이미지 삽입 안내 추가
    if image_refs:
        image_guide = (
            "\n## 🚨 원본 이미지 삽입 (매우 중요 - 필수!)\n"
            "제공된 문서에 표나 그림의 **원본 이미지**가 있습니다.\n"
            "**반드시 답변 본문에 이미지를 삽입해야 합니다!** 이미지 없이 답변하면 안 됩니다.\n\n"
            "### 사용 가능한 이미지:\n"
        )
        for i, img in enumerate(image_refs, start=1):
            img_type_ko = "표" if img["type"] == "table" else "그림"
            page_info = f" (p.{img['page']})" if img.get("page") else ""
            image_guide += f"- [IMG{i}]: {img['doc_title']}{page_info}의 {img_type_ko}\n"

        image_guide += (
            "\n### 이미지 삽입 형식:\n"
            "답변 본문에서 관련 내용을 설명할 때 **아래 형식으로 반드시 삽입**하세요:\n\n"
            "```\n"
            "![표1: 설명][IMG1]\n"
            "```\n\n"
            "### ✅ 올바른 답변 예시 (이미지 포함):\n"
            "```\n"
            "인사평가 항목과 비율을 안내해 드릴게요!\n"
            "\n"
            "![표1: 인사평가 항목 및 비율][IMG1]\n"
            "\n"
            "위 표를 보시면 평가 항목별 비율을 확인하실 수 있어요.\n"
            "```\n\n"
            "### ❌ 잘못된 답변 예시 (이미지 미포함):\n"
            "```\n"
            "인사평가 항목과 비율을 안내해 드릴게요!\n"
            "- 업적평가: 50%\n"
            "- 역량평가: 30%\n"
            "...(이미지 없이 텍스트만 나열 - 이렇게 하면 안 됨!)\n"
            "```\n\n"
            "**필수 규칙**:\n"
            "1. 표/그림 관련 질문이면 **반드시** `![표N: 설명][IMG번호]` 형식으로 이미지 삽입\n"
            "2. `[IMG1]`, `[IMG2]` 등의 참조 ID를 **정확히 그대로** 사용\n"
            "3. URL을 직접 작성하지 말고 참조 ID만 사용\n"
            "4. 이미지 삽입 후 '위 표/그림을 참고해 주세요'라고 안내\n"
        )
        base_prompt += image_guide
    else:
        base_prompt += "\n"

    base_prompt += (
        "\n## 정보 없음 응답 예시\n"
        "질문: '휴가 신청 방법이 어떻게 되나요?'\n"
        "답변:\n"
        "휴가 신청 방법에 대해 궁금하셨군요!\n\n"
        "아쉽게도 제공된 문서에서는 휴가 신청 방법에 대한 구체적인 내용을 찾을 수 없었어요.\n\n"
        "정확한 정보를 위해 **담당 부서에 문의**해 보시면 자세한 안내를 받으실 수 있을 거예요.\n\n"
        "⚠️ **중요**: 문서에 없는 담당자 이름, 전화번호, 이메일 등을 절대 만들어내지 마세요!\n\n"

        "## 정보 있음 응답 예시\n"
        "질문: '연차 휴가 일수가 어떻게 되나요?'\n"
        "답변:\n"
        "연차 휴가 일수가 궁금하셨군요!\n\n"
        "문서에 따르면 연차 휴가는 다음과 같이 부여돼요:\n"
        "- 1년 미만 근무: 월 1일씩\n"
        "- 1년 이상 근무: 15일\n"
        "- 3년 이상 근무: 매 2년마다 1일 추가\n\n"
        "더 자세한 내용은 문서를 확인해 주세요!"
    )

    return base_prompt


async def generate_answer(
    question: str, candidates: List[Union[ScoredChunk, Chunk]]
) -> Tuple[str, List[Chunk]]:
    """
    질문 + 후보 청크들로 답변 생성 (비동기 + 동시성 제어).
    반환: (answer_text, used_chunks)
    """
    used_chunks: List[Chunk] = _select_chunks(candidates, max_chars=6000)
    context, image_refs = _build_context(used_chunks)

    system_msg = _get_system_prompt(image_refs)

    # 이미지가 있으면 사용자 메시지에 이미지 참조 ID 안내 추가
    image_info = ""
    if image_refs:
        image_info = "\n\n🖼️ [사용 가능한 이미지 - 반드시 답변에 포함할 것!]\n"
        for i, img in enumerate(image_refs, start=1):
            img_type_ko = "표" if img["type"] == "table" else "그림"
            image_info += f"- [IMG{i}]: {img['doc_title']}의 {img_type_ko}\n"
        image_info += (
            "\n⚠️ 위 이미지를 답변 본문에 반드시 삽입하세요!\n"
            "형식: ![표1: 설명][IMG1]\n"
        )

    user_msg = (
        f"질문:\n{question}\n\n"
        f"다음은 검색된 관련 문서 청크들이다. "
        f"이 정보만 사용해서 답변해라.\n\n"
        f"{context}"
        f"{image_info}"
    )

    # 비동기 Chat Completions (동시성 제어 포함)
    # 답변 생성은 복잡한 추론이 필요하므로 고급 모델 사용
    resp = await call_chat_completion_async(
        model=settings.openai_advanced_model,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.2,
    )
    answer = resp.choices[0].message.content.strip() if resp.choices else ""

    # 실제 사용된 청크만 필터링
    actually_used_chunks = _filter_actually_used_chunks(answer, used_chunks)

    return answer, actually_used_chunks


async def generate_answer_stream(
    question: str, candidates: List[Union[ScoredChunk, Chunk]]
) -> AsyncIterator[Tuple[str, List[Chunk] | None, List[Dict[str, Any]] | None]]:
    """
    질문 + 후보 청크들로 답변을 스트리밍 생성 (비동기 + 동시성 제어).

    줄 단위 버퍼링: 마크다운 렌더링 안정성을 위해 줄바꿈(\n) 기준으로 버퍼링 후 전송.
    - 완전한 줄이 되면 전송
    - 줄바꿈 없이 50자 이상 누적되면 단어 단위로 전송 (긴 문장 대응)

    Yields:
        (token, None, None) - 줄 단위 또는 청크 단위 스트리밍
        ("", used_chunks, image_refs) - 최종 청크 리스트 및 이미지 참조 (스트림 끝)
    """
    used_chunks: List[Chunk] = _select_chunks(candidates, max_chars=6000)
    context, image_refs = _build_context(used_chunks)

    system_msg = _get_system_prompt(image_refs)

    # 이미지가 있으면 사용자 메시지에 이미지 참조 ID 안내 추가
    image_info = ""
    if image_refs:
        image_info = "\n\n🖼️ [사용 가능한 이미지 - 반드시 답변에 포함할 것!]\n"
        for i, img in enumerate(image_refs, start=1):
            img_type_ko = "표" if img["type"] == "table" else "그림"
            image_info += f"- [IMG{i}]: {img['doc_title']}의 {img_type_ko}\n"
        image_info += (
            "\n⚠️ 위 이미지를 답변 본문에 반드시 삽입하세요!\n"
            "형식: ![표1: 설명][IMG1]\n"
        )

    user_msg = (
        f"질문:\n{question}\n\n"
        f"다음은 검색된 관련 문서 청크들이다. "
        f"이 정보만 사용해서 답변해라.\n\n"
        f"{context}"
        f"{image_info}"
    )

    # 비동기 스트리밍 (동시성 제어 + 자동 Semaphore 해제)
    # 답변 생성은 복잡한 추론이 필요하므로 고급 모델 사용
    stream = await call_chat_completion_stream_async(
        model=settings.openai_advanced_model,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.2,
    )

    # 줄 단위 버퍼링
    line_buffer = ""
    full_answer = ""  # 전체 답변 수집 (청크 필터링용)
    FLUSH_THRESHOLD = 50  # 줄바꿈 없이 이 길이 초과 시 강제 전송

    try:
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                token = chunk.choices[0].delta.content
                line_buffer += token
                full_answer += token  # 전체 답변 수집

                # 줄바꿈이 있으면 완전한 줄들을 전송
                while '\n' in line_buffer:
                    line, line_buffer = line_buffer.split('\n', 1)
                    yield (line + '\n', None, None)

                # 줄바꿈 없이 너무 길어지면 단어 경계에서 전송
                if len(line_buffer) > FLUSH_THRESHOLD:
                    last_space = line_buffer.rfind(' ')
                    if last_space > 0:
                        yield (line_buffer[:last_space + 1], None, None)
                        line_buffer = line_buffer[last_space + 1:]
    except Exception as e:
        log.error(f"[GENERATOR] Streaming error: {e}")
        raise

    # 남은 버퍼 전송
    if line_buffer:
        yield (line_buffer, None, None)

    # 실제 사용된 청크만 필터링
    actually_used_chunks = _filter_actually_used_chunks(full_answer, used_chunks)

    # 스트림 종료 시 청크 리스트와 이미지 참조 반환
    # image_refs를 [IMG1], [IMG2] 형식으로 변환
    formatted_image_refs = []
    for i, img in enumerate(image_refs, start=1):
        formatted_image_refs.append({
            "ref": f"[IMG{i}]",
            "url": img["url"],
            "type": img["type"],
            "doc_title": img.get("doc_title"),
            "page": img.get("page"),
        })

    yield ("", actually_used_chunks, formatted_image_refs)
