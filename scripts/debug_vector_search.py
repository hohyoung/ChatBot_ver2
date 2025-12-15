# -*- coding: utf-8 -*-
"""
벡터 검색 결과 상세 분석 스크립트
왜 청크 0005가 상위에 안 올라오는지 확인
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from app.vectorstore.store import get_collection, query_by_embedding
from app.services.embedding import embed_texts

def analyze_search_ranking():
    """검색 결과에서 각 청크의 거리 분석"""
    col = get_collection()

    # 쿼리 임베딩 생성
    query = "수습에 대한 질문이 있어. 기간은 어떻게 되고, 월급은 어떻게 받지?"
    embeddings = embed_texts([query])
    q_vec = embeddings[0]

    # 필터 설정
    where_filter = {
        "$and": [
            {"visibility": {"$in": ["org", "public"]}},
            {"team_id": {"$eq": "1"}},
        ]
    }

    # 전체 23개 청크 모두 검색 (n_results=30)
    raw = col.query(
        query_embeddings=[q_vec],
        n_results=30,
        where=where_filter,
        include=["documents", "metadatas", "distances"],
    )

    ids = raw.get("ids", [[]])[0]
    docs = raw.get("documents", [[]])[0]
    metas = raw.get("metadatas", [[]])[0]
    dists = raw.get("distances", [[]])[0]

    print("=" * 70)
    print(f"Query: {query}")
    print("=" * 70)
    print(f"Total results: {len(ids)}")
    print()

    # 청크 0005의 순위 찾기
    target_chunk = "doc_ee060aba2b14_0005"
    target_rank = None

    for i, (cid, doc, meta, dist) in enumerate(zip(ids, docs, metas, dists)):
        # 유사도 계산 (distance -> similarity)
        similarity = 1.0 - (dist / 2.0)

        has_keyword = "수습" in doc

        marker = ""
        if cid == target_chunk:
            target_rank = i + 1
            marker = " <-- TARGET (contains 수습 규정)"
        elif has_keyword:
            marker = " [contains 수습]"

        print(f"[{i+1:2d}] {cid}")
        print(f"     distance={dist:.6f}, similarity={similarity:.4f}{marker}")
        print(f"     content: {doc[:80]}...")
        print()

    print("=" * 70)
    if target_rank:
        print(f"TARGET chunk (0005) rank: {target_rank}")
    else:
        print("TARGET chunk (0005) NOT FOUND in results!")
    print("=" * 70)


def compare_chunk_embeddings():
    """청크 0005와 쿼리의 임베딩 유사도 직접 계산"""
    col = get_collection()

    # 청크 0005 내용 가져오기
    target_id = "doc_ee060aba2b14_0005"
    res = col.get(ids=[target_id], include=["documents", "embeddings"])

    if not res.get("ids"):
        print("Target chunk not found!")
        return

    chunk_content = res["documents"][0]
    chunk_embedding = res["embeddings"][0] if res.get("embeddings") else None

    print("=" * 70)
    print("Chunk 0005 content:")
    print("=" * 70)
    print(chunk_content[:500])
    print("..." if len(chunk_content) > 500 else "")
    print()

    # 쿼리 임베딩
    query = "수습에 대한 질문이 있어. 기간은 어떻게 되고, 월급은 어떻게 받지?"
    query_embedding = embed_texts([query])[0]

    # 다양한 쿼리로 유사도 비교
    test_queries = [
        "수습에 대한 질문이 있어. 기간은 어떻게 되고, 월급은 어떻게 받지?",
        "수습 기간 규정",
        "수습 급여",
        "신규채용자 수습기간",
        "수습 3개월",
        "제14조 수습",
    ]

    print("=" * 70)
    print("Query-to-chunk similarity analysis (cosine)")
    print("=" * 70)

    if chunk_embedding:
        import numpy as np

        chunk_vec = np.array(chunk_embedding)

        for q in test_queries:
            q_vec = np.array(embed_texts([q])[0])

            # 코사인 유사도 계산
            cosine_sim = np.dot(chunk_vec, q_vec) / (np.linalg.norm(chunk_vec) * np.linalg.norm(q_vec))

            # ChromaDB cosine distance = 1 - cosine_similarity (but range 0~2)
            # Actually ChromaDB uses: distance = 1 - cosine_similarity when cosine_similarity >= 0
            # So similarity = 1 - distance/2 when distance is in range [0, 2]
            chroma_dist = 1 - cosine_sim  # approximate

            print(f"Query: '{q[:50]}'")
            print(f"  cosine_similarity: {cosine_sim:.6f}")
            print(f"  approx_chroma_dist: {chroma_dist:.6f}")
            print()
    else:
        print("No embedding stored for chunk - cannot compute similarity")


if __name__ == "__main__":
    analyze_search_ranking()
    print("\n\n")
    compare_chunk_embeddings()
