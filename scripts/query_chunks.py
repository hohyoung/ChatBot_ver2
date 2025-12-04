#!/usr/bin/env python3
"""
특정 문서의 청크 조회 스크립트

사용 예)
  python scripts/query_chunks.py "25년도 직원 인사평가 실시 안내"
  python scripts/query_chunks.py "25년도 직원 인사평가 실시 안내" --output temp.txt
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 경로 설정
ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    import chromadb
except ImportError:
    print("[ERR] chromadb 미설치")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="특정 문서의 청크 조회")
    parser.add_argument("doc_title", help="문서 제목")
    parser.add_argument("--output", "-o", help="출력 파일 경로 (없으면 stdout)")
    args = parser.parse_args()

    # ChromaDB 연결
    chroma_path = BACKEND_DIR / "data" / "chroma"
    client = chromadb.PersistentClient(path=str(chroma_path))

    try:
        collection = client.get_collection("knowledge_base")
    except Exception as e:
        print(f"[ERR] 컬렉션 조회 실패: {e}")
        sys.exit(1)

    # 문서 청크 조회
    results = collection.get(
        where={"doc_title": args.doc_title},
        include=["documents", "metadatas"]
    )

    if not results["ids"]:
        print(f"[WARN] '{args.doc_title}' 문서를 찾을 수 없습니다.")
        sys.exit(1)

    # 출력 생성
    output_lines = []
    output_lines.append(f"문서: {args.doc_title}")
    output_lines.append(f"총 청크 수: {len(results['ids'])}")
    output_lines.append("=" * 80)

    for i, (chunk_id, content, meta) in enumerate(zip(
        results["ids"], results["documents"], results["metadatas"]
    )):
        output_lines.append(f"\n[청크 {i+1}] ID: {chunk_id}")
        output_lines.append(f"페이지: {meta.get('page_start', '?')} ~ {meta.get('page_end', '?')}")
        output_lines.append(f"태그: {meta.get('tags', '')}")
        output_lines.append("-" * 40)
        output_lines.append(content)
        output_lines.append("=" * 80)

    output_text = "\n".join(output_lines)

    # 출력
    if args.output:
        output_path = ROOT_DIR / args.output
        output_path.write_text(output_text, encoding="utf-8")
        print(f"[OK] {output_path} 에 저장됨 ({len(results['ids'])}개 청크)")
    else:
        print(output_text)


if __name__ == "__main__":
    main()
