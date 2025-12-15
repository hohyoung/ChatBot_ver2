"""
검색 결과 비결정성 디버깅 스크립트

동일한 쿼리로 여러 번 검색하여 결과가 달라지는지 확인합니다.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from app.vectorstore.store import get_collection, query_by_embedding
from app.services.embedding import embed_texts

def find_chunks_containing(keyword: str):
    """특정 키워드가 포함된 청크 찾기"""
    col = get_collection()
    res = col.get(include=["documents", "metadatas"])

    ids = res.get("ids", [])
    docs = res.get("documents", [])
    metas = res.get("metadatas", [])

    print(f"\n{'='*60}")
    print(f"키워드 '{keyword}' 포함 청크 검색")
    print(f"{'='*60}")

    found = []
    for i, (chunk_id, doc, meta) in enumerate(zip(ids, docs, metas)):
        if keyword in doc:
            found.append({
                "chunk_id": chunk_id,
                "content_preview": doc[:200],
                "doc_title": meta.get("doc_title", ""),
                "team_id": meta.get("team_id", "<없음>"),
            })

    print(f"총 {len(found)}개 청크에서 '{keyword}' 발견\n")
    for i, item in enumerate(found):
        print(f"[{i+1}] {item['chunk_id']}")
        print(f"    team_id: {item['team_id']}")
        print(f"    내용: {item['content_preview'][:100]}...")
        print()

    return found


def test_search_consistency(query: str, team_id: int = 1, n_runs: int = 5):
    """
    동일 쿼리로 여러 번 검색하여 결과 일관성 테스트
    """
    print(f"\n{'='*60}")
    print(f"검색 일관성 테스트: '{query}'")
    print(f"team_id={team_id}, 반복횟수={n_runs}")
    print(f"{'='*60}")

    # 쿼리 임베딩 생성 (매번 새로 생성)
    results_per_run = []

    for run in range(n_runs):
        print(f"\n--- Run {run+1}/{n_runs} ---")

        # 임베딩 생성
        embeddings = embed_texts([query])
        q_vec = embeddings[0]

        # 임베딩 해시 (처음 10개 값)
        emb_hash = tuple(round(v, 6) for v in q_vec[:10])
        print(f"임베딩 해시(처음10): {emb_hash}")

        # ChromaDB 검색
        where_filter = {
            "$and": [
                {"visibility": {"$in": ["org", "public"]}},
                {"team_id": {"$eq": str(team_id)}},
            ]
        }

        raw = query_by_embedding(
            q_vec,
            n_results=10,
            where=where_filter,
        )

        ids = raw.get("ids", [[]])[0]
        dists = raw.get("distances", [[]])[0]

        result_summary = [(cid, round(d, 6)) for cid, d in zip(ids, dists)]
        results_per_run.append(result_summary)

        print(f"결과 (상위 5개):")
        for j, (cid, dist) in enumerate(result_summary[:5]):
            print(f"  [{j+1}] {cid} (dist={dist})")

    # 결과 비교
    print(f"\n{'='*60}")
    print("결과 비교 분석")
    print(f"{'='*60}")

    # 모든 run에서 동일한 결과인지 확인
    first_result = results_per_run[0]
    all_same = all(r == first_result for r in results_per_run)

    if all_same:
        print("[OK] 모든 실행에서 동일한 결과!")
    else:
        print("[DIFF] 실행마다 결과가 다름!")

        # 어떤 부분이 다른지 분석
        for run_idx, result in enumerate(results_per_run):
            ids_only = [r[0] for r in result[:5]]
            print(f"  Run {run_idx+1}: {ids_only}")

        # 임베딩이 달라지는지 확인
        print("\n임베딩 변화 확인:")
        emb_hashes = []
        for run in range(3):
            embs = embed_texts([query])
            h = tuple(round(v, 6) for v in embs[0][:5])
            emb_hashes.append(h)
            print(f"  Run {run+1}: {h}")

        if len(set(emb_hashes)) > 1:
            print("[WARN] 임베딩이 매번 다르게 생성됨!")
        else:
            print("[OK] 임베딩은 일관됨 - ChromaDB HNSW 문제일 수 있음")


def analyze_all_chunks():
    """전체 청크 분석"""
    col = get_collection()
    res = col.get(include=["documents", "metadatas"])

    ids = res.get("ids", [])
    docs = res.get("documents", [])
    metas = res.get("metadatas", [])

    print(f"\n{'='*60}")
    print(f"전체 청크 분석 (총 {len(ids)}개)")
    print(f"{'='*60}")

    for i, (chunk_id, doc, meta) in enumerate(zip(ids, docs, metas)):
        print(f"\n[{i+1}] {chunk_id}")
        print(f"    team_id: {meta.get('team_id', '<없음>')}")
        print(f"    visibility: {meta.get('visibility', '<없음>')}")
        print(f"    doc_title: {meta.get('doc_title', '')[:50]}")
        print(f"    내용: {doc[:150]}...")


if __name__ == "__main__":
    print("=" * 60)
    print("검색 디버깅 시작")
    print("=" * 60)

    # 1. 수습 관련 청크 찾기
    find_chunks_containing("수습")

    # 2. 검색 일관성 테스트
    test_search_consistency(
        query="수습에 대한 질문이 있어. 기간은 어떻게 되고, 월급은 어떻게 받지?",
        team_id=1,
        n_runs=5
    )

    # 3. 단순 쿼리로도 테스트
    test_search_consistency(
        query="수습 기간",
        team_id=1,
        n_runs=3
    )
