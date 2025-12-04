"""
PDF 구조 디버깅 스크립트
"""

import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "backend"))

import pdfplumber

test_file = project_root / "25년도 직원 인사평가 실시 안내.pdf"

with pdfplumber.open(test_file) as pdf:
    page = pdf.pages[0]

    print("=" * 60)
    print("PDF 페이지 분석")
    print("=" * 60)

    print(f"\n페이지 크기: {page.width} x {page.height}")

    # 선(lines) 분석
    lines = page.lines
    print(f"\n선(lines) 개수: {len(lines)}")
    if lines:
        print("처음 10개 선:")
        for i, line in enumerate(lines[:10]):
            print(f"  {i}: {line}")

    # 사각형(rects) 분석
    rects = page.rects
    print(f"\n사각형(rects) 개수: {len(rects)}")
    if rects:
        print("처음 10개 사각형:")
        for i, rect in enumerate(rects[:10]):
            print(f"  {i}: {rect}")

    # 곡선(curves) 분석
    curves = page.curves
    print(f"\n곡선(curves) 개수: {len(curves)}")

    # 표 찾기 - 여러 전략 시도
    print("\n" + "=" * 60)
    print("표 감지 전략별 결과")
    print("=" * 60)

    strategies = [
        {"vertical_strategy": "lines", "horizontal_strategy": "lines"},
        {"vertical_strategy": "lines_strict", "horizontal_strategy": "lines_strict"},
        {"vertical_strategy": "text", "horizontal_strategy": "text"},
        {"vertical_strategy": "explicit", "horizontal_strategy": "explicit"},
    ]

    for strat in strategies:
        try:
            tables = page.find_tables(strat)
            print(f"\n{strat}:")
            print(f"  발견된 표: {len(tables)}개")
            for i, t in enumerate(tables):
                area = (t.bbox[2] - t.bbox[0]) * (t.bbox[3] - t.bbox[1])
                ratio = area / (page.width * page.height)
                print(f"  표 {i}: bbox={t.bbox}, 면적비율={ratio:.2%}")
        except Exception as e:
            print(f"\n{strat}: 오류 - {e}")
