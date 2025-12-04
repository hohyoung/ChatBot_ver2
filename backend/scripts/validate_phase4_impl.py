#!/usr/bin/env python3
"""
GAR Phase 4 구현 검증 스크립트 (경량)

OpenAI API 호출 없이 코드 구조만 검증합니다.

검증 항목:
1. LLMReranker 클래스 구조 확인
2. Redis 캐싱 메서드 존재 확인
3. 동적 배치 크기 메서드 확인
4. PerformanceMonitor 클래스 확인
5. 메트릭 수집 메서드 확인

실행 방법:
    cd backend
    python scripts/validate_phase4_impl.py
"""

import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.rag.reranker import LLMReranker
from app.services.performance_monitor import PerformanceMonitor, get_performance_monitor
from app.services.logging import get_logger

log = get_logger("validate_phase4")


def validate_reranker():
    """LLMReranker 클래스 구조 검증"""
    print("\n" + "=" * 80)
    print("검증 1: LLMReranker 클래스 구조")
    print("=" * 80)

    # 인스턴스 생성 (API 호출 없음)
    reranker = LLMReranker(use_cache=True, dynamic_batch=True)

    # 필수 속성 확인
    required_attrs = [
        'use_cache',
        'dynamic_batch',
        'cache_hits',
        'cache_misses',
        'llm_calls',
        'w_llm',
        'w_feedback',
        'w_tag',
        'w_similarity',
    ]

    for attr in required_attrs:
        if not hasattr(reranker, attr):
            print(f"[FAIL] 누락된 속성: {attr}")
            return False
        print(f"[PASS] 속성 확인: {attr}")

    # 필수 메서드 확인
    required_methods = [
        'get_metrics',
        '_generate_cache_key',
        '_get_optimal_batch_size',
        'rerank',
    ]

    for method in required_methods:
        if not hasattr(reranker, method):
            print(f"[FAIL] 누락된 메서드: {method}")
            return False
        print(f"[PASS] 메서드 확인: {method}")

    print("\n[PASS] LLMReranker 클래스 구조 검증 완료")
    return True


def validate_cache_key_generation():
    """캐시 키 생성 메서드 검증"""
    print("\n" + "=" * 80)
    print("검증 2: 캐시 키 생성 메서드")
    print("=" * 80)

    reranker = LLMReranker(use_cache=True)

    # 테스트 입력
    question = "연차는 몇 일인가요?"
    chunk_ids = ["chunk_1", "chunk_2", "chunk_3"]

    # 캐시 키 생성
    cache_key = reranker._generate_cache_key(question, chunk_ids)

    # 검증
    if not cache_key:
        print("[FAIL] 캐시 키 생성 실패")
        return False

    if not cache_key.startswith("rerank:"):
        print(f"[FAIL] 캐시 키 형식 오류: {cache_key}")
        return False

    print(f"[PASS] 캐시 키 생성 성공: {cache_key[:50]}...")

    # 동일 입력 → 동일 키 확인
    cache_key2 = reranker._generate_cache_key(question, chunk_ids)
    if cache_key != cache_key2:
        print("[FAIL] 동일 입력에 대한 캐시 키 불일치")
        return False

    print("[PASS] 캐시 키 일관성 확인 완료")

    # 다른 입력 → 다른 키 확인
    cache_key3 = reranker._generate_cache_key("다른 질문", chunk_ids)
    if cache_key == cache_key3:
        print("[FAIL] 다른 입력에 대한 캐시 키 중복")
        return False

    print("[PASS] 캐시 키 고유성 확인 완료")

    print("\n[PASS] 캐시 키 생성 메서드 검증 완료")
    return True


def validate_dynamic_batch_size():
    """동적 배치 크기 메서드 검증"""
    print("\n" + "=" * 80)
    print("검증 3: 동적 배치 크기 메서드")
    print("=" * 80)

    reranker = LLMReranker(dynamic_batch=True)

    # 테스트 케이스: (청크 수, 기대 배치 크기)
    test_cases = [
        (3, 3),   # ≤5 → 3
        (5, 3),   # ≤5 → 3
        (6, 5),   # 6-10 → 5
        (10, 5),  # 6-10 → 5
        (15, 7),  # 11-20 → 7
        (20, 7),  # 11-20 → 7
        (25, 10), # 21+ → 10
        (100, 10), # 21+ → 10
    ]

    all_passed = True
    for num_chunks, expected_batch in test_cases:
        actual_batch = reranker._get_optimal_batch_size(num_chunks)

        if actual_batch != expected_batch:
            print(
                f"[FAIL] 청크 수 {num_chunks}: "
                f"기대 배치 {expected_batch}, 실제 배치 {actual_batch}"
            )
            all_passed = False
        else:
            print(
                f"[PASS] 청크 수 {num_chunks:3d} → 배치 크기 {actual_batch}"
            )

    if not all_passed:
        print("\n[FAIL] 동적 배치 크기 검증 실패")
        return False

    print("\n[PASS] 동적 배치 크기 메서드 검증 완료")
    return True


