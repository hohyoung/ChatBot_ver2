from __future__ import annotations

import logging
import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.rag.retriever import retrieve
from app.rag.generator import generate_answer
from app.services.idgen import new_id
from app.models.schemas import (
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

        # 3) 답변 생성 (제너레이터) 시간 측정
        t5 = time.perf_counter()
        answer, used_chunks = await generate_answer(question, candidates)
        t6 = time.perf_counter()
        logger.info(f"Step 3: Generation took {(t6 - t5) * 1000:.1f} ms")
        
        t_end = time.perf_counter()
        total_ms = (t_end - t_start) * 1000
        logger.info(f"Total RAG pipeline time: {total_ms:.1f} ms")

        # 최종 응답 전송
        final_msg = ChatFinalEvent(
            data=ChatFinalData(
                answer=answer,
                chunks=used_chunks,
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


