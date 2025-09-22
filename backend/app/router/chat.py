from __future__ import annotations

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
from fastapi import Body
from app.ingest.tagger import tag_query

router = APIRouter()


@router.websocket("/")
async def chat_ws(ws: WebSocket):
    await ws.accept()
    try:
        t0 = time.perf_counter()

        # 프론트 → 백: 문자열만 수신 (요구사항 2-1)
        question = await ws.receive_text()

        # ✅ 질문 태깅 활성화 (실패 시 빈 리스트)
        try:
            used_tags: list[str] = await tag_query(question, max_tags=6)
        except Exception:
            used_tags = []

        # 후보 검색 → 답변 생성
        candidates = await retrieve(question, used_tags)
        answer, used_chunks = await generate_answer(question, candidates)

        latency_ms = int((time.perf_counter() - t0) * 1000)

        # 백 → 프론트: 최종 응답 + 근거 청크들 (요구사항 2-1)
        final_msg = ChatFinalEvent(
            data=ChatFinalData(
                answer=answer,
                chunks=used_chunks,  # Pydantic 모델 그대로 OK
                answer_id=new_id("ans"),
                used_tags=used_tags,
                latency_ms=latency_ms,
            )
        )
        await ws.send_json(final_msg.model_dump(mode="json"))

    except WebSocketDisconnect:
        # 클라이언트가 연결을 끊음
        return
    except Exception as e:
        err = ChatErrorEvent(data=ChatErrorData(message=str(e), code="internal"))
        await ws.send_json(err.model_dump(mode="json"))


# # 디버그용
# @router.post("/debug")
# async def chat_debug(question: str = Body(..., embed=True)):
#     t0 = time.perf_counter()
#     try:
#         tags = await tag_query(question)
#     except Exception:
#         tags = []
#     cands = await retrieve(question, tags, k=5)
#     answer, used_chunks = await generate_answer(question, cands)
#     return {
#         "type": "final",
#         "data": {
#             "answer": answer,
#             "chunks": [c.model_dump() for c in used_chunks],
#             "answer_id": new_id("ans"),
#             "used_tags": tags,
#             "latency_ms": int((time.perf_counter() - t0) * 1000),
#         },
#     }
