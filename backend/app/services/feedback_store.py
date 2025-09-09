# backend/app/services/feedback_store.py
from __future__ import annotations

import json
import time
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, List, Optional, Literal

from app.config import settings
from app.services.logging import get_logger

log = get_logger("app.services.feedback_store")

# data/chroma 의 상위(data)에 feedback 폴더 생성
DATA_ROOT = Path(settings.chroma_persist_dir).resolve().parent
_FEEDBACK_DIR = DATA_ROOT / "feedback"
_FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)


def _file_path(chunk_id: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "._-=" else "_" for ch in chunk_id)
    return _FEEDBACK_DIR / f"{safe}.json"


def _atomic_write(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        "w", delete=False, dir=str(path.parent), encoding="utf-8"
    ) as tmp:
        json.dump(obj, tmp, ensure_ascii=False, indent=2)
        tmp.flush()
    Path(tmp.name).replace(path)


def _load(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception as e:
        log.warning(
            "feedback_store: failed to read %s (%s) — recreating empty", path, e
        )
        return {}


def _compute_factor(pos: int, neg: int) -> float:
    # 확률형 선호도 p = (pos+1)/(pos+neg+2) → factor = 0.5 + p (범위 0.5~1.5)
    p = (pos + 1.0) / (pos + neg + 2.0)
    return 0.5 + p


def upsert_boost(
    chunk_id: str,
    vote: Literal["up", "down"],
    *,
    weight: float = 1.0,
    query_tags: Optional[List[str]] = None,
    user_id: Optional[str] = None,
    question: Optional[str] = None,
) -> Dict[str, Any]:
    """
    피드백(업/다운)을 청크별로 누적하고 최신 factor를 계산해 저장.
    반환: {"chunk_id", "fb_pos", "fb_neg", "factor"}
    """
    path = _file_path(chunk_id)
    data = _load(path)

    fb_pos = int(data.get("fb_pos", 0) or 0)
    fb_neg = int(data.get("fb_neg", 0) or 0)
    w_pos = float(data.get("w_pos", 0.0) or 0.0)
    w_neg = float(data.get("w_neg", 0.0) or 0.0)

    if vote == "up":
        fb_pos += 1
        w_pos += float(weight)
    else:
        fb_neg += 1
        w_neg += float(weight)

    factor = _compute_factor(fb_pos, fb_neg)

    # 간단 이력 (원치 않으면 삭제해도 됨)
    history = data.get("history", [])
    history.append(
        {
            "ts": time.time(),
            "vote": vote,
            "weight": float(weight),
            "query_tags": list(query_tags or []),
            "user_id": user_id,
            "question": question,
        }
    )

    doc = {
        "chunk_id": chunk_id,
        "fb_pos": fb_pos,
        "fb_neg": fb_neg,
        "w_pos": round(w_pos, 6),
        "w_neg": round(w_neg, 6),
        "factor": round(factor, 6),
        "history": history[-200:],  # 최대 200개만 유지
    }
    _atomic_write(path, doc)

    log.info(
        "[feedback] upsert chunk=%s vote=%s weight=%.3f -> fb_pos=%d fb_neg=%d factor=%.4f tags=%s",
        chunk_id,
        vote,
        weight,
        fb_pos,
        fb_neg,
        factor,
        query_tags,
    )

    return {"chunk_id": chunk_id, "fb_pos": fb_pos, "fb_neg": fb_neg, "factor": factor}


def get_boost_map(
    chunk_ids: List[str], query_tags: Optional[List[str]] = None
) -> Dict[str, float]:
    """
    리트리버가 사용하는 부스트 맵. 현재는 전역 factor만 사용(태그별은 차후 확장).
    """
    out: Dict[str, float] = {}
    for cid in chunk_ids:
        doc = _load(_file_path(cid))
        out[cid] = float(doc.get("factor", 1.0) or 1.0)

    if out:
        log.info("[feedback] boost_map: %s", {k: round(v, 4) for k, v in out.items()})
    return out
