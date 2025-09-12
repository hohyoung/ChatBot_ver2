# backend/app/router/feedback.py
from fastapi import APIRouter, HTTPException
from app.services.logging import get_logger
from app.models.schemas import FeedbackRequest, FeedbackResponse  # ← 실제 이름에 맞춰 조정

import app.services.feedback_store as _fs  # 모듈 별칭으로 불러와서 .upsert_boost 호출

router = APIRouter()
log = get_logger(__name__)

@router.post("", response_model=FeedbackResponse)
def submit_feedback(body: FeedbackRequest):
    """
    요청 스키마(Strict) 기준:
      - body.tag_context: List[str]  (과거 query_tags 아님)
      - body.query: Optional[str]    (과거 question 아님)
    """
    try:
        log.info("feedback body = %s", body.model_dump())

        # ✅ 필드 매핑: 스키마 → 서비스
        res = _fs.upsert_boost(
            chunk_id   = body.chunk_id,
            vote       = body.vote,
            weight     = (body.weight or 1.0),
            query_tags = body.tag_context,   # ← 변경 포인트 (query_tags → tag_context)
            user_id    = None,               # 인증 도입 전까지 None
            question   = body.query,         # ← 변경 포인트 (question → query)
        )

        # ✅ 응답 스키마: ok/updated/error 형태로 래핑
        #   - 스크립트/클라에서 과거 수치가 필요하면 updated.meta에 포함
        return {
            "ok": True,
            "updated": {
                "chunk_id": res.get("chunk_id"),
                "new_boost": res.get("factor"),
                "meta": {
                    "fb_pos":  res.get("fb_pos"),
                    "fb_neg":  res.get("fb_neg"),
                    "factor":  res.get("factor"),
                },
            },
            "error": None,
        }

    except Exception as e:
        log.exception("feedback error: %s", e)
        # 스키마 일관성을 위해 error 채워서 반환
        raise HTTPException(status_code=500, detail=str(e))
