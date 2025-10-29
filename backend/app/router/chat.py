from __future__ import annotations

import logging
import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.rag.retriever import retrieve
from app.rag.generator import generate_answer_stream
from app.services.idgen import new_id
from app.models.schemas import (
    ChatTokenEvent,
    ChatFinalEvent,
    ChatFinalData,
    ChatErrorEvent,
    ChatErrorData,
)
from app.ingest.tagger import tag_query

router = APIRouter()
logger = logging.getLogger("app.router.chat")


@router.websocket("/")
async def chat_ws(ws: WebSocket):
    await ws.accept()
    try:
        question = await ws.receive_text()

        t_start = time.perf_counter()
        logger.info("RAG pipeline started for question (len=%d)", len(question or ""))

        # 1) 질문 태깅 시간 측정
        t1 = time.perf_counter()
        used_tags: list[str] = await tag_query(question, max_tags=6)
        t2 = time.perf_counter()
        logger.info(f"Step 1: Tagging took {(t2 - t1) * 1000:.1f} ms")

        # 2) 후보 검색 (리트리버) 시간 측정
        t3 = time.perf_counter()
        candidates = await retrieve(question, used_tags)
        t4 = time.perf_counter()
        logger.info(f"Step 2: Retrieval took {(t4 - t3) * 1000:.1f} ms")

        # 3) 답변 스트리밍 생성 시간 측정
        t5 = time.perf_counter()
        full_answer = ""
        used_chunks = None
        first_token_sent = False

        async for token, chunks in generate_answer_stream(question, candidates):
            if chunks is not None:
                # 스트림 종료: 청크 리스트 수신
                used_chunks = chunks
            else:
                # 토큰 스트리밍
                full_answer += token

                # 첫 토큰 시간 측정
                if not first_token_sent:
                    t_first_token = time.perf_counter()
                    logger.info(f"First token latency: {(t_first_token - t_start) * 1000:.1f} ms")
                    first_token_sent = True

                # 토큰 이벤트 전송
                token_event = ChatTokenEvent(token=token)
                await ws.send_json(token_event.model_dump(mode="json"))

        t6 = time.perf_counter()
        logger.info(f"Step 3: Generation (streaming) took {(t6 - t5) * 1000:.1f} ms")

        t_end = time.perf_counter()
        total_ms = (t_end - t_start) * 1000
        logger.info(f"Total RAG pipeline time: {total_ms:.1f} ms")

        # 최종 응답 전송
        final_msg = ChatFinalEvent(
            data=ChatFinalData(
                answer=full_answer,
                chunks=used_chunks or [],
                answer_id=new_id("ans"),
                used_tags=used_tags,
                latency_ms=int(total_ms),
            )
        )
        await ws.send_json(final_msg.model_dump(mode="json"))

    except WebSocketDisconnect:
        # 클라이언트가 연결을 끊음
        return
    except Exception as e:
        err = ChatErrorEvent(data=ChatErrorData(message=str(e), code="internal"))
        await ws.send_json(err.model_dump(mode="json"))


