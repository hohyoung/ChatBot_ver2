"""
PDF 문서 구조 분석기 - P0-2.5

PyMuPDF(fitz)를 사용하여 PDF 문서의 구조를 분석합니다:
- 폰트 크기/스타일 분석
- 제목 감지 (폰트 크기 기반)
- 조항 번호 패턴 인식 (정규식)
- 계층 구조 파싱

사용 예:
    from app.ingest.parsers.structure_analyzer import analyze_pdf_structure

    structure = analyze_pdf_structure(pdf_path)
    for article in structure:
        print(f"{article['full_title']}: {article['content'][:50]}...")
"""

from __future__ import annotations
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

from app.services.logging import get_logger

log = get_logger(__name__)


# =============================================================================
# 데이터 클래스
# =============================================================================

@dataclass
class TextBlock:
    """텍스트 블록 (폰트 정보 포함)"""
    text: str
    page_num: int  # 1-based
    font_size: float
    font_name: str
    bbox: Tuple[float, float, float, float]  # (x0, y0, x1, y1)
    is_bold: bool = False

    @property
    def x0(self) -> float:
        return self.bbox[0]

    @property
    def y0(self) -> float:
        return self.bbox[1]


@dataclass
class DocumentStructure:
    """문서 구조 (조항/섹션)"""
    type: str  # "article" | "section" | "item" | "paragraph"
    number: Optional[str] = None  # "1", "1-1", "가" 등
    title: Optional[str] = None  # "목적", "정의" 등
    full_title: Optional[str] = None  # "제1조 (목적)"
    content: str = ""
    page_num: int = 1
    hierarchy_level: int = 0  # 1=조항, 2=항, 3=호, 4=목
    items: List[DocumentStructure] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """딕셔너리 변환"""
        return {
            "type": self.type,
            "number": self.number,
            "title": self.title,
            "full_title": self.full_title,
            "content": self.content,
            "page_num": self.page_num,
            "hierarchy_level": self.hierarchy_level,
            "items": [item.to_dict() for item in self.items]
        }


# =============================================================================
# 정규식 패턴
# =============================================================================

# 조항 번호 패턴
ARTICLE_PATTERN = re.compile(r'^제(\d+)조\s*(?:\(([^)]+)\))?', re.MULTILINE)

# 항 번호 패턴
ITEM_PATTERNS = [
    (re.compile(r'^(\d+)\.\s'), 1),  # "1. ", "2. " → Level 2
    (re.compile(r'^([가-힣])\.\s'), 2),  # "가. ", "나. " → Level 3
    (re.compile(r'^(\d+)\)\s'), 3),  # "1) ", "2) " → Level 4
    (re.compile(r'^([가-힣])\)\s'), 4),  # "가) ", "나) " → Level 4
]


# =============================================================================
# 폰트 분석
# =============================================================================

def extract_text_blocks(pdf_path: Path) -> List[TextBlock]:
    """
    PDF에서 폰트 정보를 포함한 텍스트 블록 추출

    Args:
        pdf_path: PDF 파일 경로

    Returns:
        TextBlock 리스트
    """
    if fitz is None:
        log.warning("[STRUCTURE] PyMuPDF not available, falling back to simple extraction")
        return []

    blocks = []

    try:
        doc = fitz.open(pdf_path)

        for page_num, page in enumerate(doc, start=1):
            # 텍스트 블록 추출 (폰트 정보 포함)
            text_dict = page.get_text("dict")

            for block in text_dict.get("blocks", []):
                if block.get("type") != 0:  # 0 = text block
                    continue

                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = span.get("text", "").strip()
                        if not text:
                            continue

                        font_size = span.get("size", 12.0)
                        font_name = span.get("font", "")
                        bbox = span.get("bbox", (0, 0, 0, 0))

                        # 볼드 감지 (폰트 이름에 "Bold" 포함)
                        is_bold = "bold" in font_name.lower()

                        blocks.append(TextBlock(
                            text=text,
                            page_num=page_num,
                            font_size=font_size,
                            font_name=font_name,
                            bbox=bbox,
                            is_bold=is_bold
                        ))

        doc.close()
        log.info(f"[STRUCTURE] Extracted {len(blocks)} text blocks from {pdf_path.name}")
        return blocks

    except Exception as e:
        log.error(f"[STRUCTURE] Failed to extract text blocks: {e}")
        return []


def calculate_average_font_size(blocks: List[TextBlock]) -> float:
    """평균 폰트 크기 계산"""
    if not blocks:
        return 12.0

    # 너무 작거나 큰 폰트는 제외 (아웃라이어)
    sizes = [b.font_size for b in blocks if 8.0 <= b.font_size <= 20.0]

    if not sizes:
        return 12.0

    return sum(sizes) / len(sizes)


def is_heading(block: TextBlock, avg_font_size: float, threshold: float = 1.2) -> bool:
    """
    제목 여부 판단

    Args:
        block: 텍스트 블록
        avg_font_size: 평균 폰트 크기
        threshold: 제목으로 간주할 배율 (기본: 평균의 1.2배)

    Returns:
        제목이면 True
    """
    # 폰트 크기가 평균보다 20% 이상 크면 제목
    if block.font_size >= avg_font_size * threshold:
        return True

    # 볼드체면 제목일 가능성 높음
    if block.is_bold and block.font_size >= avg_font_size * 1.1:
        return True

    # 조항 패턴이 있으면 제목
    if ARTICLE_PATTERN.match(block.text):
        return True

    return False


# =============================================================================
# 조항 파싱
# =============================================================================

