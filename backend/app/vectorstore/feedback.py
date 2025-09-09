import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple

from app.vectorstore.store import get_collection
from app.config import settings

DATA_DIR = (
    Path(settings.data_dir) if hasattr(settings, "data_dir") else Path("./backend/data")
)
EVENTS_PATH = DATA_DIR / "feedback" / "events.jsonl"
EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)


def _append_event(
    chunk_id: str,
    vote: str,
    question: str | None,
    query_tags: list[str] | None,
    user_id: str | None,
):
    evt = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "chunk_id": chunk_id,
        "vote": vote,
        "question": question,
        "query_tags": query_tags or [],
        "user_id": user_id,
    }
    with EVENTS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(evt, ensure_ascii=False) + "\n")


def update_feedback(
    chunk_id: str,
    vote: str,
    question: str | None = None,
    query_tags: list[str] | None = None,
    user_id: str | None = None,
) -> Tuple[int, int]:
    """
    Chroma 메타데이터의 fb_pos/fb_neg를 증감하고 값을 리턴.
    """
    col = get_collection()
    got = col.get(ids=[chunk_id], include=["metadatas"])
    if not got or not got.get("ids"):
        raise KeyError(f"chunk not found: {chunk_id}")

    meta = (got["metadatas"] or [{}])[0] or {}
    pos = int(meta.get("fb_pos") or 0)
    neg = int(meta.get("fb_neg") or 0)

    if vote == "up":
        pos += 1
    else:
        neg += 1

    # 메타데이터는 스칼라만 허용됨! (list 금지)
    meta["fb_pos"] = pos
    meta["fb_neg"] = neg

    col.update(ids=[chunk_id], metadatas=[meta])

    # 이벤트 로그는 파일에 별도 축적(선택)
    _append_event(chunk_id, vote, question, query_tags, user_id)
    return pos, neg
