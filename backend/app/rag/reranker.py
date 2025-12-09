# backend/app/rag/reranker.py
"""
LLM-based Reranker - GAR Phase 3 + Phase 4 최적화

정확도 극대화를 위한 LLM 기반 청크 재랭킹.

전략:
1. LLM 관련성 평가 (0.0~1.0 점수)
2. 피드백 점수 통합 (fb_pos, fb_neg)
3. 유사도 점수 통합
4. 최종 점수 = w1*LLM점수 + w2*피드백점수 + w3*유사도점수

Phase 4 최적화:
- Redis 캐싱 (LLM 평가 결과)
- 동적 배치 크기 조정
- 상세 로깅

목표:
- 정확도 ≥85% (수동 평가 200건)
- 기존 RAG 대비 +15%p 이상
- Top-5 정확도 ≥95%
- 캐시 적중률 >40%
"""

from __future__ import annotations

import asyncio
import json
import hashlib
from typing import List, Optional
from pydantic import BaseModel, Field

from app.services.openai_client import get_async_client
from app.services.logging import get_logger
from app.services.redis_client import get_redis_client, is_redis_available
from app.models.schemas import ScoredChunk
from app.services import debug_logger as dbg

log = get_logger("app.rag.reranker")

# 리랭킹 모델 설정: 문서 관련성 판단에 고급 모델 사용
from app.config import settings
RERANK_MODEL = settings.openai_advanced_model  # gpt-4o (정확도 향상)

# 캐시 설정 (P1-1 성능 최적화)
RERANK_CACHE_TTL = 3600 * 6  # 6시간 (기존 1시간 → 6시간)


class RelevanceScore(BaseModel):
    """LLM이 평가한 청크 관련성 점수"""

    chunk_index: int = Field(..., description="청크 인덱스 (0-based)")
    relevance: float = Field(
        ..., ge=0.0, le=1.0, description="관련성 점수 (0.0~1.0)"
    )
    reason: str = Field(default="", description="점수 부여 이유")