def validate_metrics():
    """메트릭 수집 메서드 검증"""
    print("\n" + "=" * 80)
    print("검증 4: 메트릭 수집 메서드")
    print("=" * 80)

    reranker = LLMReranker()

    # 초기 메트릭 확인
    metrics = reranker.get_metrics()

    required_keys = [
        'cache_hits',
        'cache_misses',
        'cache_hit_rate',
        'llm_calls',
    ]

    for key in required_keys:
        if key not in metrics:
            print(f"[FAIL] 누락된 메트릭: {key}")
            return False
        print(f"[PASS] 메트릭 키 확인: {key} = {metrics[key]}")

    # 초기값 확인
    if metrics['cache_hits'] != 0:
        print(f"[FAIL] cache_hits 초기값 오류: {metrics['cache_hits']}")
        return False

    if metrics['cache_misses'] != 0:
        print(f"[FAIL] cache_misses 초기값 오류: {metrics['cache_misses']}")
        return False

    if metrics['llm_calls'] != 0:
        print(f"[FAIL] llm_calls 초기값 오류: {metrics['llm_calls']}")
        return False

    if metrics['cache_hit_rate'] != 0.0:
        print(f"[FAIL] cache_hit_rate 초기값 오류: {metrics['cache_hit_rate']}")
        return False

    print("[PASS] 초기 메트릭 값 확인 완료")

    print("\n[PASS] 메트릭 수집 메서드 검증 완료")
    return True


def validate_performance_monitor():
    """PerformanceMonitor 클래스 검증"""
    print("\n" + "=" * 80)
    print("검증 5: PerformanceMonitor 클래스")
    print("=" * 80)

    # 인스턴스 생성
    monitor = PerformanceMonitor(window_size=100)

    # 필수 속성 확인
    if not hasattr(monitor, 'requests'):
        print("[FAIL] requests 속성 누락")
        return False
    print("[PASS] 속성 확인: requests")

    if not hasattr(monitor, 'window_size'):
        print("[FAIL] window_size 속성 누락")
        return False
    print(f"[PASS] 속성 확인: window_size = {monitor.window_size}")

    # 필수 메서드 확인
    required_methods = [
        'record_request',
        'get_stats',
        'reset',
        'print_summary',
        '_estimate_llm_cost',
    ]

    for method in required_methods:
        if not hasattr(monitor, method):
            print(f"[FAIL] 누락된 메서드: {method}")
            return False
        print(f"[PASS] 메서드 확인: {method}")

    # 요청 기록 테스트
    monitor.record_request(
        latency_ms=1234.5,
        cache_hit=True,
        llm_calls=2,
    )

    if monitor.total_requests != 1:
        print(f"[FAIL] total_requests 업데이트 실패: {monitor.total_requests}")
        return False
    print("[PASS] 요청 기록 성공")

    # 통계 조회 테스트
    stats = monitor.get_stats()

    if stats['total_requests'] != 1:
        print(f"[FAIL] 통계 조회 실패: {stats['total_requests']}")
        return False
    print("[PASS] 통계 조회 성공")

    # 리셋 테스트
    monitor.reset()

    if monitor.total_requests != 0:
        print(f"[FAIL] 리셋 실패: {monitor.total_requests}")
        return False
    print("[PASS] 리셋 성공")

    print("\n[PASS] PerformanceMonitor 클래스 검증 완료")
    return True


def validate_singleton():
    """PerformanceMonitor 싱글톤 검증"""
    print("\n" + "=" * 80)
    print("검증 6: PerformanceMonitor 싱글톤")
    print("=" * 80)

    # 싱글톤 인스턴스 가져오기
    monitor1 = get_performance_monitor()
    monitor2 = get_performance_monitor()

    if monitor1 is not monitor2:
        print("[FAIL] 싱글톤 인스턴스 불일치")
        return False

    print(f"[PASS] 싱글톤 인스턴스 일치: id={id(monitor1)}")

    print("\n[PASS] 싱글톤 검증 완료")
    return True


def main():
    """모든 검증 실행"""
    print("\n" + "=" * 80)
    print("GAR Phase 4 구현 검증 시작 (경량)")
    print("=" * 80)

    tests = [
        ("LLMReranker 클래스 구조", validate_reranker),
        ("캐시 키 생성 메서드", validate_cache_key_generation),
        ("동적 배치 크기 메서드", validate_dynamic_batch_size),
        ("메트릭 수집 메서드", validate_metrics),
        ("PerformanceMonitor 클래스", validate_performance_monitor),
        ("PerformanceMonitor 싱글톤", validate_singleton),
    ]

    results = []

    for name, test_func in tests:
        try:
            success = test_func()
            results.append((name, success))
        except Exception as e:
            log.error(f"[FAIL] {name} 검증 중 오류 발생", exc_info=True)
            results.append((name, False))

    # 최종 결과
    print("\n" + "=" * 80)
    print("검증 결과 요약")
    print("=" * 80)

    passed = sum(1 for _, success in results if success)
    total = len(results)

    for name, success in results:
        status = "[PASS] 통과" if success else "[FAIL] 실패"
        print(f"{status}: {name}")

    print("\n" + "=" * 80)
    print(f"총 {passed}/{total} 검증 통과 ({passed/total*100:.1f}%)")
    print("=" * 80)

    if passed == total:
        print("\n[PASS] 모든 검증 통과! Phase 4 구현이 완료되었습니다.")
        return 0
    else:
        print(f"\n[WARN] {total - passed}개 검증 실패. 구현을 확인해주세요.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
