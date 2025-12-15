# -*- coding: utf-8 -*-
"""
전체 청크 내용 확인 스크립트
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from app.vectorstore.store import get_collection

def analyze_all_chunks():
    """전체 청크 분석"""
    col = get_collection()
    res = col.get(include=["documents", "metadatas"])

    ids = res.get("ids", [])
    docs = res.get("documents", [])
    metas = res.get("metadatas", [])

    print("=" * 60)
    print(f"Total chunks: {len(ids)}")
    print("=" * 60)

    for i, (chunk_id, doc, meta) in enumerate(zip(ids, docs, metas)):
        print(f"\n[{i+1}] {chunk_id}")
        print(f"    team_id: {meta.get('team_id', '<none>')}")
        print(f"    visibility: {meta.get('visibility', '<none>')}")
        print(f"    doc_title: {meta.get('doc_title', '')[:50]}")
        print(f"    content ({len(doc)} chars):")
        # 처음 300자만 출력
        preview = doc[:300].replace('\n', ' ')
        print(f"    {preview}...")

def search_keywords():
    """여러 키워드로 검색"""
    col = get_collection()
    res = col.get(include=["documents", "metadatas"])

    ids = res.get("ids", [])
    docs = res.get("documents", [])

    keywords = ["수습", "시용", "trial", "probation", "신입", "입사", "채용", "임금", "급여", "월급"]

    print("\n" + "=" * 60)
    print("Keyword search in chunks")
    print("=" * 60)

    for kw in keywords:
        count = sum(1 for doc in docs if kw in doc)
        print(f"  '{kw}': {count} chunks")

        if count > 0 and count <= 3:
            # 해당 청크 내용 일부 출력
            for i, doc in enumerate(docs):
                if kw in doc:
                    idx = doc.find(kw)
                    context = doc[max(0, idx-50):idx+100]
                    print(f"    -> chunk {ids[i]}: ...{context}...")

if __name__ == "__main__":
    analyze_all_chunks()
    search_keywords()
