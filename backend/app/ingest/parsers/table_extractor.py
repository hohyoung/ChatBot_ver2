"""
PDF 표 추출 모듈 (pdfplumber 사용)

PDF 문서에서 표를 구조적으로 추출합니다:
- pdfplumber를 사용하여 표 셀 구조 직접 분석
- 복합 표 (여러 섹션) 처리
- 중첩 표 (표 안의 표) 인식
- Vision API 폴백 지원
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
from io import BytesIO

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    pdfplumber = None
    HAS_PDFPLUMBER = False

try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    fitz = None
    HAS_PYMUPDF = False

from app.services.logging import get_logger

log = get_logger("app.ingest.parsers.table_extractor")


@dataclass
class ExtractedTable:
    """추출된 표 데이터"""
    page_num: int                           # 페이지 번호 (1-based), 병합 시 시작 페이지
    table_index: int                        # 페이지 내 표 인덱스 (0-based)
    bbox: Tuple[float, float, float, float] # (x0, y0, x1, y1)
    rows: List[List[str]]                   # 2D 셀 데이터
    markdown: str                           # 마크다운 변환 결과
    section_title: Optional[str] = None     # 표 섹션 제목 (감지된 경우)
    confidence: float = 1.0                 # 추출 신뢰도 (0.0 ~ 1.0)
    metadata: Dict[str, Any] = field(default_factory=dict)
    # 원본 이미지 데이터 (P0-2 개선)
    image_data: Optional[bytes] = None      # 표 영역 이미지 바이너리
    image_format: str = "png"               # 이미지 포맷
    # 연속 페이지 표 병합 정보
    page_end: Optional[int] = None          # 끝 페이지 (병합된 경우)
    is_merged: bool = False                 # 병합된 표 여부
    merged_from: List[int] = field(default_factory=list)  # 병합 원본 페이지 목록


def _clean_cell(cell: Any) -> str:
    """셀 값 정제"""
    if cell is None:
        return ""
    text = str(cell).strip()
    # 줄바꿈을 공백으로 대체
    text = " ".join(text.split())
    return text


def _table_to_markdown(rows: List[List[str]], section_title: Optional[str] = None) -> str:
    """
    2D 테이블을 마크다운 표로 변환

    Args:
        rows: 2D 셀 데이터
        section_title: 섹션 제목 (있으면 ### 헤더 추가)

    Returns:
        마크다운 문자열
    """
    if not rows or len(rows) < 1:
        return ""

    lines = []

    # 섹션 제목
    if section_title:
        lines.append(f"### {section_title}")
        lines.append("")

    # 헤더 행
    header = rows[0]
    header_line = "| " + " | ".join(_clean_cell(c) for c in header) + " |"
    lines.append(header_line)

    # 구분선
    separator = "|" + "|".join("---" for _ in header) + "|"
    lines.append(separator)

    # 데이터 행
    for row in rows[1:]:
        # 열 수 맞추기
        while len(row) < len(header):
            row.append("")
        row_line = "| " + " | ".join(_clean_cell(c) for c in row[:len(header)]) + " |"
        lines.append(row_line)

    return "\n".join(lines)


def _detect_section_titles(rows: List[List[str]]) -> List[Tuple[int, str]]:
    """
    표 내부의 섹션 구분 행 감지

    섹션 구분 특징:
    - 첫 번째 셀에만 텍스트가 있고 나머지가 비어있거나
    - 모든 셀이 병합된 것처럼 동일한 값을 가짐

    Returns:
        [(row_index, section_title), ...]
    """
    sections = []

    for i, row in enumerate(rows):
        if i == 0:  # 헤더는 스킵
            continue

        non_empty = [c for c in row if _clean_cell(c)]

        # 첫 셀만 값이 있고 나머지가 비어있는 경우
        if len(non_empty) == 1 and _clean_cell(row[0]):
            sections.append((i, _clean_cell(row[0])))
        # 모든 셀이 동일한 값인 경우 (병합된 행)
        elif len(set(_clean_cell(c) for c in row if _clean_cell(c))) == 1 and non_empty:
            sections.append((i, non_empty[0]))

    return sections


def _split_table_by_sections(
    rows: List[List[str]],
    sections: List[Tuple[int, str]]
) -> List[Tuple[str, List[List[str]]]]:
    """
    섹션별로 표 분할

    Returns:
        [(section_title, rows), ...]
    """
    if not sections:
        return [(None, rows)]

    result = []
    header = rows[0]

    # 첫 섹션 이전 데이터
    if sections[0][0] > 1:
        pre_section_rows = [header] + rows[1:sections[0][0]]
        result.append((None, pre_section_rows))

    # 각 섹션별 데이터
    for i, (row_idx, title) in enumerate(sections):
        # 다음 섹션 시작점 또는 끝
        next_idx = sections[i + 1][0] if i + 1 < len(sections) else len(rows)

        # 섹션 제목 행 다음부터 다음 섹션 전까지
        section_rows = [header] + rows[row_idx + 1:next_idx]

        if len(section_rows) > 1:  # 데이터가 있는 경우만
            result.append((title, section_rows))

    return result


def _calculate_confidence(table_data: List[List[str]]) -> float:
    """
    표 추출 신뢰도 계산

    낮은 신뢰도 요인:
    - 빈 셀이 너무 많음
    - 행별 열 수가 불일치
    - 데이터 행이 너무 적음
    """
    if not table_data or len(table_data) < 2:
        return 0.0

    confidence = 1.0

    # 1. 빈 셀 비율 체크
    total_cells = sum(len(row) for row in table_data)
    empty_cells = sum(1 for row in table_data for cell in row if not _clean_cell(cell))
    empty_ratio = empty_cells / total_cells if total_cells > 0 else 1.0

    if empty_ratio > 0.5:
        confidence -= 0.3
    elif empty_ratio > 0.3:
        confidence -= 0.1

    # 2. 열 수 일관성 체크
    col_counts = [len(row) for row in table_data]
    if len(set(col_counts)) > 1:
        confidence -= 0.2

    # 3. 데이터 행 수 체크
    if len(table_data) < 3:
        confidence -= 0.1

    return max(0.0, confidence)


def extract_tables_from_pdf(pdf_path: Path) -> List[ExtractedTable]:
    """
    PDF에서 모든 표 추출 (pdfplumber 사용)

    Args:
        pdf_path: PDF 파일 경로

    Returns:
        추출된 표 리스트
    """
    if not HAS_PDFPLUMBER:
        log.warning("[TABLE] pdfplumber not available, skipping table extraction")
        return []

    extracted_tables: List[ExtractedTable] = []

    try:
        with pdfplumber.open(pdf_path) as pdf:
            log.info(f"[TABLE] Opened PDF: {pdf_path.name}, pages={len(pdf.pages)}")

            for page_num, page in enumerate(pdf.pages, start=1):
                page_area = page.width * page.height
                valid_tables = []

                # 여러 전략으로 표 감지 시도
                strategies = [
                    # 1) 선 기반 (테두리가 있는 표)
                    {
                        "vertical_strategy": "lines",
                        "horizontal_strategy": "lines",
                        "snap_tolerance": 5,
                        "join_tolerance": 5,
                    },
                    # 2) 텍스트 기반 (선이 없는 표)
                    {
                        "vertical_strategy": "text",
                        "horizontal_strategy": "text",
                        "snap_tolerance": 5,
                        "join_tolerance": 5,
                        "min_words_vertical": 3,
                        "min_words_horizontal": 3,
                    },
                ]

                for strategy in strategies:
                    if valid_tables:  # 이미 유효한 표를 찾았으면 중단
                        break

                    try:
                        detected_tables = page.find_tables(strategy)

                        for t in detected_tables:
                            table_area = (t.bbox[2] - t.bbox[0]) * (t.bbox[3] - t.bbox[1])
                            area_ratio = table_area / page_area

                            # 페이지의 3% ~ 70% 사이인 표만 유효 (범위 확대)
                            if 0.03 < area_ratio < 0.70:
                                valid_tables.append(t)
                                log.debug(
                                    f"[TABLE] Valid table found: page={page_num}, "
                                    f"strategy={strategy.get('vertical_strategy')}, "
                                    f"bbox={t.bbox}, area_ratio={area_ratio:.2%}"
                                )
                            else:
                                log.debug(
                                    f"[TABLE] Skipping table: page={page_num}, "
                                    f"area_ratio={area_ratio:.2%} (out of range)"
                                )
                    except Exception as e:
                        log.debug(f"[TABLE] Strategy {strategy} failed: {e}")
                        continue

                # 유효한 표가 없으면 다음 페이지
                if not valid_tables:
                    log.debug(f"[TABLE] No valid tables on page {page_num}")
                    continue

                log.debug(f"[TABLE] Page {page_num}: found {len(valid_tables)} valid tables")

                for table_idx, table_obj in enumerate(valid_tables):
                    table_data = table_obj.extract()

                    if not table_data or len(table_data) < 2:
                        continue

                    # 신뢰도 계산
                    confidence = _calculate_confidence(table_data)

                    if confidence < 0.3:
                        log.debug(
                            f"[TABLE] Skipping low-confidence table: "
                            f"page={page_num}, index={table_idx}, confidence={confidence:.2f}"
                        )
                        continue

                    # 섹션 감지 및 분할
                    sections = _detect_section_titles(table_data)

                    if sections:
                        # 복합 표: 섹션별로 분할하여 마크다운 생성
                        split_tables = _split_table_by_sections(table_data, sections)
                        markdown_parts = []

                        for section_title, section_rows in split_tables:
                            md = _table_to_markdown(section_rows, section_title)
                            if md:
                                markdown_parts.append(md)

                        markdown = "\n\n".join(markdown_parts)
                        section_title = "복합 표"
                    else:
                        # 단일 표
                        markdown = _table_to_markdown(table_data)
                        section_title = None

                    # 표 영역 (바운딩 박스) - find_tables에서 제공하는 실제 bbox 사용
                    bbox = table_obj.bbox

                    extracted_table = ExtractedTable(
                        page_num=page_num,
                        table_index=table_idx,
                        bbox=bbox,
                        rows=table_data,
                        markdown=markdown,
                        section_title=section_title,
                        confidence=confidence,
                        metadata={
                            "row_count": len(table_data),
                            "col_count": len(table_data[0]) if table_data else 0,
                            "has_sections": len(sections) > 0,
                            "section_count": len(sections),
                        }
                    )

                    extracted_tables.append(extracted_table)
                    log.info(
                        f"[TABLE] Extracted table: page={page_num}, index={table_idx}, "
                        f"rows={len(table_data)}, cols={len(table_data[0]) if table_data else 0}, "
                        f"confidence={confidence:.2f}, sections={len(sections)}"
                    )

        log.info(f"[TABLE] Extracted {len(extracted_tables)} tables from {pdf_path.name}")

    except Exception as e:
        log.error(f"[TABLE] Failed to extract tables from {pdf_path}: {e}")

    return extracted_tables


def merge_tables_with_text(
    text_chunks: List[Tuple[int, str]],
    tables: List[ExtractedTable],
) -> List[Tuple[int, str, Optional[str]]]:
    """
    텍스트 청크와 표를 페이지 순서대로 병합

    Args:
        text_chunks: [(page_num, text), ...]
        tables: 추출된 표 리스트

    Returns:
        [(page_num, content, content_type), ...]
        content_type: "text" | "table"
    """
    result = []

    # 페이지별로 그룹화
    page_tables = {}
    for table in tables:
        if table.page_num not in page_tables:
            page_tables[table.page_num] = []
        page_tables[table.page_num].append(table)

    # 텍스트 청크 추가
    for page_num, text in text_chunks:
        result.append((page_num, text, "text"))

    # 표 추가 (각 페이지의 텍스트 뒤에)
    for page_num, page_table_list in page_tables.items():
        for table in page_table_list:
            result.append((page_num, table.markdown, "table"))

    # 페이지 번호로 정렬
    result.sort(key=lambda x: (x[0], 0 if x[2] == "text" else 1))

    return result


# ===========================================================================
# 방안 A: 같은 페이지 내 인접 표 병합 (Adjacent Table Merging)
# ===========================================================================

def _is_adjacent_table(
    upper_table: ExtractedTable,
    lower_table: ExtractedTable,
    y_threshold: float = 50.0,
    x_overlap_ratio: float = 0.3,
) -> bool:
    """
    두 표가 세로로 인접한지 판단 (완화된 조건)

    조건:
    1. 같은 페이지
    2. Y 좌표가 가까움 (upper의 하단과 lower의 상단 간격이 threshold 이하)
    3. X 좌표가 겹침 (가로 위치가 유사)

    Args:
        upper_table: 위쪽 표
        lower_table: 아래쪽 표
        y_threshold: Y 간격 임계값 (points, 기본 50 - 완화)
        x_overlap_ratio: X 겹침 비율 (기본 30% - 완화)

    Returns:
        인접 여부
    """
    # 1. 같은 페이지 확인
    if upper_table.page_num != lower_table.page_num:
        return False

    # 2. Y 좌표 확인: upper가 위에 있어야 함
    upper_bottom = upper_table.bbox[3]  # y1
    lower_top = lower_table.bbox[1]     # y0

    # upper가 lower보다 아래에 있으면 순서가 잘못됨
    if upper_bottom > lower_top + y_threshold:
        return False

    # Y 간격 확인 (음수도 허용 - 표가 살짝 겹칠 수 있음)
    y_gap = lower_top - upper_bottom
    if y_gap > y_threshold:
        log.debug(f"[ADJACENT] Y gap too large: {y_gap:.1f} > {y_threshold}")
        return False

    # 3. X 좌표 겹침 확인
    upper_x0, upper_x1 = upper_table.bbox[0], upper_table.bbox[2]
    lower_x0, lower_x1 = lower_table.bbox[0], lower_table.bbox[2]

    # 겹치는 X 범위 계산
    overlap_x0 = max(upper_x0, lower_x0)
    overlap_x1 = min(upper_x1, lower_x1)
    overlap_width = max(0, overlap_x1 - overlap_x0)

    # 더 좁은 표 기준으로 겹침 비율 계산
    upper_width = upper_x1 - upper_x0
    lower_width = lower_x1 - lower_x0
    min_width = min(upper_width, lower_width)

    if min_width <= 0:
        return False

    overlap_ratio = overlap_width / min_width
    if overlap_ratio < x_overlap_ratio:
        log.debug(f"[ADJACENT] X overlap too small: {overlap_ratio:.2f} < {x_overlap_ratio}")
        return False

    log.debug(
        f"[ADJACENT] Tables are adjacent: y_gap={y_gap:.1f}, x_overlap={overlap_ratio:.2f}"
    )
    return True


def _merge_adjacent_tables(
    upper_table: ExtractedTable,
    lower_table: ExtractedTable,
) -> ExtractedTable:
    """
    세로로 인접한 두 표를 하나로 병합

    Args:
        upper_table: 위쪽 표
        lower_table: 아래쪽 표

    Returns:
        병합된 ExtractedTable
    """
    # 열 구조 비교
    upper_cols = len(upper_table.rows[0]) if upper_table.rows else 0
    lower_cols = len(lower_table.rows[0]) if lower_table.rows else 0

    # 행 병합: 열 수가 같으면 헤더 스킵 검토, 다르면 그대로 병합
    merged_rows = list(upper_table.rows)

    if upper_cols == lower_cols:
        # 열 수가 같으면 lower의 첫 행이 헤더인지 확인
        upper_header = [_clean_cell(c).lower() for c in upper_table.rows[0]] if upper_table.rows else []
        lower_header = [_clean_cell(c).lower() for c in lower_table.rows[0]] if lower_table.rows else []

        if upper_header == lower_header:
            # 헤더 동일 -> 스킵
            merged_rows.extend(lower_table.rows[1:])
        else:
            # 헤더 다름 -> lower가 별도 섹션일 수 있음, 빈 행 추가 후 병합
            merged_rows.append([""] * upper_cols)  # 구분용 빈 행
            merged_rows.extend(lower_table.rows)
    else:
        # 열 수가 다름 -> 복잡한 중첩 표, 그대로 병합 (열 수 맞춤)
        max_cols = max(upper_cols, lower_cols)
        # 기존 행들 열 수 맞춤
        for i, row in enumerate(merged_rows):
            while len(row) < max_cols:
                row.append("")
            merged_rows[i] = row[:max_cols]
        # lower 행 추가
        for row in lower_table.rows:
            new_row = list(row)
            while len(new_row) < max_cols:
                new_row.append("")
            merged_rows.append(new_row[:max_cols])

    # 마크다운 재생성
    merged_markdown = _table_to_markdown(merged_rows, upper_table.section_title)

    # bbox 병합: 두 표를 감싸는 영역
    merged_bbox = (
        min(upper_table.bbox[0], lower_table.bbox[0]),  # x0
        upper_table.bbox[1],  # y0 (위쪽 표 상단)
        max(upper_table.bbox[2], lower_table.bbox[2]),  # x1
        lower_table.bbox[3],  # y1 (아래쪽 표 하단)
    )

    # 신뢰도: 낮은 쪽 기준 (보수적)
    merged_confidence = min(upper_table.confidence, lower_table.confidence)

    merged_table = ExtractedTable(
        page_num=upper_table.page_num,
        table_index=upper_table.table_index,
        bbox=merged_bbox,
        rows=merged_rows,
        markdown=merged_markdown,
        section_title=upper_table.section_title or lower_table.section_title,
        confidence=merged_confidence,
        metadata={
            "row_count": len(merged_rows),
            "col_count": len(merged_rows[0]) if merged_rows else 0,
            "is_adjacent_merged": True,
            "merged_table_count": 2,
        },
        image_data=None,
        image_format="png",
        page_end=upper_table.page_num,
        is_merged=True,
        merged_from=[upper_table.page_num],
    )

    log.info(
        f"[ADJACENT] Merged adjacent tables on page {upper_table.page_num}: "
        f"rows={len(merged_rows)}, confidence={merged_confidence:.2f}"
    )

    return merged_table


def merge_adjacent_tables_on_page(
    tables: List[ExtractedTable],
    y_threshold: float = 80.0,
    x_overlap_ratio: float = 0.2,
) -> List[ExtractedTable]:
    """
    같은 페이지에서 세로로 인접한 표들을 병합 (방안 A)

    pdfplumber가 하나의 복잡한 표를 여러 개로 분리한 경우를 복구합니다.

    주의: 복합 표(중첩 구조)의 경우 매우 완화된 조건으로 병합해야 합니다.

    Args:
        tables: 추출된 표 리스트
        y_threshold: Y 간격 임계값 (points, 기본 80 - 매우 완화)
        x_overlap_ratio: X 겹침 비율 임계값 (기본 20% - 매우 완화)

    Returns:
        병합 처리된 표 리스트
    """
    if not tables or len(tables) < 2:
        return tables

    # 페이지별로 그룹화
    page_tables: Dict[int, List[ExtractedTable]] = {}
    for table in tables:
        if table.page_num not in page_tables:
            page_tables[table.page_num] = []
        page_tables[table.page_num].append(table)

    merged_all: List[ExtractedTable] = []

    for page_num, page_table_list in page_tables.items():
        if len(page_table_list) < 2:
            merged_all.extend(page_table_list)
            continue

        # Y 좌표(상단) 기준 정렬
        sorted_tables = sorted(page_table_list, key=lambda t: t.bbox[1])

        merged_on_page: List[ExtractedTable] = []
        current_table = sorted_tables[0]

        for next_table in sorted_tables[1:]:
            if _is_adjacent_table(current_table, next_table, y_threshold, x_overlap_ratio):
                # 인접 -> 병합
                current_table = _merge_adjacent_tables(current_table, next_table)
                # 연쇄 병합 메타데이터 업데이트
                current_table.metadata["merged_table_count"] = \
                    current_table.metadata.get("merged_table_count", 1) + 1
            else:
                # 인접 아님 -> 현재 표 확정, 다음으로
                merged_on_page.append(current_table)
                current_table = next_table

        # 마지막 표 추가
        merged_on_page.append(current_table)
        merged_all.extend(merged_on_page)

        adj_merged_count = sum(
            1 for t in merged_on_page if t.metadata.get("is_adjacent_merged")
        )
        if adj_merged_count > 0:
            log.info(
                f"[ADJACENT] Page {page_num}: {len(page_table_list)} tables -> "
                f"{len(merged_on_page)} tables ({adj_merged_count} merged)"
            )

    total_adj_merged = sum(1 for t in merged_all if t.metadata.get("is_adjacent_merged"))
    log.info(
        f"[ADJACENT] Total: {len(tables)} tables -> {len(merged_all)} tables "
        f"({total_adj_merged} adjacent-merged)"
    )

    return merged_all


def is_complex_table(table: ExtractedTable) -> bool:
    """
    표가 복잡한 구조인지 판단 (Vision API 폴백 필요 여부)

    복잡한 표 조건:
    1. 신뢰도가 낮음 (< 0.7)
    2. 빈 셀이 너무 많음 (> 30%)
    3. 행별 열 수가 불일치
    4. 인접 병합된 표

    Returns:
        복잡한 표 여부
    """
    # 1. 신뢰도 체크
    if table.confidence < 0.7:
        log.debug(f"[COMPLEX] Low confidence: {table.confidence:.2f}")
        return True

    # 2. 인접 병합된 표
    if table.metadata.get("is_adjacent_merged"):
        log.debug("[COMPLEX] Adjacent-merged table")
        return True

    # 3. 빈 셀 비율 체크
    if table.rows:
        total_cells = sum(len(row) for row in table.rows)
        empty_cells = sum(1 for row in table.rows for cell in row if not _clean_cell(cell))
        empty_ratio = empty_cells / total_cells if total_cells > 0 else 0

        if empty_ratio > 0.3:
            log.debug(f"[COMPLEX] High empty ratio: {empty_ratio:.2f}")
            return True

    # 4. 열 수 불일치 체크
    if table.rows and len(table.rows) > 1:
        col_counts = [len(row) for row in table.rows]
        if len(set(col_counts)) > 1:
            log.debug(f"[COMPLEX] Inconsistent columns: {set(col_counts)}")
            return True

    return False


def capture_full_table_region(
    pdf_path: Path,
    page_num: int,
    bbox: Tuple[float, float, float, float],
    dpi: int = 200,
    padding: int = 15,
) -> Optional[bytes]:
    """
    방안 C: 복잡한 표의 전체 영역을 고해상도 이미지로 캡처

    pdfplumber가 분리한 인접 표들의 병합된 bbox 영역 전체를 캡처합니다.

    Args:
        pdf_path: PDF 파일 경로
        page_num: 페이지 번호 (1-based)
        bbox: 표 영역 (x0, y0, x1, y1)
        dpi: 이미지 해상도 (기본 200, 높은 해상도)
        padding: 표 주변 여백 (pixels)

    Returns:
        PNG 이미지 바이너리, 실패 시 None
    """
    if not HAS_PYMUPDF:
        log.warning("[TABLE] PyMuPDF not available")
        return None

    try:
        doc = fitz.open(pdf_path)
        page_idx = page_num - 1

        if page_idx < 0 or page_idx >= len(doc):
            log.warning(f"[TABLE] Invalid page number: {page_num}")
            doc.close()
            return None

        page = doc[page_idx]

        # bbox에 패딩 적용
        x0, y0, x1, y1 = bbox
        padding_pts = padding * 72 / dpi
        x0 = max(0, x0 - padding_pts)
        y0 = max(0, y0 - padding_pts)
        x1 = min(page.rect.width, x1 + padding_pts)
        y1 = min(page.rect.height, y1 + padding_pts)

        clip_rect = fitz.Rect(x0, y0, x1, y1)

        # 고해상도 캡처
        zoom = dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=matrix, clip=clip_rect)

        image_data = pix.tobytes("png")
        doc.close()

        log.info(
            f"[TABLE] Captured full region: page={page_num}, "
            f"bbox=({x0:.0f},{y0:.0f},{x1:.0f},{y1:.0f}), "
            f"size={len(image_data)} bytes"
        )
        return image_data

    except Exception as e:
        log.error(f"[TABLE] Failed to capture full region: {e}")
        return None


def get_table_summary(tables: List[ExtractedTable]) -> Dict[str, Any]:
    """표 추출 요약 정보"""
    if not tables:
        return {"total": 0}

    return {
        "total": len(tables),
        "by_page": {t.page_num: sum(1 for tt in tables if tt.page_num == t.page_num) for t in tables},
        "avg_confidence": sum(t.confidence for t in tables) / len(tables),
        "total_rows": sum(len(t.rows) for t in tables),
        "with_sections": sum(1 for t in tables if t.metadata.get("has_sections")),
    }


def capture_table_images(
    pdf_path: Path,
    tables: List[ExtractedTable],
    dpi: int = 150,
    padding: int = 10,
) -> List[ExtractedTable]:
    """
    pdfplumber로 추출한 표의 bbox 영역을 PyMuPDF로 이미지 캡처.

    Args:
        pdf_path: PDF 파일 경로
        tables: pdfplumber로 추출한 ExtractedTable 리스트
        dpi: 이미지 해상도 (기본 150)
        padding: 표 주변 여백 (픽셀)

    Returns:
        이미지 데이터가 추가된 ExtractedTable 리스트
    """
    if not HAS_PYMUPDF:
        log.warning("[TABLE] PyMuPDF not available, cannot capture table images")
        return tables

    if not tables:
        return tables

    try:
        doc = fitz.open(pdf_path)

        for table in tables:
            try:
                # pdfplumber는 1-based, fitz는 0-based 페이지
                page_idx = table.page_num - 1
                if page_idx < 0 or page_idx >= len(doc):
                    log.warning(f"[TABLE] Invalid page number: {table.page_num}")
                    continue

                page = doc[page_idx]

                # pdfplumber bbox를 fitz Rect로 변환
                # pdfplumber: (x0, y0, x1, y1) in points
                # fitz: Rect(x0, y0, x1, y1) in points
                x0, y0, x1, y1 = table.bbox

                # 여백 추가 (포인트 단위로 변환)
                padding_pts = padding * 72 / dpi
                x0 = max(0, x0 - padding_pts)
                y0 = max(0, y0 - padding_pts)
                x1 = min(page.rect.width, x1 + padding_pts)
                y1 = min(page.rect.height, y1 + padding_pts)

                clip_rect = fitz.Rect(x0, y0, x1, y1)

                # DPI 기반 줌 계산 (72 DPI가 기본)
                zoom = dpi / 72.0
                matrix = fitz.Matrix(zoom, zoom)

                # 클리핑 영역 이미지 생성
                pix = page.get_pixmap(matrix=matrix, clip=clip_rect)

                # PNG 바이트로 변환
                image_bytes = pix.tobytes("png")

                # ExtractedTable에 이미지 데이터 추가
                table.image_data = image_bytes
                table.image_format = "png"

                log.debug(
                    f"[TABLE] Captured table image: page={table.page_num}, "
                    f"index={table.table_index}, size={len(image_bytes)} bytes"
                )

            except Exception as e:
                log.warning(
                    f"[TABLE] Failed to capture table image: "
                    f"page={table.page_num}, index={table.table_index}, error={e}"
                )
                continue

        doc.close()

        captured_count = sum(1 for t in tables if t.image_data is not None)
        log.info(f"[TABLE] Captured {captured_count}/{len(tables)} table images from {pdf_path.name}")

    except Exception as e:
        log.error(f"[TABLE] Failed to capture table images from {pdf_path}: {e}")

    return tables


# ===========================================================================
# 연속 페이지 표 병합 (Multi-page Table Merging)
# ===========================================================================

def _get_column_signature(rows: List[List[str]]) -> Tuple[int, List[str]]:
    """
    표의 열 구조 시그니처 추출

    Returns:
        (열 개수, 헤더 행 정규화)
    """
    if not rows:
        return (0, [])

    header = rows[0]
    col_count = len(header)
    # 헤더를 소문자로 정규화 (공백 제거)
    normalized_header = [_clean_cell(c).lower().replace(" ", "") for c in header]

    return (col_count, normalized_header)


def _is_continuation_table(
    prev_table: ExtractedTable,
    curr_table: ExtractedTable,
    page_height: float,
    threshold_bottom: float = 0.85,  # 이전 표가 페이지 하단 85% 이하에 있어야 함
    threshold_top: float = 0.20,     # 현재 표가 페이지 상단 20% 이내에 있어야 함
) -> bool:
    """
    두 표가 연속 페이지의 이어지는 표인지 판단

    조건:
    1. 연속된 페이지 (curr = prev + 1)
    2. 열 구조가 동일하거나 유사
    3. 이전 표가 페이지 하단에 위치
    4. 현재 표가 페이지 상단에 위치
    5. 현재 표의 첫 행이 헤더가 아님 (데이터 행으로 시작)

    Args:
        prev_table: 이전 페이지 표
        curr_table: 현재 페이지 표
        page_height: 페이지 높이 (points)
        threshold_bottom: 이전 표 하단 위치 임계값
        threshold_top: 현재 표 상단 위치 임계값

    Returns:
        연속 표 여부
    """
    # 1. 연속 페이지 확인
    if curr_table.page_num != prev_table.page_num + 1:
        return False

    # 2. 열 구조 비교
    prev_sig = _get_column_signature(prev_table.rows)
    curr_sig = _get_column_signature(curr_table.rows)

    # 열 개수가 다르면 연속 표 아님
    if prev_sig[0] != curr_sig[0]:
        log.debug(
            f"[TABLE_MERGE] Column count mismatch: prev={prev_sig[0]}, curr={curr_sig[0]}"
        )
        return False

    # 3. 이전 표가 페이지 하단에 있는지 확인
    # bbox = (x0, y0, x1, y1), y1이 표 하단
    prev_bottom_ratio = prev_table.bbox[3] / page_height if page_height > 0 else 0
    if prev_bottom_ratio < threshold_bottom:
        log.debug(
            f"[TABLE_MERGE] Previous table not at bottom: ratio={prev_bottom_ratio:.2f} < {threshold_bottom}"
        )
        return False

    # 4. 현재 표가 페이지 상단에 있는지 확인
    # y0이 표 상단
    curr_top_ratio = curr_table.bbox[1] / page_height if page_height > 0 else 1
    if curr_top_ratio > threshold_top:
        log.debug(
            f"[TABLE_MERGE] Current table not at top: ratio={curr_top_ratio:.2f} > {threshold_top}"
        )
        return False

    # 5. 헤더 유사성 체크 (선택적)
    # 현재 표의 첫 행이 이전 표의 헤더와 동일하면 -> 헤더 반복 (연속 표)
    # 현재 표의 첫 행이 데이터처럼 보이면 -> 연속 표
    if prev_sig[1] == curr_sig[1]:
        # 헤더가 동일 -> 헤더 반복된 연속 표 (첫 행 제거 필요)
        log.debug(f"[TABLE_MERGE] Header repeated, marking as continuation")
        return True

    # 헤더가 다르면 -> 현재 표 첫 행이 데이터일 가능성
    # 데이터인지 판단: 헤더에 일반적인 헤더 키워드가 없으면 데이터로 간주
    header_keywords = ["번호", "항목", "이름", "내용", "구분", "비고", "날짜", "금액",
                       "no", "name", "item", "date", "amount", "type", "description"]
    first_row_text = " ".join(curr_sig[1]).lower()
    has_header_keyword = any(kw in first_row_text for kw in header_keywords)

    if not has_header_keyword:
        # 헤더 키워드 없음 -> 데이터 행으로 시작하는 연속 표
        log.debug(f"[TABLE_MERGE] First row looks like data, marking as continuation")
        return True

    log.debug(f"[TABLE_MERGE] Not a continuation table")
    return False


def _merge_two_tables(
    prev_table: ExtractedTable,
    curr_table: ExtractedTable,
    skip_header: bool = True,
) -> ExtractedTable:
    """
    두 연속 표를 하나로 병합

    Args:
        prev_table: 이전 표 (기준)
        curr_table: 현재 표 (병합 대상)
        skip_header: True면 현재 표의 헤더 행 제거

    Returns:
        병합된 ExtractedTable
    """
    # 행 병합
    merged_rows = list(prev_table.rows)  # 이전 표 전체

    # 현재 표의 헤더가 이전 표와 동일하면 스킵
    prev_header = _get_column_signature(prev_table.rows)[1]
    curr_header = _get_column_signature(curr_table.rows)[1]

    start_idx = 1 if (skip_header and prev_header == curr_header) else 0
    merged_rows.extend(curr_table.rows[start_idx:])

    # 마크다운 재생성
    merged_markdown = _table_to_markdown(merged_rows, prev_table.section_title)

    # 병합 메타데이터
    merged_from = list(prev_table.merged_from) if prev_table.merged_from else [prev_table.page_num]
    merged_from.append(curr_table.page_num)

    # 신뢰도: 평균
    avg_confidence = (prev_table.confidence + curr_table.confidence) / 2

    merged_table = ExtractedTable(
        page_num=prev_table.page_num,  # 시작 페이지
        table_index=prev_table.table_index,
        bbox=prev_table.bbox,  # 첫 페이지 bbox 유지
        rows=merged_rows,
        markdown=merged_markdown,
        section_title=prev_table.section_title,
        confidence=avg_confidence,
        metadata={
            **prev_table.metadata,
            "row_count": len(merged_rows),
            "is_merged": True,
            "merged_pages": merged_from,
        },
        image_data=None,  # 이미지는 나중에 별도 캡처
        image_format="png",
        page_end=curr_table.page_num,
        is_merged=True,
        merged_from=merged_from,
    )

    log.info(
        f"[TABLE_MERGE] Merged tables: pages {merged_from}, "
        f"rows={len(merged_rows)}, confidence={avg_confidence:.2f}"
    )

    return merged_table


def merge_continuation_tables(
    tables: List[ExtractedTable],
    page_heights: Dict[int, float],
) -> List[ExtractedTable]:
    """
    연속 페이지에 걸친 표들을 병합

    Args:
        tables: 추출된 표 리스트 (페이지 순)
        page_heights: 페이지별 높이 {page_num: height}

    Returns:
        병합 처리된 표 리스트
    """
    if not tables or len(tables) < 2:
        return tables

    # 페이지 번호로 정렬
    sorted_tables = sorted(tables, key=lambda t: (t.page_num, t.table_index))

    merged_tables: List[ExtractedTable] = []
    current_table: Optional[ExtractedTable] = None

    for table in sorted_tables:
        if current_table is None:
            current_table = table
            continue

        page_height = page_heights.get(current_table.page_num, 792)  # 기본 Letter 크기

        # 연속 표인지 확인
        if _is_continuation_table(current_table, table, page_height):
            # 병합
            current_table = _merge_two_tables(current_table, table)
            log.debug(
                f"[TABLE_MERGE] Merged page {table.page_num} into table starting at page {current_table.page_num}"
            )
        else:
            # 연속 아님 -> 현재 표 확정, 새 표 시작
            merged_tables.append(current_table)
            current_table = table

    # 마지막 표 추가
    if current_table is not None:
        merged_tables.append(current_table)

    merged_count = sum(1 for t in merged_tables if t.is_merged)
    log.info(
        f"[TABLE_MERGE] Result: {len(tables)} tables -> {len(merged_tables)} tables "
        f"({merged_count} merged)"
    )

    return merged_tables


def capture_merged_table_images(
    pdf_path: Path,
    tables: List[ExtractedTable],
    dpi: int = 150,
    padding: int = 10,
) -> List[ExtractedTable]:
    """
    병합된 표의 이미지 캡처 (여러 페이지 결합)

    병합된 표의 경우 각 페이지별로 캡처 후 세로로 결합합니다.

    Args:
        pdf_path: PDF 파일 경로
        tables: 표 리스트 (병합 포함)
        dpi: 이미지 해상도
        padding: 표 주변 여백

    Returns:
        이미지가 추가된 표 리스트
    """
    if not HAS_PYMUPDF:
        log.warning("[TABLE] PyMuPDF not available, cannot capture table images")
        return tables

    try:
        from PIL import Image
    except ImportError:
        log.warning("[TABLE] Pillow not available, cannot merge images")
        # 단일 페이지 이미지만 캡처
        return capture_table_images(pdf_path, tables, dpi, padding)

    try:
        doc = fitz.open(pdf_path)

        for table in tables:
            try:
                if not table.is_merged:
                    # 단일 페이지 표: 기존 로직
                    page_idx = table.page_num - 1
                    if page_idx < 0 or page_idx >= len(doc):
                        continue

                    page = doc[page_idx]
                    x0, y0, x1, y1 = table.bbox
                    padding_pts = padding * 72 / dpi
                    x0 = max(0, x0 - padding_pts)
                    y0 = max(0, y0 - padding_pts)
                    x1 = min(page.rect.width, x1 + padding_pts)
                    y1 = min(page.rect.height, y1 + padding_pts)

                    clip_rect = fitz.Rect(x0, y0, x1, y1)
                    zoom = dpi / 72.0
                    matrix = fitz.Matrix(zoom, zoom)
                    pix = page.get_pixmap(matrix=matrix, clip=clip_rect)

                    table.image_data = pix.tobytes("png")
                    table.image_format = "png"

                else:
                    # 병합된 표 처리
                    merged_pages = table.merged_from or [table.page_num]

                    # 인접 병합 (같은 페이지 내 병합): 병합된 bbox로 단순 캡처
                    is_same_page_merge = (
                        table.metadata.get("is_adjacent_merged") or
                        len(set(merged_pages)) == 1 or
                        (table.page_end and table.page_num == table.page_end)
                    )

                    if is_same_page_merge:
                        # 같은 페이지 내 인접 병합: 병합된 bbox 사용
                        page_idx = table.page_num - 1
                        if page_idx < 0 or page_idx >= len(doc):
                            continue

                        page = doc[page_idx]
                        x0, y0, x1, y1 = table.bbox  # 병합된 bbox

                        padding_pts = padding * 72 / dpi
                        x0 = max(0, x0 - padding_pts)
                        y0 = max(0, y0 - padding_pts)
                        x1 = min(page.rect.width, x1 + padding_pts)
                        y1 = min(page.rect.height, y1 + padding_pts)

                        clip_rect = fitz.Rect(x0, y0, x1, y1)
                        zoom = dpi / 72.0
                        matrix = fitz.Matrix(zoom, zoom)
                        pix = page.get_pixmap(matrix=matrix, clip=clip_rect)

                        table.image_data = pix.tobytes("png")
                        table.image_format = "png"

                        log.debug(
                            f"[TABLE] Captured adjacent-merged table image: page={table.page_num}, "
                            f"bbox=({x0:.0f},{y0:.0f},{x1:.0f},{y1:.0f}), "
                            f"size={len(table.image_data)} bytes"
                        )
                    else:
                        # 여러 페이지에 걸친 병합: 각 페이지 캡처 후 결합
                        page_images = []

                        for i, page_num in enumerate(merged_pages):
                            page_idx = page_num - 1
                            if page_idx < 0 or page_idx >= len(doc):
                                continue

                            page = doc[page_idx]

                            # 첫 페이지: 원래 bbox의 y0부터 페이지 끝까지
                            # 중간/마지막 페이지: 페이지 시작부터 페이지 끝(또는 표 끝)까지
                            if i == 0:
                                # 첫 페이지: 원래 표 시작부터
                                x0, y0, x1, y1 = table.bbox
                                y1 = page.rect.height  # 페이지 끝까지
                            elif i == len(merged_pages) - 1:
                                # 마지막 페이지: 페이지 시작부터 표 끝까지
                                x0 = table.bbox[0]
                                x1 = table.bbox[2]
                                y0 = 0
                                y1 = page.rect.height * 0.5  # 상단 50% 정도로 추정
                            else:
                                # 중간 페이지: 전체 페이지
                                x0 = table.bbox[0]
                                x1 = table.bbox[2]
                                y0 = 0
                                y1 = page.rect.height

                            padding_pts = padding * 72 / dpi
                            x0 = max(0, x0 - padding_pts)
                            y0 = max(0, y0 - padding_pts)
                            x1 = min(page.rect.width, x1 + padding_pts)
                            y1 = min(page.rect.height, y1 + padding_pts)

                            clip_rect = fitz.Rect(x0, y0, x1, y1)
                            zoom = dpi / 72.0
                            matrix = fitz.Matrix(zoom, zoom)
                            pix = page.get_pixmap(matrix=matrix, clip=clip_rect)

                            # PIL Image로 변환
                            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                            page_images.append(img)

                        if page_images:
                            # 이미지 세로 결합
                            total_height = sum(img.height for img in page_images)
                            max_width = max(img.width for img in page_images)

                            combined = Image.new("RGB", (max_width, total_height), "white")
                            y_offset = 0
                            for img in page_images:
                                combined.paste(img, (0, y_offset))
                                y_offset += img.height

                            # PNG 바이트로 변환
                            buffer = BytesIO()
                            combined.save(buffer, format="PNG")
                            table.image_data = buffer.getvalue()
                            table.image_format = "png"

                            log.debug(
                                f"[TABLE] Captured multi-page merged table image: pages={merged_pages}, "
                                f"size={len(table.image_data)} bytes"
                            )

            except Exception as e:
                log.warning(
                    f"[TABLE] Failed to capture table image: "
                    f"page={table.page_num}, error={e}"
                )
                continue

        doc.close()

        captured_count = sum(1 for t in tables if t.image_data is not None)
        log.info(f"[TABLE] Captured {captured_count}/{len(tables)} table images")

    except Exception as e:
        log.error(f"[TABLE] Failed to capture table images: {e}")

    return tables