def parse_article(text: str, page_num: int) -> Optional[DocumentStructure]:
    """
    조항 파싱 (제N조 형태)

    Args:
        text: 텍스트
        page_num: 페이지 번호

    Returns:
        DocumentStructure 또는 None
    """
    match = ARTICLE_PATTERN.match(text)
    if not match:
        return None

    number = match.group(1)
    title = match.group(2) or ""

    # "제1조 (목적)" 형태
    full_title = f"제{number}조"
    if title:
        full_title += f" ({title})"

    # 본문 추출 (제목 이후)
    content = text[match.end():].strip()

    return DocumentStructure(
        type="article",
        number=number,
        title=title,
        full_title=full_title,
        content=content,
        page_num=page_num,
        hierarchy_level=1
    )


def parse_item(text: str, page_num: int) -> Optional[Tuple[DocumentStructure, int]]:
    """
    항/호/목 파싱 (1., 가., 1), 가) 형태)

    Args:
        text: 텍스트
        page_num: 페이지 번호

    Returns:
        (DocumentStructure, level) 또는 None
    """
    for pattern, level in ITEM_PATTERNS:
        match = pattern.match(text)
        if match:
            number = match.group(1)
            content = text[match.end():].strip()

            return DocumentStructure(
                type="item",
                number=number,
                content=content,
                page_num=page_num,
                hierarchy_level=level + 1  # 조항=1, 항=2, 호=3, 목=4
            ), level

    return None


# =============================================================================
# 구조 분석
# =============================================================================

def merge_text_blocks(blocks: List[TextBlock]) -> List[Tuple[str, int]]:
    """
    텍스트 블록을 줄 단위로 병합

    Args:
        blocks: TextBlock 리스트

    Returns:
        (text, page_num) 튜플 리스트
    """
    if not blocks:
        return []

    # 페이지, Y좌표 기준 정렬
    sorted_blocks = sorted(blocks, key=lambda b: (b.page_num, b.y0, b.x0))

    lines = []
    current_line = []
    current_page = sorted_blocks[0].page_num
    current_y = sorted_blocks[0].y0

    for block in sorted_blocks:
        # 페이지가 바뀌거나 Y좌표가 크게 변하면 새 줄
        if block.page_num != current_page or abs(block.y0 - current_y) > 5:
            if current_line:
                line_text = " ".join(b.text for b in current_line)
                lines.append((line_text, current_page))
            current_line = [block]
            current_page = block.page_num
            current_y = block.y0
        else:
            current_line.append(block)

    # 마지막 줄
    if current_line:
        line_text = " ".join(b.text for b in current_line)
        lines.append((line_text, current_page))

    return lines


def group_by_structure(lines: List[Tuple[str, int]]) -> List[DocumentStructure]:
    """
    줄 단위 텍스트를 구조로 그룹화

    Args:
        lines: (text, page_num) 튜플 리스트

    Returns:
        DocumentStructure 리스트
    """
    structures = []
    current_article = None
    pending_content = []

    for text, page_num in lines:
        # 1. 조항 파싱 시도
        article = parse_article(text, page_num)
        if article:
            # 이전 조항 저장
            if current_article:
                if pending_content:
                    current_article.content += "\n" + "\n".join(pending_content)
                    pending_content = []
                structures.append(current_article)

            current_article = article
            continue

        # 2. 항/호/목 파싱 시도
        item_result = parse_item(text, page_num)
        if item_result:
            item, level = item_result

            if current_article:
                # 보류된 내용 먼저 조항에 추가
                if pending_content:
                    current_article.content += "\n" + "\n".join(pending_content)
                    pending_content = []

                # 항목 추가
                current_article.items.append(item)
            else:
                # 조항 없이 항목만 있는 경우 (드물지만)
                pending_content.append(text)
            continue

        # 3. 일반 텍스트 (보류)
        pending_content.append(text)

    # 마지막 조항 저장
    if current_article:
        if pending_content:
            current_article.content += "\n" + "\n".join(pending_content)
        structures.append(current_article)

    return structures


# =============================================================================
# 메인 API
# =============================================================================

def analyze_pdf_structure(pdf_path: Path) -> List[DocumentStructure]:
    """
    PDF 문서 구조 분석

    Args:
        pdf_path: PDF 파일 경로

    Returns:
        DocumentStructure 리스트 (조항 단위)
    """
    log.info(f"[STRUCTURE] Analyzing structure of {pdf_path.name}")

    # 1. 텍스트 블록 추출
    blocks = extract_text_blocks(pdf_path)
    if not blocks:
        log.warning(f"[STRUCTURE] No text blocks found in {pdf_path.name}")
        return []

    # 2. 줄 단위 병합
    lines = merge_text_blocks(blocks)
    log.info(f"[STRUCTURE] Merged into {len(lines)} lines")

    # 3. 구조 파싱
    structures = group_by_structure(lines)
    log.info(f"[STRUCTURE] Found {len(structures)} articles in {pdf_path.name}")

    # 통계 로깅
    total_items = sum(len(s.items) for s in structures)
    log.info(
        f"[STRUCTURE] Statistics: {len(structures)} articles, "
        f"{total_items} items"
    )

    return structures


def structure_to_simple_blocks(structures: List[DocumentStructure]) -> List[Tuple[int, str]]:
    """
    구조를 단순 (page_num, text) 블록으로 변환 (기존 파이프라인 호환용)

    Args:
        structures: DocumentStructure 리스트

    Returns:
        (page_num, text) 튜플 리스트
    """
    blocks = []

    for article in structures:
        # 조항 전체 텍스트 구성
        full_text = ""

        if article.full_title:
            full_text += article.full_title + "\n"

        if article.content:
            full_text += article.content + "\n"

        # 하위 항목들
        for item in article.items:
            item_text = f"{item.number}. {item.content}"
            full_text += item_text + "\n"

        blocks.append((article.page_num, full_text.strip()))

    return blocks
