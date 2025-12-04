# backend/app/services/performance_monitor.py
"""
성능 모니터링 유틸리티 - GAR Phase 4

GAR 파이프라인의 성능 메트릭을 수집하고 집계합니다.

메트릭:
- 응답 시간 (p50, p90, p99)
- 캐시 적중률
- LLM API 호출 횟수
- 단계별 소요 시간

사용법:
    from app.services.performance_monitor import PerformanceMonitor

    monitor = PerformanceMonitor()
    monitor.record_request(
        latency_ms=1234.5,
        cache_hit=True,
        llm_calls=2,
        metrics={...}
    )

    # 통계 조회
    stats = monitor.get_stats()
"""

import time
from collections import deque
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.services.logging import get_logger

log = get_logger("app.services.performance_monitor")


@dataclass
class RequestMetrics:
    """개별 요청 메트릭"""

    timestamp: float = field(default_factory=time.time)
    latency_ms: float = 0.0
    intent_ms: float = 0.0
    doc_discovery_ms: float = 0.0
    query_decomposition_ms: float = 0.0
    tagging_ms: float = 0.0
    retrieval_ms: float = 0.0
    reranking_ms: float = 0.0
    generation_ms: float = 0.0
    cache_hit: bool = False
    llm_calls: int = 0


class PerformanceMonitor:
    """
    GAR 파이프라인 성능 모니터

    Features:
    - 최근 N개 요청 메트릭 저장 (메모리 효율)
    - 통계 집계 (평균, p50, p90, p99)
    - 캐시 적중률 추적
    - LLM 비용 추정
    """

    def __init__(self, window_size: int = 1000):
        """
        Args:
            window_size: 저장할 최대 요청 수 (기본: 1000)
        """
        self.window_size = window_size
        self.requests = deque(maxlen=window_size)

        # 집계 통계
        self.total_requests = 0
        self.total_cache_hits = 0
        self.total_llm_calls = 0

        log.info(f"[PERF-MONITOR] Initialized (window_size={window_size})")

    def record_request(
        self,
        latency_ms: float,
        cache_hit: bool = False,
        llm_calls: int = 0,
        metrics: Optional[Dict[str, Any]] = None,
    ):
        """
        요청 메트릭 기록

        Args:
            latency_ms: 전체 응답 시간 (ms)
            cache_hit: 캐시 적중 여부
            llm_calls: LLM API 호출 횟수
            metrics: 추가 메트릭 딕셔너리 (optional)
        """
        request = RequestMetrics(
            latency_ms=latency_ms,
            cache_hit=cache_hit,
            llm_calls=llm_calls,
        )

        # 추가 메트릭 설정
        if metrics:
            for key, value in metrics.items():
                if hasattr(request, key):
                    setattr(request, key, value)

        self.requests.append(request)

        # 집계 통계 업데이트
        self.total_requests += 1
        if cache_hit:
            self.total_cache_hits += 1
        self.total_llm_calls += llm_calls

        log.debug(
            f"[PERF-MONITOR] Recorded request: "
            f"latency={latency_ms:.1f}ms, "
            f"cache_hit={cache_hit}, "
            f"llm_calls={llm_calls}"
        )

    def get_stats(self, period_seconds: Optional[int] = None) -> Dict[str, Any]:
        """
        통계 조회

        Args:
            period_seconds: 집계 기간 (초), None이면 전체

        Returns:
            통계 딕셔너리
        """
        # 기간 필터링
        if period_seconds:
            cutoff_time = time.time() - period_seconds
            filtered = [
                r for r in self.requests if r.timestamp >= cutoff_time
            ]
        else:
            filtered = list(self.requests)

        if not filtered:
            return {
                "total_requests": 0,
                "period_seconds": period_seconds,
                "message": "No data available",
            }

        # 레이턴시 통계
        latencies = sorted([r.latency_ms for r in filtered])
        n = len(latencies)

        p50_idx = int(n * 0.50)
        p90_idx = int(n * 0.90)
        p99_idx = int(n * 0.99)

        # 캐시 통계
        cache_hits = sum(1 for r in filtered if r.cache_hit)
        cache_hit_rate = cache_hits / n if n > 0 else 0.0

        # LLM 통계
        total_llm = sum(r.llm_calls for r in filtered)
        avg_llm_per_request = total_llm / n if n > 0 else 0.0

        # 단계별 평균
        avg_intent = sum(r.intent_ms for r in filtered) / n if n > 0 else 0.0
        avg_doc_discovery = (
            sum(r.doc_discovery_ms for r in filtered) / n if n > 0 else 0.0
        )
        avg_query_decomp = (
            sum(r.query_decomposition_ms for r in filtered) / n
            if n > 0
            else 0.0
        )
        avg_tagging = sum(r.tagging_ms for r in filtered) / n if n > 0 else 0.0
        avg_retrieval = (
            sum(r.retrieval_ms for r in filtered) / n if n > 0 else 0.0
        )
        avg_reranking = (
            sum(r.reranking_ms for r in filtered) / n if n > 0 else 0.0
        )
        avg_generation = (
            sum(r.generation_ms for r in filtered) / n if n > 0 else 0.0
        )

        return {
            # 기본 정보
            "total_requests": n,
            "period_seconds": period_seconds,
            "window_size": self.window_size,
            # 레이턴시
            "latency": {
                "mean_ms": sum(latencies) / n if n > 0 else 0.0,
                "p50_ms": latencies[p50_idx] if n > 0 else 0.0,
                "p90_ms": latencies[p90_idx] if n > 0 else 0.0,
                "p99_ms": latencies[p99_idx] if n > 0 else 0.0,
                "min_ms": latencies[0] if n > 0 else 0.0,
                "max_ms": latencies[-1] if n > 0 else 0.0,
            },
            # 캐시
            "cache": {
                "hits": cache_hits,
                "misses": n - cache_hits,
                "hit_rate": cache_hit_rate,
            },
            # LLM
            "llm": {
                "total_calls": total_llm,
                "avg_per_request": avg_llm_per_request,
                "estimated_cost_usd": self._estimate_llm_cost(total_llm),
            },
            # 단계별 평균
            "stages": {
                "intent_ms": avg_intent,
                "doc_discovery_ms": avg_doc_discovery,
                "query_decomposition_ms": avg_query_decomp,
                "tagging_ms": avg_tagging,
                "retrieval_ms": avg_retrieval,
                "reranking_ms": avg_reranking,
                "generation_ms": avg_generation,
            },
        }

    def _estimate_llm_cost(self, total_calls: int) -> float:
        """
        LLM 비용 추정

        Args:
            total_calls: 총 LLM 호출 횟수

        Returns:
            추정 비용 (USD)

        Note:
            GPT-4o 기준: ~$0.005/1K input tokens, ~$0.015/1K output tokens
            평균 입력: 2000 tokens, 평균 출력: 500 tokens
            평균 비용 = (2K * 0.005 + 0.5K * 0.015) = $0.0175/call
        """
        AVG_COST_PER_CALL = 0.0175  # USD
        return total_calls * AVG_COST_PER_CALL

    def reset(self):
        """통계 초기화"""
        self.requests.clear()
        self.total_requests = 0
        self.total_cache_hits = 0
        self.total_llm_calls = 0
        log.info("[PERF-MONITOR] Statistics reset")

    def print_summary(self, period_seconds: Optional[int] = None):
        """
        통계 요약 출력 (로깅)

        Args:
            period_seconds: 집계 기간 (초), None이면 전체
        """
        stats = self.get_stats(period_seconds)

        if stats["total_requests"] == 0:
            log.info("[PERF-MONITOR] No data available")
            return

        log.info(
            "\n"
            "=" * 80 + "\n"
            f"성능 모니터링 요약 (최근 {stats['total_requests']}개 요청)\n"
            "=" * 80 + "\n"
            f"레이턴시:\n"
            f"  평균: {stats['latency']['mean_ms']:.1f} ms\n"
            f"  p50:  {stats['latency']['p50_ms']:.1f} ms\n"
            f"  p90:  {stats['latency']['p90_ms']:.1f} ms\n"
            f"  p99:  {stats['latency']['p99_ms']:.1f} ms\n"
            f"  범위: {stats['latency']['min_ms']:.1f} ~ {stats['latency']['max_ms']:.1f} ms\n\n"
            f"캐시:\n"
            f"  적중률: {stats['cache']['hit_rate']*100:.1f}%\n"
            f"  적중:   {stats['cache']['hits']}\n"
            f"  미스:   {stats['cache']['misses']}\n\n"
            f"LLM:\n"
            f"  총 호출: {stats['llm']['total_calls']}\n"
            f"  평균 호출/요청: {stats['llm']['avg_per_request']:.2f}\n"
            f"  추정 비용: ${stats['llm']['estimated_cost_usd']:.3f}\n\n"
            f"단계별 평균:\n"
            f"  Intent 분류:   {stats['stages']['intent_ms']:.1f} ms\n"
            f"  문서 인덱스:   {stats['stages']['doc_discovery_ms']:.1f} ms\n"
            f"  쿼리 분해:     {stats['stages']['query_decomposition_ms']:.1f} ms\n"
            f"  태깅:         {stats['stages']['tagging_ms']:.1f} ms\n"
            f"  검색:         {stats['stages']['retrieval_ms']:.1f} ms\n"
            f"  리랭킹:       {stats['stages']['reranking_ms']:.1f} ms\n"
            f"  생성:         {stats['stages']['generation_ms']:.1f} ms\n"
            "=" * 80
        )


# 전역 싱글톤
_global_monitor: Optional[PerformanceMonitor] = None


def get_performance_monitor() -> PerformanceMonitor:
    """
    전역 성능 모니터 인스턴스 반환

    Returns:
        PerformanceMonitor 싱글톤
    """
    global _global_monitor

    if _global_monitor is None:
        _global_monitor = PerformanceMonitor(window_size=1000)

    return _global_monitor
