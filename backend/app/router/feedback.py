from __future__ import annotations

from fastapi import APIRouter, HTTPException
from app.services.logging import get_logger
from app.models.schemas import FeedbackRequest, FeedbackResponse, FeedbackUpdated
from app.ingest.tagger import tag_query
import app.services.feedback_store as _fs  # upsert_boost 호출

router = APIRouter()
log = get_logger(__name__)


@router.post("", response_model=FeedbackResponse)
async def submit_feedback(body: FeedbackRequest) -> FeedbackResponse:
    """
    피드백 수집 엔드포인트.
    - 프런트가 tag_context를 비워보내도 서버가 question(query)에서 태그를 생성하여 저장합니다.
    - 레거시 필드(signal, weight)도 하위호환으로 처리합니다.
    """
    try:
        if not body.chunk_id:
            raise ValueError("chunk_id is required")

        # 1) vote / weight 하위호환 처리
        vote = body.vote or body.signal
        if vote not in ("up", "down"):
            raise ValueError("vote must be 'up' or 'down'")
        weight = float(body.weight) if body.weight is not None else 1.0

        # 2) 질문 태그 확보 (클라이언트가 비워 보내면 서버 폴백)
        query = (body.query or "").strip()
        query_tags = list(body.tag_context or [])
        if not query_tags and query:
            try:
                query_tags = await tag_query(query, max_tags=6)
            except Exception:
                # 태그 생성 실패 → 컨텍스트 없이 진행(전역 피드백으로 저장)
                query_tags = []

        # 3) 스토어에 누적 및 factor 재계산
        res = _fs.upsert_boost(
            chunk_id=body.chunk_id,
            vote=vote,
            weight=weight,
            query_tags=query_tags,
            user_id=None,  # JWT 도입 전까지 None
            question=query or None,
        )

        # 4) 응답 스키마 구성
        updated = FeedbackUpdated(
            chunk_id=res.get("chunk_id") or body.chunk_id,
            delta=res.get("delta"),
            new_boost=res.get("factor"),
            meta={
                "fb_pos": res.get("fb_pos"),
                "fb_neg": res.get("fb_neg"),
                "factor": res.get("factor"),
            },
        )
        return FeedbackResponse(ok=True, updated=updated, error=None)

    except Exception as e:
        log.exception("feedback error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
