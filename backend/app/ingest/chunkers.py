from __future__ import annotations
from typing import Iterable, List, Tuple, Optional, Dict
from pathlib import Path

# Import structure analyzer (conditional)
try:
    from app.ingest.parsers.structure_analyzer import (
        analyze_pdf_structure,
        DocumentStructure
    )
    HAS_STRUCTURE_ANALYZER = True
except ImportError:
    HAS_STRUCTURE_ANALYZER = False

from app.services.logging import get_logger

log = get_logger(__name__)


def merge_blocks_to_chunks(
    blocks: Iterable[str],
    *,
    min_chars: int = 500,
    max_chars: int = 1200,
    overlap: int = 150,
) -> List[str]:
    """
    문단 리스트를 받아 길이 범위에 맞춰 청크로 병합.
    - 너무 짧은 것은 이전/다음과 합치고, 너무 긴 것은 적당히 잘라서 겹침(overlap) 부여.
    """
    chunks: List[str] = []
    buf: List[str] = []
    size = 0

    def flush():
        nonlocal buf, size
        if buf:
            text = "\n".join(buf).strip()
            if text:
                chunks.append(text)
            buf, size = [], 0

    for block in blocks:
        b = block.strip()
        if not b:
            continue
        if size + len(b) + 1 <= max_chars:
            buf.append(b)
            size += len(b) + 1
            continue

        # 현재 buf를 청크로 내보내기
        if size >= min_chars:
            flush()
            buf.append(b)
            size = len(b)
        else:
            # 최소 길이 미달이면 조금 오버해도 합치기
            buf.append(b)
            size += len(b) + 1
            flush()

    flush()

    # 긴 청크는 잘라서 overlap 부여
    final: List[str] = []
    for ch in chunks:
        if len(ch) <= max_chars:
            final.append(ch)
            continue
        start = 0
        while start < len(ch):
            end = min(len(ch), start + max_chars)
            part = ch[start:end]
            final.append(part.strip())
            if end == len(ch):
                break
            start = end - overlap  # 겹침
            if start < 0:
                start = 0
    return [c for c in final if c]


# =============================================================================
# 구조 기반 청킹 (P0-2.5)
# =============================================================================

def chunk_by_structure(
    pdf_path: Path,
    *,
    max_chars: int = 2000,
    split_large_articles: bool = True
) -> Tuple[List[str], List[Tuple[Optional[int], Optional[int]]], List[Dict]]:
    """
    PDF 문서를 구조(조항) 단위로 청킹

    Args:
        pdf_path: PDF 파일 경로
        max_chars: 최대 청크 크기 (조항이 너무 크면 분할)
        split_large_articles: 큰 조항을 하위 항목으로 분할할지 여부

    Returns:
        Tuple of:
        - chunks_text: List[str] - 청크 텍스트 리스트
        - page_ranges: List[(page_start, page_end)] - 페이지 범위
        - metadata: List[Dict] - 구조 메타데이터
            - section_title: "제1조 (목적)"
            - article_number: "1"
            - hierarchy_level: 1
            - parent_article: None or "1"
            - is_complete_article: True/False
    """
    if not HAS_STRUCTURE_ANALYZER:
        log.warning(
            "[CHUNK-STRUCTURE] Structure analyzer not available, "
            "falling back to simple chunking"
        )
        return [], [], []

    log.info(f"[CHUNK-STRUCTURE] Analyzing {pdf_path.name} for structural chunking")

    # 1. 문서 구조 분석
    structures = analyze_pdf_structure(pdf_path)

    if not structures:
        log.warning(f"[CHUNK-STRUCTURE] No structure found in {pdf_path.name}")
        return [], [], []

    chunks_text = []
    page_ranges = []
    metadata = []

    # 2. 조항별로 청크 생성
    for article in structures:
        # 조항 전체 텍스트 구성
        full_text = _build_article_text(article)

        # 조항이 너무 크면 분할
        if len(full_text) > max_chars and split_large_articles and article.items:
            # 하위 항목으로 분할
            sub_chunks = _split_article_by_items(article, max_chars)
            chunks_text.extend([c["text"] for c in sub_chunks])
            page_ranges.extend([c["page_range"] for c in sub_chunks])
            metadata.extend([c["metadata"] for c in sub_chunks])
        else:
            # 조항 전체를 하나의 청크로
            chunks_text.append(full_text)
            page_ranges.append((article.page_num, article.page_num))
            metadata.append({
                "section_title": article.full_title,
                "article_number": article.number,
                "hierarchy_level": article.hierarchy_level,
                "parent_article": None,
                "is_complete_article": True,
            })

    log.info(
        f"[CHUNK-STRUCTURE] Created {len(chunks_text)} chunks from "
        f"{len(structures)} articles in {pdf_path.name}"
    )

    return chunks_text, page_ranges, metadata


def _build_article_text(article: DocumentStructure) -> str:
    """조항 전체 텍스트 구성"""
    parts = []

    # 제목
    if article.full_title:
        parts.append(article.full_title)

    # 본문
    if article.content:
        parts.append(article.content)

    # 하위 항목들
    for item in article.items:
        item_text = f"{item.number}. {item.content}"
        parts.append(item_text)

    return "\n".join(parts)


def _split_article_by_items(
    article: DocumentStructure,
    max_chars: int
) -> List[Dict]:
    """
    큰 조항을 하위 항목으로 분할

    Args:
        article: DocumentStructure
        max_chars: 최대 청크 크기

    Returns:
        List of dicts with keys: text, page_range, metadata
    """
    chunks = []

    # 조항 제목 + 본문을 헤더로
    header = ""
    if article.full_title:
        header = article.full_title + "\n"
    if article.content:
        header += article.content + "\n"

    # 항목들을 그룹으로 묶기
    current_group = []
    current_size = len(header)

    for item in article.items:
        item_text = f"{item.number}. {item.content}"
        item_size = len(item_text)

        # 현재 그룹에 추가하면 max_chars 초과하는 경우
        if current_size + item_size + 1 > max_chars and current_group:
            # 현재 그룹을 청크로 저장
            chunk_text = header + "\n".join(current_group)
            chunks.append({
                "text": chunk_text.strip(),
                "page_range": (article.page_num, article.page_num),
                "metadata": {
                    "section_title": article.full_title,
                    "article_number": article.number,
                    "hierarchy_level": article.hierarchy_level,
                    "parent_article": None,
                    "is_complete_article": False,  # 부분 조항
                }
            })

            # 새 그룹 시작
            current_group = [item_text]
            current_size = len(header) + item_size
        else:
            # 현재 그룹에 추가
            current_group.append(item_text)
            current_size += item_size + 1

    # 마지막 그룹
    if current_group:
        chunk_text = header + "\n".join(current_group)
        chunks.append({
            "text": chunk_text.strip(),
            "page_range": (article.page_num, article.page_num),
            "metadata": {
                "section_title": article.full_title,
                "article_number": article.number,
                "hierarchy_level": article.hierarchy_level,
                "parent_article": None,
                "is_complete_article": False,
            }
        })

    return chunks
