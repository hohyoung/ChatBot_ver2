"""
PDF 처리 모듈

PDF 파일의 페이지 정보를 보존하면서 청크를 생성하는 기능 제공.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Tuple

from app.ingest.parsers.pdf import parse_pdf
from app.services.storage import DOCS_DIR
from app.services.logging import get_logger

log = get_logger("app.ingest.pdf_processor")


# --------------------------------------------------------------------------
# 공통 헬퍼
# --------------------------------------------------------------------------
def norm_rel_and_url(dst_path: Path) -> Tuple[str, str]:
    """
    DOCS_DIR 기준 상대경로를 구해 슬래시 표준화.
    - doc_relpath: 항상 'public/<...>'
    - doc_url: 항상 '/static/docs/<...>'  (여기서 <...>은 public/ 제거한 rel_core)
    """
    try:
        rel = str(dst_path.resolve().relative_to(DOCS_DIR.resolve()))
    except Exception:
        rel = str(dst_path)

    rel = rel.replace("\\", "/").lstrip("/")

    # rel_core: URL용 (public/ 또는 static/docs/ 프리픽스를 제거)
    rel_core = rel
    for p in ("public/", "static/docs/"):
        if rel_core.startswith(p):
            rel_core = rel_core[len(p):]

    # doc_relpath: 저장소 상대경로는 항상 public/을 유지
    doc_relpath = rel if rel.startswith("public/") else f"public/{rel_core}"
    # doc_url: 웹 경로(항상 /static/docs/<rel_core>)
    doc_url = f"/static/docs/{rel_core}"
    return doc_relpath, doc_url


def is_pdf(ftype) -> bool:
    """detect_type 결과가 무엇이든 문자열화 해서 'pdf' 포함 여부로 판별"""
    try:
        return "pdf" in str(ftype).lower()
    except Exception:
        return False


# --------------------------------------------------------------------------
# PDF 전용: 페이지 정보를 보존하기 위한 헬퍼
# --------------------------------------------------------------------------
def pdf_blocks_with_pages(file_path: Path) -> List[Tuple[int, str]]:
    """
    PDF를 (page_no, paragraph) 블록으로 변환.
    - parse_pdf: List[str] (페이지별) 또는 str(전문) 모두 처리
    - 페이지가 분리되지 않으면 1페이지로 보고 블록 생성
    """
    pages = parse_pdf(file_path)

    # 타입 정규화
    if isinstance(pages, str):
        parts = (
            [p for p in re.split(r"\f+", pages) if p.strip()]
            if "\f" in pages
            else [pages]
        )
        pages = parts or [pages]
    elif not isinstance(pages, list):
        pages = [str(pages or "")]

    blocks = []
    for pno, text in enumerate(pages, start=1):
        t = (text or "").strip()
        if not t:
            continue
        # 빈 줄 기준 문단화 (없으면 줄 단위)
        paras = [pp.strip() for pp in re.split(r"\n\s*\n", t) if pp.strip()] or [
            ln.strip() for ln in t.splitlines() if ln.strip()
        ]
        for para in paras:
            blocks.append((pno, para))
    return blocks


def merge_with_pages(
    blocks: List[Tuple[int, str]],
    *,
    max_chars: int = 1200,
) -> Tuple[List[str], List[Tuple[Optional[int], Optional[int]]]]:
    """
    (page_no, paragraph) 블록을 받아 페이지 범위를 보존하며 청크 병합.
    반환값: (chunks_text, page_ranges)
      - chunks_text: List[str]
      - page_ranges: List[(page_start, page_end)]  # 각 청크와 1:1 매칭
    """
    chunks: List[str] = []
    ranges: List[Tuple[Optional[int], Optional[int]]] = []

    cur = ""
    start_p: Optional[int] = None
    end_p: Optional[int] = None

    for pno, para in blocks:
        if not cur:
            start_p = pno
        if len(cur) + len(para) + 1 <= max_chars:
            cur = (cur + "\n" if cur else "") + para
            end_p = pno
        else:
            if cur:
                chunks.append(cur.strip())
                ranges.append((start_p, end_p or start_p))
            # 새 청크 시작
            cur = para.strip()
            start_p = pno
            end_p = pno

    if cur:
        chunks.append(cur.strip())
        ranges.append((start_p, end_p or start_p))

    return chunks, ranges
