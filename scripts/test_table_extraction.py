"""
표 추출 테스트 스크립트

인사평가 PDF에서 표를 추출하여 결과를 확인합니다.
"""

import sys
import os
from pathlib import Path

# Windows 콘솔 인코딩 설정
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

# 프로젝트 루트를 path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "backend"))

# .env 로드
from dotenv import load_dotenv
load_dotenv(project_root / "backend" / ".env")


def test_pdfplumber_extraction():
    """pdfplumber를 사용한 표 추출 테스트"""
    from app.ingest.parsers.table_extractor import (
        extract_tables_from_pdf,
        HAS_PDFPLUMBER,
    )

    if not HAS_PDFPLUMBER:
        print("❌ pdfplumber가 설치되지 않았습니다.")
        print("   pip install pdfplumber 로 설치하세요.")
        return

    # 테스트 파일 경로
    test_file = project_root / "25년도 직원 인사평가 실시 안내.pdf"

    if not test_file.exists():
        print(f"❌ 테스트 파일을 찾을 수 없습니다: {test_file}")
        return

    print(f"📄 테스트 파일: {test_file.name}")
    print("=" * 60)

    # 표 추출
    tables = extract_tables_from_pdf(test_file)

    print(f"\n✅ 추출된 표 개수: {len(tables)}")
    print("=" * 60)

    for i, table in enumerate(tables, 1):
        print(f"\n--- 표 #{i} ---")
        print(f"페이지: {table.page_num}")
        print(f"행 수: {table.metadata.get('row_count', 0)}")
        print(f"열 수: {table.metadata.get('col_count', 0)}")
        print(f"신뢰도: {table.confidence:.2f}")
        print(f"섹션 포함: {table.metadata.get('has_sections', False)}")
        print(f"섹션 수: {table.metadata.get('section_count', 0)}")
        print(f"\n[마크다운 출력]")
        print(table.markdown)
        print("-" * 40)

    return tables


def test_vision_extraction():
    """Vision API를 사용한 표 이미지 추출 테스트"""
    import asyncio
    from app.ingest.parsers.image_extractor import extract_images_from_pdf
    from app.ingest.parsers.vision_processor import process_table_image

    # 테스트 파일 경로
    test_file = project_root / "25년도 직원 인사평가 실시 안내.pdf"

    if not test_file.exists():
        print(f"❌ 테스트 파일을 찾을 수 없습니다: {test_file}")
        return

    print(f"📄 테스트 파일: {test_file.name}")
    print("=" * 60)

    # 이미지 추출
    images = extract_images_from_pdf(test_file)
    table_images = [img for img in images if img.image_type == "table"]

    print(f"\n✅ 추출된 이미지: 총 {len(images)}개, 표 {len(table_images)}개")

    if not table_images:
        print("❌ 표 이미지가 없습니다.")
        return

    # 첫 번째 표 이미지만 Vision API로 처리
    print(f"\n🔍 첫 번째 표 이미지 Vision API 처리 중...")

    async def process():
        img = table_images[0]
        result = await process_table_image(img)
        return result

    markdown = asyncio.run(process())

    if markdown:
        print(f"\n[Vision API 마크다운 출력]")
        print(markdown)
    else:
        print("❌ Vision API 처리 실패")


def test_hybrid_extraction():
    """하이브리드 방식 테스트 (pdfplumber + Vision fallback)"""
    import asyncio
    from app.ingest.parsers.image_extractor import extract_images_from_pdf
    from app.ingest.parsers.vision_processor import process_table_image
    from app.ingest.parsers.table_extractor import (
        extract_tables_from_pdf,
        HAS_PDFPLUMBER,
    )

    test_file = project_root / "25년도 직원 인사평가 실시 안내.pdf"

    if not test_file.exists():
        print(f"[오류] 테스트 파일을 찾을 수 없습니다: {test_file}")
        return

    print(f"[파일] {test_file.name}")
    print("=" * 60)

    # 1. pdfplumber로 표 추출
    print("\n[1단계] pdfplumber 표 추출")
    print("-" * 40)

    if HAS_PDFPLUMBER:
        pdfplumber_tables = extract_tables_from_pdf(test_file)
        print(f"추출된 표: {len(pdfplumber_tables)}개")

        for i, table in enumerate(pdfplumber_tables, 1):
            print(f"\n표 #{i}:")
            print(f"  페이지: {table.page_num}")
            print(f"  행/열: {table.metadata.get('row_count', 0)} x {table.metadata.get('col_count', 0)}")
            print(f"  신뢰도: {table.confidence:.2f}")
            print(f"  미리보기: {table.markdown[:200]}...")
    else:
        pdfplumber_tables = []
        print("pdfplumber 미설치")

    # 2. 이미지에서 표 감지
    print("\n[2단계] 이미지 기반 표 감지")
    print("-" * 40)

    images = extract_images_from_pdf(test_file)
    table_images = [img for img in images if img.image_type == "table"]
    print(f"전체 이미지: {len(images)}개")
    print(f"표 이미지: {len(table_images)}개")

    for img in table_images:
        print(f"  - 페이지 {img.page_num}: {img.width}x{img.height}px")

    # 3. Vision API로 표 이미지 처리 (비용 발생 주의)
    print("\n[3단계] Vision API 처리")
    print("-" * 40)

    if table_images and input("Vision API 테스트 실행? (비용 발생) [y/N]: ").lower() == 'y':
        async def process_first_table():
            img = table_images[0]
            print(f"처리 중: 페이지 {img.page_num}의 표 이미지...")
            result = await process_table_image(img)
            return result

        markdown = asyncio.run(process_first_table())

        if markdown:
            print(f"\n[Vision API 결과]")
            print(markdown)
        else:
            print("[오류] Vision API 처리 실패")
    else:
        print("Vision API 테스트 건너뜀")

    # 4. 요약
    print("\n" + "=" * 60)
    print("[요약]")
    print(f"  pdfplumber 추출 표: {len(pdfplumber_tables)}개")
    print(f"  Vision 대상 이미지: {len(table_images)}개")
    print("=" * 60)


def compare_results():
    """pdfplumber vs Vision API 결과 비교"""
    print("\n" + "=" * 60)
    print("pdfplumber vs Vision API 비교")
    print("=" * 60)

    print("\n[1] pdfplumber 결과:")
    print("-" * 40)
    pdfplumber_tables = test_pdfplumber_extraction()

    print("\n[2] Vision API 결과:")
    print("-" * 40)
    # Vision은 비용이 발생하므로 기본적으로 비활성화
    # test_vision_extraction()
    print("(Vision API 테스트는 비용 발생으로 주석 처리됨)")
    print("테스트하려면 스크립트에서 test_vision_extraction() 주석 해제")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="표 추출 테스트")
    parser.add_argument("--mode", choices=["pdfplumber", "vision", "hybrid", "compare"],
                       default="pdfplumber", help="테스트 모드")

    args = parser.parse_args()

    if args.mode == "pdfplumber":
        test_pdfplumber_extraction()
    elif args.mode == "vision":
        test_vision_extraction()
    elif args.mode == "hybrid":
        test_hybrid_extraction()
    else:
        compare_results()
