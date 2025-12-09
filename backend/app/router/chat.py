from __future__ import annotations

import os
import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.rag.retriever import retrieve
from app.rag.generator import generate_answer_stream
from app.services.idgen import new_id
from app.services.faq import log_question
from app.services.logging import get_logger
from app.models.schemas import (
    ChatTokenEvent,
    ChatFinalEvent,
    ChatAnswer,
    ChatErrorEvent,
)

router = APIRouter()
logger = get_logger(__name__)

# ====================================================================
# Feature Flags: GAR Phase 2/3 활성화 여부
# ====================================================================
# 환경변수로 제어:
# - GAR_PHASE2_ENABLED=true/false (쿼리 확장 + 다단계 검색)
# - GAR_PHASE3_ENABLED=true/false (LLM 리랭킹)
USE_GAR_PHASE2 = os.getenv("GAR_PHASE2_ENABLED", "false").lower() == "true"
USE_GAR_PHASE3 = os.getenv("GAR_PHASE3_ENABLED", "false").lower() == "true"


@router.websocket("/")
async def chat_ws(ws: WebSocket):
    await ws.accept()
    try:
        raw_question = await ws.receive_text()

        # !tq 접두사: FAQ 집계에서 제외 (테스트 쿼리)
        skip_log = raw_question.startswith("!tq ")
        question = raw_question[4:].strip() if skip_log else raw_question

        t_start = time.perf_counter()
        logger.debug(f"RAG 시작: {question[:30]}... (skip_log={skip_log})")

        # ====================================================================
        # Feature Flag 분기: GAR Phase 2/3 vs 기존 RAG
        # ====================================================================
        if USE_GAR_PHASE2 or USE_GAR_PHASE3:
            # ✅ GAR 파이프라인 사용 (Phase 2/3)
            # GAR 파이프라인 사용

            from app.rag.orchestrator import orchestrate_gar_stream

            full_answer = ""
            used_chunks = None
            image_refs = []  # GAR에서는 orchestrator 레벨에서 image_refs를 전달하지 않음
            first_token_sent = False

            async for token, chunks in orchestrate_gar_stream(
                question=question,
                use_phase2=USE_GAR_PHASE2,
                use_phase3=USE_GAR_PHASE3,
                websocket=ws
            ):
                if chunks is not None:
                    # 스트림 종료: 청크 리스트 수신
                    used_chunks = chunks
                    # GAR: 청크에서 image_refs 생성 (프론트엔드와 동일한 로직)
                    image_refs = []
                    img_idx = 1
                    for chunk in (used_chunks or []):
                        if getattr(chunk, 'has_image', False) and getattr(chunk, 'image_url', None):
                            image_refs.append({
                                "ref": f"[IMG{img_idx}]",
                                "url": chunk.image_url,
                                "type": getattr(chunk, 'image_type', 'image'),
                                "doc_title": getattr(chunk, 'doc_title', None),
                                "page": getattr(chunk, 'page_start', None),
                            })
                            img_idx += 1
                else:
                    # 토큰 스트리밍
                    full_answer += token

                    # 첫 토큰 시간 측정
                    if not first_token_sent:
                        t_first_token = time.perf_counter()
                        logger.debug(f"첫 토큰: {(t_first_token - t_start) * 1000:.0f}ms")
                        first_token_sent = True

                    # 토큰 이벤트 전송
                    token_event = ChatTokenEvent(token=token)
                    await ws.send_json(token_event.model_dump(mode="json"))

        else:
            # 기존 RAG 파이프라인 (태깅 제거됨 - 방안 3)

            # 순수 벡터 검색 (태깅 없이)
            t1 = time.perf_counter()
            candidates = await retrieve(question, tags=None)

            t2 = time.perf_counter()
            logger.debug(
                f"검색 완료: {(t2 - t1) * 1000:.0f}ms, 후보={len(candidates)}개"
            )

            # 3) 답변 스트리밍 생성 시간 측정
            t5 = time.perf_counter()
            full_answer = ""
            used_chunks = None
            image_refs = []  # 이미지 참조 리스트
            first_token_sent = False

            async for token, chunks, img_refs in generate_answer_stream(question, candidates):
                if chunks is not None:
                    # 스트림 종료: 청크 리스트 및 이미지 참조 수신
                    used_chunks = chunks
                    image_refs = img_refs or []
                else:
                    # 토큰 스트리밍
                    full_answer += token

                    # 첫 토큰 시간 측정
                    if not first_token_sent:
                        t_first_token = time.perf_counter()
                        logger.debug(f"첫 토큰: {(t_first_token - t_start) * 1000:.0f}ms")
                        first_token_sent = True

                    # 토큰 이벤트 전송
                    token_event = ChatTokenEvent(token=token)
                    await ws.send_json(token_event.model_dump(mode="json"))

            t6 = time.perf_counter()
            logger.debug(f"생성: {(t6 - t5) * 1000:.0f}ms")

        # ====================================================================
        # 공통: 최종 응답 전송
        # ====================================================================
        t_end = time.perf_counter()
        total_ms = (t_end - t_start) * 1000
        logger.info(f"응답 완료: {total_ms:.0f}ms")

        # image_refs가 GAR 파이프라인에서 정의되지 않을 수 있으므로 기본값 설정
        if 'image_refs' not in locals():
            image_refs = []

        # 최종 응답 전송
        answer_id = new_id("ans")
        final_msg = ChatFinalEvent(
            data=ChatAnswer(
                answer=full_answer,
                chunks=used_chunks or [],
                image_refs=image_refs,
                answer_id=answer_id,
                latency_ms=int(total_ms),
            )
        )
        await ws.send_json(final_msg.model_dump(mode="json"))

        # 질문 로그 저장 (FAQ 생성용) - !tq 접두사 시 스킵
        if not skip_log:
            try:
                await log_question(question, answer_id)
            except Exception as log_err:
                logger.warning(f"질문 로그 저장 실패 (무시): {log_err}")

    except WebSocketDisconnect:
        # 클라이언트가 연결을 끊음
        return
    except Exception as e:
        logger.exception("Chat WebSocket error")
        err = ChatErrorEvent(error=str(e))
        await ws.send_json(err.model_dump(mode="json"))


