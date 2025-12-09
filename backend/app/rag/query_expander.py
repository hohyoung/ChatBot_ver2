# backend/app/rag/query_expander.py
"""
Query Expander - GAR Phase 2

단일 쿼리를 여러 표현으로 확장하여 재현율(Recall)을 극대화합니다.

전략:
1. LLM을 사용한 동의어/구체화/일반화
2. 문서 컨텍스트 기반 확장
3. 규칙 기반 태그 자동 추출
"""

from __future__ import annotations

import re
from typing import List, Dict, Tuple
from app.services.openai_client import get_client
from app.services.logging import get_logger

log = get_logger("app.rag.query_expander")

# 표/기준표 탐색 키워드 → 확장 쿼리
# "표 보여줘" 같은 탐색 요청을 구체적인 검색어로 확장
TABLE_EXPLORE_KEYWORDS: List[str] = [
    "표", "기준표", "별표", "목록", "테이블",
]

TABLE_EXPAND_TERMS: List[str] = [
    "별표", "<별표", "표>", "기준표", "기준",
    "### 표", "| ", "---|",  # 마크다운 표 패턴
]

# 음차 표기 사전 (한글 발음 → 영문 원어)
# 쿼리에 한글 음차가 있으면 영문으로 변환한 쿼리도 검색에 포함
PHONETIC_MAP: Dict[str, str] = {
    # 어학 시험
    "토익": "TOEIC",
    "토플": "TOEFL",
    "오픽": "OPIc",
    "아이엘츠": "IELTS",
    "텝스": "TEPS",
    "지텔프": "G-TELP",
    # IT/소프트웨어
    "엑셀": "Excel",
    "파워포인트": "PowerPoint",
    "피피티": "PPT",
    "워드": "Word",
    "아웃룩": "Outlook",
    "에스큐엘": "SQL",
    "파이썬": "Python",
    "자바": "Java",
    # 자격증
    "피엠피": "PMP",
    "시스코": "Cisco",
    # 기타 비즈니스 용어
    "이메일": "email",
    "미팅": "meeting",
}