class LLMReranker:
    """
    LLM 기반 리랭커: 검색된 청크를 질문과의 관련성으로 재평가

    정확도 우선 전략:
    - 빠른 응답보다 정확한 답변이 최우선
    - LLM을 사용해 청크와 질문의 의미적 관련성 평가
    - 피드백, 유사도 점수를 통합하여 최종 순위 결정

    Phase 4 최적화:
    - Redis 캐싱으로 LLM 호출 횟수 감소
    - 동적 배치 크기 조정
    - 상세 로깅 및 메트릭 수집
    """

    def __init__(
        self,
        *,
        w_llm: float = 0.6,  # LLM 점수 가중치
        w_feedback: float = 0.2,  # 피드백 점수 가중치
        w_similarity: float = 0.2,  # 코사인 유사도 가중치
        batch_size: int = 5,  # LLM 배치 처리 크기
        use_cache: bool = True,  # Redis 캐시 사용 여부
        dynamic_batch: bool = True,  # 동적 배치 크기 조정
    ):
        """
        Args:
            w_llm: LLM 관련성 점수 가중치 (기본: 0.6)
            w_feedback: 피드백 점수 가중치 (기본: 0.2)
            w_similarity: 유사도 점수 가중치 (기본: 0.2)
            batch_size: LLM 배치 처리 크기 (기본: 5)
            use_cache: Redis 캐싱 활성화 (기본: True)
            dynamic_batch: 동적 배치 크기 조정 (기본: True)
        """
        self.w_llm = w_llm
        self.w_feedback = w_feedback
        self.w_similarity = w_similarity
        self.batch_size = batch_size
        self.use_cache = use_cache
        self.dynamic_batch = dynamic_batch

        # 메트릭 수집
        self.cache_hits = 0
        self.cache_misses = 0
        self.llm_calls = 0

        # 가중치 합이 1.0인지 확인 (경고만)
        total_weight = w_llm + w_feedback + w_similarity
        if abs(total_weight - 1.0) > 0.01:
            log.warning(
                f"[RERANKER] Weight sum is {total_weight:.2f}, not 1.0. "
                f"Consider normalizing weights."
            )

    def get_metrics(self) -> dict:
        """
        메트릭 반환 (캐시 적중률, LLM 호출 수 등)

        Returns:
            메트릭 딕셔너리
        """
        total_requests = self.cache_hits + self.cache_misses
        hit_rate = (
            self.cache_hits / total_requests if total_requests > 0 else 0.0
        )

        return {
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_hit_rate": hit_rate,
            "llm_calls": self.llm_calls,
        }

    async def rerank(
        self,
        question: str,
        chunks: List[ScoredChunk],
        top_k: int = 5,
    ) -> List[ScoredChunk]:
        """
        LLM을 사용해 청크를 재랭킹합니다.

        Phase 4 최적화:
        - Redis 캐싱으로 동일 질문 재사용
        - 동적 배치 크기 조정
        - 메트릭 수집

        Args:
            question: 사용자 질문
            chunks: 검색된 청크 리스트 (ScoredChunk)
            top_k: 최종 선택할 청크 개수 (기본: 5)

        Returns:
            재랭킹된 ScoredChunk 리스트 (정확도 우선)

        Example:
            >>> reranker = LLMReranker()
            >>> reranked = await reranker.rerank(
            ...     question="연차는 몇 일인가요?",
            ...     chunks=scored_chunks,
            ...     top_k=5
            ... )
        """
        if not chunks:
            log.warning("[RERANK] No chunks to rerank")
            return []

        # [DEBUG] 리랭킹 시작 로깅
        dbg.log_reranking_start(question, len(chunks))

        log.info(
            f"[RERANK] Starting reranking: {len(chunks)} chunks → Top {top_k}"
        )

        # 동적 배치 크기 조정
        batch_size = self._get_optimal_batch_size(len(chunks))
        log.debug(f"[RERANK] Batch size: {batch_size} (dynamic={self.dynamic_batch})")

        # 1단계: LLM 관련성 평가 (배치 처리 + 캐싱)
        llm_scores = await self._evaluate_relevance_batch(question, chunks, batch_size)

        # [DEBUG] LLM 점수 로깅
        dbg.log_reranking_llm_scores(llm_scores, chunks)

        # 2단계: 점수 통합 (LLM + 피드백 + 유사도)
        reranked = []
        for i, chunk in enumerate(chunks):
            llm_score = llm_scores.get(i, 0.0)
            feedback_score = self._calculate_feedback_score(chunk)
            similarity_score = chunk.similarity or 0.0

            # 최종 점수 계산
            final_score = (
                self.w_llm * llm_score
                + self.w_feedback * feedback_score
                + self.w_similarity * similarity_score
            )

            # 점수 업데이트
            chunk.final_score = final_score

            # 이유 추가
            reason = (
                f"LLM={llm_score:.2f}, "
                f"FB={feedback_score:.2f}, "
                f"Sim={similarity_score:.2f}"
            )
            if reason not in chunk.reasons:
                chunk.reasons.append(reason)

            reranked.append(chunk)

        # 3단계: 최종 점수 기준 정렬
        reranked.sort(key=lambda c: c.final_score or 0.0, reverse=True)

        # 4단계: Top-K 선택
        selected = reranked[:top_k]

        # [DEBUG] 리랭킹 최종 결과 로깅
        dbg.log_reranking_final_scores(selected)

        log.info(
            f"[RERANK] Completed: Top {len(selected)} chunks selected\n"
            f"  Top-1 score: {selected[0].final_score:.3f}\n"
            f"  Top-{len(selected)} score: {selected[-1].final_score:.3f}"
        )

        return selected

    def _get_optimal_batch_size(self, num_chunks: int) -> int:
        """
        청크 수에 따라 최적 배치 크기 결정

        Args:
            num_chunks: 전체 청크 수

        Returns:
            최적 배치 크기 (3~10)
        """
        if not self.dynamic_batch:
            return self.batch_size

        # 동적 조정 로직
        if num_chunks <= 5:
            return 3  # 작은 배치로 빠르게
        elif num_chunks <= 10:
            return 5  # 기본
        elif num_chunks <= 20:
            return 7  # 중간
        else:
            return 10  # 큰 배치로 효율성 향상

    def _generate_cache_key(self, question: str, chunk_ids: List[str]) -> str:
        """
        캐시 키 생성 (질문 + 청크 ID 해시)

        Args:
            question: 사용자 질문
            chunk_ids: 청크 ID 리스트

        Returns:
            캐시 키 문자열
        """
        # 질문 + 청크 ID를 조합하여 해시
        content = question + "|" + ",".join(sorted(chunk_ids))
        hash_obj = hashlib.sha256(content.encode("utf-8"))
        cache_key = f"rerank:{hash_obj.hexdigest()[:16]}"
        return cache_key

    async def _evaluate_relevance_batch(
        self, question: str, chunks: List[ScoredChunk], batch_size: int
    ) -> dict[int, float]:
        """
        LLM을 사용해 청크 관련성을 배치 평가 (캐싱 포함)

        Args:
            question: 사용자 질문
            chunks: 청크 리스트
            batch_size: 배치 크기

        Returns:
            {chunk_index: relevance_score} 딕셔너리
        """
        if not chunks:
            return {}

        # 캐시 확인
        if self.use_cache and is_redis_available():
            chunk_ids = [c.chunk.chunk_id for c in chunks]
            cache_key = self._generate_cache_key(question, chunk_ids)

            try:
                redis_client = get_redis_client()
                cached = redis_client.get(cache_key)

                if cached:
                    self.cache_hits += 1
                    log.info(f"[RERANK] Cache HIT: {cache_key[:24]}...")
                    scores = json.loads(cached)
                    # 문자열 키를 정수로 변환
                    return {int(k): v for k, v in scores.items()}

                self.cache_misses += 1
                log.debug(f"[RERANK] Cache MISS: {cache_key[:24]}...")

            except Exception as e:
                log.warning(f"[RERANK] Cache error: {e}")

        # 캐시 미스 또는 캐시 비활성화: LLM 평가
        log.info(f"[RERANK] Evaluating {len(chunks)} chunks with LLM...")

        # 배치 처리
        scores = {}
        for batch_start in range(0, len(chunks), batch_size):
            batch_end = min(batch_start + batch_size, len(chunks))
            batch = chunks[batch_start:batch_end]

            batch_scores = await self._evaluate_batch(question, batch, batch_start)
            scores.update(batch_scores)

        log.info(f"[RERANK] LLM evaluation completed: {len(scores)} scores")

        # 캐시 저장
        if self.use_cache and is_redis_available():
            try:
                redis_client = get_redis_client()
                redis_client.setex(
                    cache_key,
                    RERANK_CACHE_TTL,
                    json.dumps(scores)
                )
                log.debug(f"[RERANK] Cached scores: {cache_key[:24]}... (TTL={RERANK_CACHE_TTL}s)")
            except Exception as e:
                log.warning(f"[RERANK] Cache save error: {e}")

        return scores

    async def _evaluate_batch(
        self, question: str, batch: List[ScoredChunk], offset: int
    ) -> dict[int, float]:
        """
        단일 배치 평가

        Args:
            question: 사용자 질문
            batch: 청크 배치
            offset: 청크 인덱스 오프셋

        Returns:
            {chunk_index: relevance_score}
        """
        # 프롬프트 구성
        chunks_text = []
        for i, sc in enumerate(batch):
            doc_title = sc.chunk.doc_title or "제목 없음"
            chunk_preview = sc.chunk.content[:800]  # 800자 미리보기 (더 많은 컨텍스트)
            chunks_text.append(f"청크 {i} (문서: {doc_title}):\n{chunk_preview}")

        prompt = f"""다음은 사용자 질문과 검색된 문서 청크들입니다.

**질문**: {question}

**청크 목록** (총 {len(batch)}개):
{chr(10).join(chunks_text)}

**중요: 반드시 모든 {len(batch)}개 청크를 평가해주세요!**

각 청크가 질문에 **실제로 답변할 수 있는 정보를 담고 있는지** 0.0~1.0 점수로 평가해주세요.

**평가 기준**:
- 1.0: 질문에 직접 답변할 수 있는 **구체적인 정보**가 포함됨
- 0.7~0.9: 관련 정보가 있지만 부분적인 답변만 가능
- 0.4~0.6: 약간 관련 있으나 답변에 도움이 제한적
- 0.1~0.3: 거의 관련 없음
- 0.0: 완전히 무관

**낮은 점수(0.1~0.3)를 줘야 하는 경우**:
- 빈 양식/서식/템플릿 (빈칸만 있고 실제 데이터가 없는 문서)
- 목차, 색인, 부서명 목록만 있는 내용
- 관련 키워드는 있지만 실제 답변에 필요한 정보가 없는 경우

**높은 점수(0.7~1.0)를 줘야 하는 경우**:
- 구체적인 수치, 기준, 조건이 명시된 경우
- 실제 규정, 절차, 방법이 설명된 경우
- 질문에 대한 답변을 직접 도출할 수 있는 내용
- **표나 데이터가 포함된 경우** (직급, 기준, 승진 등의 표)

**응답 형식** (JSON 배열 - 반드시 {len(batch)}개 항목):
```json
{{"scores": [
  {{"chunk_index": 0, "relevance": 0.9, "reason": "구체적인 기준 포함"}},
  {{"chunk_index": 1, "relevance": 0.2, "reason": "빈 양식"}},
  {{"chunk_index": 2, "relevance": 0.7, "reason": "관련 표 포함"}}
]}}
```

**주의**: 청크 0부터 {len(batch) - 1}까지 모든 청크를 평가해주세요. JSON만 응답하세요.
"""

        try:
            # LLM 호출 (비동기 + JSON 모드)
            self.llm_calls += 1  # 메트릭 수집

            client = get_async_client()
            response = await client.chat.completions.create(
                model=RERANK_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,  # 일관성 최대화
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            log.debug(f"[RERANK] LLM response: {content[:200]}...")

            # [DEBUG] LLM 응답 전체를 파일에 기록
            dbg.log("")
            dbg.log(f"[리랭커 LLM 응답 원본]")
            dbg.log(content[:500])

            # JSON 파싱
            try:
                # JSON 배열 추출 (코드 블록 제거)
                content = content.strip()
                if content.startswith("```"):
                    # 코드 블록 제거
                    lines = content.split("\n")
                    content = "\n".join(
                        line for line in lines if not line.startswith("```")
                    )

                # JSON 파싱 시도
                parsed = json.loads(content)

                # 배열이 아니면 배열로 감싸기
                if isinstance(parsed, dict):
                    dbg.log(f"[리랭커] parsed는 dict, keys={list(parsed.keys())}")
                    # {"scores": [...]} 형태인 경우
                    if "scores" in parsed:
                        parsed = parsed["scores"]
                    # {"results": [...]} 형태인 경우
                    elif "results" in parsed:
                        parsed = parsed["results"]
                    # {"evaluations": [...]} 형태인 경우
                    elif "evaluations" in parsed:
                        parsed = parsed["evaluations"]
                    # 배열 형태의 값이 있는지 찾기
                    else:
                        for key, value in parsed.items():
                            if isinstance(value, list) and len(value) > 0:
                                dbg.log(f"[리랭커] 배열 필드 발견: {key}")
                                parsed = value
                                break
                        else:
                            # 단일 객체인 경우 배열로
                            parsed = [parsed]

                scores_list = [RelevanceScore(**item) for item in parsed]
                dbg.log(f"[리랭커] 파싱 성공: {len(scores_list)}개 점수")

                # 모든 청크가 평가되지 않았으면 경고 및 보완
                if len(scores_list) < len(batch):
                    dbg.log(f"[리랭커] 경고: {len(batch)}개 중 {len(scores_list)}개만 평가됨, 미평가 청크에 유사도 기반 점수 부여")
                    evaluated_indices = {s.chunk_index for s in scores_list}
                    for i in range(len(batch)):
                        if i not in evaluated_indices:
                            # 미평가 청크: 유사도 점수를 기반으로 fallback
                            sim_score = batch[i].similarity or 0.5
                            scores_list.append(RelevanceScore(
                                chunk_index=i,
                                relevance=sim_score * 0.7,  # 유사도의 70%로 보수적 평가
                                reason="LLM 미평가 - 유사도 기반 추정"
                            ))

            except json.JSONDecodeError as e:
                log.warning(f"[RERANK] JSON parse error: {e}, using fallback")
                dbg.log(f"[리랭커] JSON 파싱 오류: {e}", "ERROR")
                # 폴백: 모든 청크에 0.5 점수
                scores_list = [
                    RelevanceScore(chunk_index=i, relevance=0.5, reason="Parse error")
                    for i in range(len(batch))
                ]
            except Exception as e:
                log.warning(f"[RERANK] Pydantic validation error: {e}, using fallback")
                dbg.log(f"[리랭커] Pydantic 검증 오류: {e}", "ERROR")
                dbg.log(f"[리랭커] parsed 내용: {str(parsed)[:300]}")
                # 폴백: 모든 청크에 0.5 점수
                scores_list = [
                    RelevanceScore(chunk_index=i, relevance=0.5, reason="Validation error")
                    for i in range(len(batch))
                ]

            # 인덱스 오프셋 적용
            scores = {}
            for score_obj in scores_list:
                global_index = offset + score_obj.chunk_index
                scores[global_index] = score_obj.relevance

            log.debug(
                f"[RERANK] Batch scores: {[(idx, f'{sc:.2f}') for idx, sc in scores.items()]}"
            )

            return scores

        except Exception as e:
            log.error(f"[RERANK] LLM evaluation failed: {e}")
            # 폴백: 모든 청크에 0.5 점수
            return {offset + i: 0.5 for i in range(len(batch))}

    def _calculate_feedback_score(self, chunk: ScoredChunk) -> float:
        """
        피드백 점수 계산 (0.0~1.0)

        Args:
            chunk: ScoredChunk

        Returns:
            정규화된 피드백 점수 (0.0~1.0)
        """
        # 메타데이터에서 피드백 추출
        meta = chunk.chunk.model_dump()
        fb_pos = meta.get("fb_pos", 0) or 0
        fb_neg = meta.get("fb_neg", 0) or 0

        total_fb = fb_pos + fb_neg
        if total_fb == 0:
            return 0.5  # 중립

        # 긍정 비율 (0.0~1.0)
        positive_ratio = fb_pos / total_fb

        return positive_ratio

# ====================================================================
# 간단한 휴리스틱 리랭커 (LLM 없이 빠르게)
# ====================================================================
class HeuristicReranker:
    """
    LLM 없이 빠르게 재랭킹 (피드백 + 유사도만 사용)

    용도:
    - 빠른 응답이 필요한 경우
    - LLM API 비용 절감
    """

    def __init__(
        self,
        w_feedback: float = 0.5,
        w_similarity: float = 0.5,
    ):
        self.w_feedback = w_feedback
        self.w_similarity = w_similarity
        log.info("[HEURISTIC-RERANK] Initialized (no LLM)")

    async def rerank(
        self,
        question: str,
        chunks: List[ScoredChunk],
        top_k: int = 5,
    ) -> List[ScoredChunk]:
        """휴리스틱 재랭킹 (LLM 호출 없음)"""
        if not chunks:
            return []

        log.info(f"[HEURISTIC-RERANK] Reranking {len(chunks)} chunks → Top {top_k}")

        reranked = []
        for chunk in chunks:
            feedback_score = self._calculate_feedback_score(chunk)
            similarity_score = chunk.similarity or 0.0

            final_score = (
                self.w_feedback * feedback_score
                + self.w_similarity * similarity_score
            )

            chunk.final_score = final_score
            reranked.append(chunk)

        reranked.sort(key=lambda c: c.final_score or 0.0, reverse=True)
        return reranked[:top_k]

    def _calculate_feedback_score(self, chunk: ScoredChunk) -> float:
        """피드백 점수 (LLMReranker와 동일)"""
        meta = chunk.chunk.model_dump()
        fb_pos = meta.get("fb_pos", 0) or 0
        fb_neg = meta.get("fb_neg", 0) or 0

        total_fb = fb_pos + fb_neg
        if total_fb == 0:
            return 0.5

        return fb_pos / total_fb
