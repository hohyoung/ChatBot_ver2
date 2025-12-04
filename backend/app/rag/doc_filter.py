# backend/app/rag/doc_filter.py
"""
Document Filter - GAR Phase 2

Intent와 문서 컨텍스트 기반으로 검색 범위를 좁혀 정확도를 높입니다.

전략:
1. Intent별 필터 전략
   - doc_request: 문서명 정확 매칭
   - info_request: 태그 기반 OR 조건
   - multi_step: 서브쿼리별로 처리 (필터 없음)
2. 년도 필터 (최신 년도 우선)
3. ChromaDB where 절 생성
"""

from __future__ import annotations

import re
from typing import List, Optional, Dict, Any
from app.services.logging import get_logger

log = get_logger("app.rag.doc_filter")


class DocumentFilter:
    """문서 레벨 필터링: 검색 전 문서 범위 축소"""

    def build_filter_criteria(
        self,
        intent: str,
        doc_context: List[str],
        tags: List[str],
    ) -> Optional[Dict[str, Any]]:
        """
        ChromaDB where 필터 생성

        Args:
            intent: Intent 타입 (doc_request/info_request/multi_step)
            doc_context: 사용 가능한 문서 제목 리스트
            tags: 쿼리 태그 리스트

        Returns:
            ChromaDB where 필터 딕셔너리 또는 None (필터 없음)

        Example:
            >>> filter = DocumentFilter()
            >>> criteria = filter.build_filter_criteria(
            ...     intent="info_request",
            ...     doc_context=["인사규정 2024.pdf"],
            ...     tags=["vacation", "2024"]
            ... )
            >>> # {'$or': [{'tags': {'$contains': 'vacation'}}, {'tags': {'$contains': '2024'}}]}
        """
        log.info(
            "필터 생성 시작: intent=%s, docs=%d개, tags=%s",
            intent,
            len(doc_context),
            tags,
        )

        criteria = {}

        # 1. Intent 기반 필터
        # 주의: ChromaDB 메타데이터 필터는 $contains를 지원하지 않음
        # 태그는 CSV 문자열로 저장되므로 정확한 매칭만 가능
        # 태그 기반 필터링은 검색 후 후처리로 수행

        if intent == "doc_request":
            # 문서 요청: doc_title 정확히 매칭
            if doc_context:
                titles = [self._extract_title(doc) for doc in doc_context]
                # 중복 제거
                titles = list(set(titles))
                log.debug("문서 요청 → doc_title 필터: %s", titles)
                criteria["doc_title"] = {"$in": titles}

        elif intent == "info_request":
            # 정보 요청: 태그 필터링은 후처리에서 수행
            # ChromaDB는 CSV 문자열 부분 매칭을 지원하지 않음
            log.debug("정보 요청 → 태그 필터는 후처리로 위임 (tags=%s)", tags)

        elif intent == "multi_step":
            # 복합 질문: 필터 없음 (서브쿼리별로 개별 처리)
            log.debug("복합 질문 → 필터 없음")
            return None

        # 2. 년도 필터: ChromaDB에서 직접 지원하지 않으므로 후처리로 위임
        years = self._extract_years(tags)
        if years:
            latest_year = max(years)
            log.debug("년도 필터 → 후처리로 위임: %s", latest_year)

        # 3. 기본 visibility 필터 (항상 적용)
        # public 또는 org 문서만 검색 (private 제외)
        visibility_filter = {"visibility": {"$in": ["public", "org"]}}

        if criteria:
            # ChromaDB는 최상위에 하나의 연산자만 허용
            # $or 또는 다른 조건이 있으면 $and로 감싸서 visibility와 결합
            criteria = {"$and": [criteria, visibility_filter]}
        else:
            # 필터가 비어있으면 visibility만
            criteria = visibility_filter

        log.info("필터 생성 완료: %s", criteria)
        return criteria if criteria else None

    def _extract_title(self, filename: str) -> str:
        """
        파일명에서 핵심 제목 추출

        Args:
            filename: 파일명 (예: "인사규정 2024.pdf")

        Returns:
            핵심 제목 (예: "인사규정")

        Example:
            >>> filter = DocumentFilter()
            >>> filter._extract_title("인사규정 2024.pdf")
            '인사규정'
        """
        # 확장자 제거
        name = filename.replace(".pdf", "").replace(".docx", "").replace(".txt", "")

        # 년도 제거 (2020~2030)
        name = re.sub(r"\s*20[2-3]\d\s*", " ", name).strip()

        # 괄호 내용 제거 (예: "인사규정 (개정판)")
        name = re.sub(r"\s*[\(\[].+?[\)\]]\s*", " ", name).strip()

        # 다중 공백 제거
        name = re.sub(r"\s+", " ", name).strip()

        return name

    def _extract_years(self, tags: List[str]) -> List[int]:
        """
        태그에서 년도 추출

        Args:
            tags: 태그 리스트

        Returns:
            년도 리스트 (int)

        Example:
            >>> filter = DocumentFilter()
            >>> filter._extract_years(["vacation", "2024", "hr-policy"])
            [2024]
        """
        years = []
        for tag in tags:
            # 4자리 숫자이고 2020~2030 범위
            if tag.isdigit() and len(tag) == 4:
                year = int(tag)
                if 2020 <= year <= 2030:
                    years.append(year)
        return years

    def merge_filters(
        self,
        filter1: Optional[Dict[str, Any]],
        filter2: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """
        두 필터를 AND 조건으로 병합

        Args:
            filter1: 첫 번째 필터
            filter2: 두 번째 필터

        Returns:
            병합된 필터

        Example:
            >>> filter = DocumentFilter()
            >>> f1 = {"doc_title": {"$in": ["인사규정"]}}
            >>> f2 = {"tags": {"$contains": "2024"}}
            >>> filter.merge_filters(f1, f2)
            {'$and': [{'doc_title': {'$in': ['인사규정']}}, {'tags': {'$contains': '2024'}}]}
        """
        if not filter1:
            return filter2
        if not filter2:
            return filter1

        # ChromaDB $and 조건
        return {"$and": [filter1, filter2]}


# 편의 함수
def build_filter(
    intent: str,
    doc_context: List[str],
    tags: List[str],
) -> Optional[Dict[str, Any]]:
    """
    필터 생성 편의 함수

    Example:
        >>> from app.rag.doc_filter import build_filter
        >>> criteria = build_filter("info_request", ["인사규정.pdf"], ["vacation"])
    """
    doc_filter = DocumentFilter()
    return doc_filter.build_filter_criteria(intent, doc_context, tags)