class QueryExpander:
    """쿼리 확장기: 단일 쿼리를 3~5개의 확장 쿼리로 변환"""

    def __init__(self):
        self.client = get_client()

    def expand_phonetic(self, query: str) -> List[str]:
        """
        음차 표기 확장: 한글 음차를 영문 원어로 변환

        쿼리에 음차 단어가 있을 때만 변환된 쿼리를 반환합니다.

        Args:
            query: 원본 쿼리

        Returns:
            음차 변환된 쿼리 리스트 (없으면 빈 리스트)

        Example:
            >>> expander = QueryExpander()
            >>> expander.expand_phonetic("토익 점수 기준")
            ['TOEIC 점수 기준']
            >>> expander.expand_phonetic("연차 규정")
            []
        """
        expanded = []
        found_phonetics: List[Tuple[str, str]] = []

        # 쿼리에서 음차 단어 검출
        for korean, english in PHONETIC_MAP.items():
            if korean in query:
                found_phonetics.append((korean, english))

        if not found_phonetics:
            return []

        # 음차 변환 쿼리 생성
        converted_query = query
        for korean, english in found_phonetics:
            converted_query = converted_query.replace(korean, english)

        if converted_query != query:
            expanded.append(converted_query)
            log.debug(
                "음차 확장: %r → %r (변환: %s)",
                query,
                converted_query,
                found_phonetics,
            )

        return expanded

    def expand_for_table_explore(self, query: str) -> List[str]:
        """
        표 탐색 의도 쿼리 확장

        "표 보여줘", "기준표 확인" 같은 탐색 요청을
        실제 문서에서 표를 찾을 수 있는 구체적인 검색어로 확장합니다.

        Args:
            query: 원본 쿼리

        Returns:
            확장된 쿼리 리스트

        Example:
            >>> expander = QueryExpander()
            >>> expander.expand_for_table_explore("영어평가 기준표 보여줘")
            ['영어평가 기준표', '영어평가 별표', '<별표 영어평가', '영어평가 기준']
        """
        expanded = []

        # 탐색 키워드 제거하고 핵심어 추출
        core_query = query
        remove_words = ["보여줘", "보여줄래", "확인해줘", "알려줘", "찾아줘", "뭐야", "뭐지", "있어"]
        for word in remove_words:
            core_query = core_query.replace(word, "").strip()

        # 표 관련 키워드도 일단 제거해서 핵심 주제어만 추출
        topic = core_query
        for kw in TABLE_EXPLORE_KEYWORDS:
            topic = topic.replace(kw, "").strip()

        if not topic:
            # 핵심 주제어가 없으면 일반적인 표 검색어
            topic = "기준"

        # 확장 쿼리 생성
        for term in TABLE_EXPAND_TERMS[:5]:  # 상위 5개만
            expanded_query = f"{topic} {term}".strip()
            if expanded_query not in expanded and expanded_query != query:
                expanded.append(expanded_query)

        # 원본에서 "표"를 "별표"로 치환
        if "표" in query and "별표" not in query:
            expanded.append(query.replace("표", "별표"))

        log.debug(
            "표 탐색 확장: %r → %s (topic=%r)",
            query,
            expanded[:4],
            topic,
        )

        return expanded[:4]  # 최대 4개

    def is_table_explore_intent(self, query: str) -> bool:
        """
        쿼리가 표 탐색 의도인지 빠르게 판단 (규칙 기반)

        LLM 호출 없이 키워드 기반으로 빠르게 판단합니다.

        Args:
            query: 원본 쿼리

        Returns:
            True이면 표 탐색 의도
        """
        explore_keywords = ["보여", "확인", "찾아", "알려"]
        table_keywords = TABLE_EXPLORE_KEYWORDS

        has_explore = any(kw in query for kw in explore_keywords)
        has_table = any(kw in query for kw in table_keywords)

        return has_explore and has_table

    async def expand_query(
        self,
        original_query: str,
        doc_context: List[str],
        max_expansions: int = 3,
    ) -> List[str]:
        """
        LLM을 사용해 쿼리 확장

        Args:
            original_query: 원본 질문
            doc_context: 사용 가능한 문서 제목 리스트 (예: ["인사규정 2024.pdf", ...])
            max_expansions: 최대 확장 개수 (기본 3개)

        Returns:
            확장된 쿼리 리스트 [원본, 확장1, 확장2, 확장3]

        Example:
            >>> expander = QueryExpander()
            >>> await expander.expand_query(
            ...     "2024년 입사자 연차",
            ...     ["인사규정 2024.pdf", "연차규정.pdf"],
            ...     max_expansions=3
            ... )
            ['2024년 입사자 연차',
             '2024년 신입사원 연차 휴가 일수',
             '입사 1년차 연차 개수',
             '2024 채용 휴가 규정']
        """
        log.info(
            "쿼리 확장 시작: query=%r, doc_context=%d개, max=%d",
            original_query,
            len(doc_context),
            max_expansions,
        )

        # 문서 컨텍스트를 간결하게 요약 (프롬프트 길이 절약)
        doc_summary = ", ".join(doc_context[:10])  # 최대 10개만
        if len(doc_context) > 10:
            doc_summary += f" 외 {len(doc_context) - 10}개"

        prompt = f"""다음 질문을 분석하고 {max_expansions}가지 다른 표현으로 확장하세요.

원본 질문: {original_query}

사용 가능한 문서: {doc_summary}

요구사항:
1. **오타 교정 필수**: 오타가 있다면 교정하세요 (예: "살려줄래" → "알려줄래")
2. **띄어쓰기 변형 필수**: 핵심 명사에 글자 사이 띄어쓰기를 넣은 변형을 반드시 포함하세요
   - 예: "과장" → "과 장", "임용기준" → "임 용 기 준"
   - 예: "사무국장" → "사 무 국 장", "연차휴가" → "연 차 휴 가"
   - 문서가 OCR로 스캔되어 띄어쓰기가 불규칙할 수 있으므로 이 변형이 매우 중요합니다
3. 동의어 사용 (예: "연차" → "휴가")
4. 의미는 동일하게 유지

출력 형식:
1. [오타 교정된 원본 질문]
2. [핵심 명사에 띄어쓰기를 넣은 변형]
3. [동의어를 사용한 변형]

예시:
- 입력: "과장 임용기준"
- 출력:
  1. 과장 임용기준
  2. 과 장 임 용 기 준
  3. 3급 승진 자격"""

        try:
            # OpenAI 클라이언트는 동기식이므로 await 제거
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",  # 비용 절감 (쿼리 확장은 간단한 작업)
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,  # 낮은 온도로 일관성 유지
                max_tokens=300,  # 짧은 응답만 필요
            )

            content = response.choices[0].message.content.strip()
            log.debug("LLM 응답:\n%s", content)

            # 파싱: "1. 쿼리" 형식에서 쿼리만 추출
            expanded = self._parse_expansions(content, max_expansions)

            # 원본 쿼리 + 확장 쿼리 (중복 제거)
            result = [original_query]
            for query in expanded:
                if query and query not in result:
                    result.append(query)

            # 음차 확장 추가 (한글 음차 → 영문 원어)
            phonetic_expanded = self.expand_phonetic(original_query)
            for query in phonetic_expanded:
                if query not in result:
                    result.append(query)

            # 표 탐색 의도 확장 추가
            table_expanded = []
            if self.is_table_explore_intent(original_query):
                table_expanded = self.expand_for_table_explore(original_query)
                for query in table_expanded:
                    if query not in result:
                        result.append(query)

            log.info(
                "쿼리 확장 완료: %d개 생성 (음차: %d개, 표탐색: %d개)",
                len(result) - 1,
                len(phonetic_expanded),
                len(table_expanded),
            )
            for i, q in enumerate(result):
                log.debug("  [%d] %r", i, q)

            return result

        except Exception as e:
            log.warning("쿼리 확장 실패 (원본만 반환): %s", e, exc_info=True)
            return [original_query]  # 실패 시 원본만 반환

    def _parse_expansions(self, content: str, max_count: int) -> List[str]:
        """
        LLM 응답 파싱

        지원 형식:
        - "1. 쿼리"
        - "- 쿼리"
        - "쿼리" (줄바꿈으로 구분)
        """
        expanded = []
        lines = content.strip().split("\n")

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # "1. 쿼리" 형식
            match = re.match(r"^\d+\.\s*(.+)$", line)
            if match:
                query = match.group(1).strip()
            # "- 쿼리" 형식
            elif line.startswith("- "):
                query = line[2:].strip()
            else:
                # 그냥 텍스트
                query = line

            # 유효성 검사
            if len(query) > 5 and len(query) < 100:  # 너무 짧거나 긴 것 제외
                expanded.append(query)

            if len(expanded) >= max_count:
                break

        return expanded[:max_count]

    def extract_tags_from_context(self, doc_context: List[str]) -> List[str]:
        """
        문서 컨텍스트에서 태그 자동 추출

        전략:
        1. 규칙 기반 키워드 매핑
        2. 년도 추출 (2020~2030)
        3. 중복 제거

        Args:
            doc_context: 문서 제목 리스트

        Returns:
            추출된 태그 리스트

        Example:
            >>> expander = QueryExpander()
            >>> expander.extract_tags_from_context(["인사규정 2024.pdf", "연차휴가 매뉴얼.pdf"])
            ['hr-policy', '2024', 'vacation', 'policy']
        """
        tags = set()

        # 규칙 기반 키워드 → 태그 매핑
        keyword_to_tag = {
            "인사": "hr-policy",
            "규정": "policy",
            "연차": "vacation",
            "휴가": "vacation",
            "휴무": "leave",
            "급여": "salary",
            "보수": "salary",
            "복지": "welfare",
            "평가": "evaluation",
            "고과": "evaluation",
            "채용": "recruitment",
            "입사": "recruitment",
            "퇴직": "retirement",
            "해고": "termination",
            "징계": "discipline",
            "보안": "security",
            "개인정보": "privacy",
            "안전": "safety",
            "매뉴얼": "manual",
            "가이드": "guide",
        }

        for doc in doc_context:
            doc_lower = doc.lower()

            # 년도 추출 (2020~2030)
            years = re.findall(r"20[2-3]\d", doc)
            tags.update(years)

            # 키워드 매칭
            for keyword, tag in keyword_to_tag.items():
                if keyword in doc:
                    tags.add(tag)

        result = sorted(list(tags))  # 정렬로 일관성 확보
        log.debug("문서 컨텍스트에서 태그 추출: %s → %s", doc_context[:3], result)
        return result

    async def expand_with_synonyms(self, query: str) -> List[str]:
        """
        동의어 기반 간단한 확장 (LLM 없이)

        규칙 기반으로 빠르게 확장 (폴백용)

        Args:
            query: 원본 쿼리

        Returns:
            동의어 적용된 쿼리 리스트
        """
        synonyms = {
            "연차": ["휴가", "annual leave"],
            "입사": ["채용", "신입"],
            "퇴사": ["퇴직", "이직"],
            "급여": ["보수", "월급", "연봉"],
            "규정": ["정책", "policy"],
        }

        expanded = [query]

        for original, syns in synonyms.items():
            if original in query:
                for syn in syns:
                    new_query = query.replace(original, syn)
                    if new_query not in expanded:
                        expanded.append(new_query)

        return expanded[:4]  # 최대 4개 (원본 + 3개)


# 편의 함수
async def expand_query(
    original_query: str,
    doc_context: List[str],
    max_expansions: int = 3,
) -> List[str]:
    """
    쿼리 확장 편의 함수

    Example:
        >>> from app.rag.query_expander import expand_query
        >>> queries = await expand_query("2024년 연차", ["인사규정 2024.pdf"])
    """
    expander = QueryExpander()
    return await expander.expand_query(original_query, doc_context, max_expansions)


def extract_tags(doc_context: List[str]) -> List[str]:
    """태그 추출 편의 함수"""
    expander = QueryExpander()
    return expander.extract_tags_from_context(doc_context)
