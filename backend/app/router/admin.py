from __future__ import annotations

import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Header, Query, Path
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db import models as m
from app.services.security import decode_access_token

# docs 라우터가 쓰는 유틸 재사용
from app.vectorstore.store import list_docs_by_owner, delete_doc_for_owner
from app.services.storage import delete_files_by_relpaths
from app.services.feedback_store import delete_many as feedback_delete_many

router = APIRouter()


# ─────────────
# 스키마
# ─────────────
class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    username: str
    security_level: int
    is_active: bool


class UserPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    username: Optional[str] = Field(default=None, min_length=3, max_length=50)
    password: Optional[str] = Field(default=None, min_length=6, max_length=128)
    security_level: Optional[int] = Field(default=None, ge=1, le=4)
    is_active: Optional[bool] = None


# ─────────────
# 권한 체크
# ─────────────
def _require_admin(authorization: str | None, db: Session) -> m.User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="인증 토큰이 없습니다.")
    token = authorization.split(" ", 1)[1]
    data = decode_access_token(token)
    if not data or "sub" not in data:
        raise HTTPException(status_code=401, detail="토큰이 유효하지 않습니다.")
    me = db.get(m.User, int(data["sub"]))
    if not me:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    if me.security_level != 1:
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    return me


# ─────────────
# API
# ─────────────
@router.get("/users", response_model=List[UserOut])
def list_users(
    authorization: str = Header(None),
    db: Session = Depends(get_db),
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    _require_admin(authorization, db)
    query = db.query(m.User)
    if q:
        like = f"%{q}%"
        query = query.filter((m.User.username.ilike(like)) | (m.User.name.ilike(like)))
    users = query.order_by(m.User.id.desc()).offset(offset).limit(limit).all()
    return [UserOut.model_validate(u) for u in users]


@router.patch("/users/{user_id}", response_model=UserOut)
def patch_user(
    user_id: int = Path(..., ge=1),
    body: UserPatch = ...,
    authorization: str = Header(None),
    db: Session = Depends(get_db),
):
    _require_admin(authorization, db)
    user = db.get(m.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    # username 변경 충돌 체크
    if body.username and body.username != user.username:
        exists = db.query(m.User).filter(m.User.username == body.username).first()
        if exists:
            raise HTTPException(status_code=409, detail="이미 사용 중인 아이디입니다.")
        user.username = body.username

    if body.name is not None:
        user.name = body.name
    if body.password:
        from app.services.security import hash_password

        user.password_hash = hash_password(body.password)
    if body.security_level is not None:
        if body.security_level not in (1, 2, 3, 4):
            raise HTTPException(
                status_code=400, detail="security_level은 1~4여야 합니다."
            )
        user.security_level = body.security_level
    if body.is_active is not None:
        user.is_active = body.is_active

    db.add(user)
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int = Path(..., ge=1),
    authorization: str = Header(None),
    db: Session = Depends(get_db),
):
    _require_admin(authorization, db)
    user = db.get(m.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    db.delete(user)
    db.commit()
    return {"ok": True}


# =========================
# Admin: 문서 목록/삭제
# =========================


@router.get("/docs")
def list_all_docs(
    authorization: str = Header(None),
    db: Session = Depends(get_db),
    q: str | None = Query(
        default=None, description="제목/업로더 이름/아이디 부분 일치"
    ),
    limit: int = Query(default=500, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
):
    """
    모든 사용자의 문서를 관리자 권한으로 조회한다.
    각 문서에 업로더 정보(owner_id/owner_username/owner_name)와 uploaded_at을 확실히 채워서 응답.
    """
    _require_admin(authorization, db)

    # 1) 사용자 조회(필터 적용)
    user_q = db.query(m.User)
    if q:
        like = f"%{q}%"
        user_q = user_q.filter(
            (m.User.username.ilike(like)) | (m.User.name.ilike(like))
        )
    users = user_q.all()

    # 2) 사용자별 문서 수집 + 필드 보강
    items: list[dict] = []
    q_lower = (q or "").lower()
    for u in users:
        docs = list_docs_by_owner(int(u.id))
        for d in docs:
            row = dict(d or {})
            # 업로더 정보 확정 (이름/아이디 모두 포함)
            row.setdefault("owner_id", int(u.id))
            row.setdefault("owner_username", u.username or "")
            row.setdefault("owner_name", u.name or u.username or "")

            # 업로드 시각 보강
            row["uploaded_at"] = row.get("uploaded_at") or _pick_uploaded_at(row)

            # q가 있으면 제목/업로더(이름/아이디)로 2차 필터링
            if q:
                title = (row.get("doc_title") or "").lower()
                owner_name = (row.get("owner_name") or "").lower()
                owner_user = (row.get("owner_username") or "").lower()
                if (
                    (q_lower not in title)
                    and (q_lower not in owner_name)
                    and (q_lower not in owner_user)
                ):
                    continue

            items.append(row)

    # 3) offset/limit
    items = items[offset : offset + limit]
    return {"items": items}


@router.delete("/docs/{doc_id}")
def admin_delete_doc(
    doc_id: str = Path(..., description="문서 ID"),
    authorization: str = Header(None),
    db: Session = Depends(get_db),
):
    """
    관리자 권한으로 특정 문서 삭제.
    어떤 사용자의 문서인지 모를 수 있으므로 소유자를 탐색해서 삭제한다.
    """
    _require_admin(
        authorization, db
    )  # 관리자 가드  :contentReference[oaicite:9]{index=9}

    # 1) 모든 사용자에서 doc_id 소유자 탐색
    user_ids = [row.id for row in db.query(m.User.id).all()]
    owner_id = None
    found_meta = None
    for uid in user_ids:
        docs = list_docs_by_owner(int(uid))
        for d in docs:
            if d.get("doc_id") == doc_id:
                owner_id = uid
                found_meta = d
                break
        if owner_id:
            break

    if not owner_id:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")

    # 2) 사용자 소유 삭제 유틸 재사용 (권한은 admin 가드에서 이미 확인)
    result = delete_doc_for_owner(
        doc_id, int(owner_id)
    )  #  :contentReference[oaicite:10]{index=10}
    deleted = int(result.get("deleted", 0))
    if deleted == 0:
        raise HTTPException(status_code=404, detail="삭제 실패 또는 권한 없음")

    # 3) 연관 피드백/파일 정리 (docs.py와 동일한 후처리)  :contentReference[oaicite:11]{index=11}
    chunk_ids = result.get("chunk_ids") or []
    feedback_delete_many(chunk_ids)

    rels = [r for r in (result.get("doc_relpaths") or []) if r]
    stats = {"requested": 0, "deleted": 0, "errors": []}
    if rels:
        stats = delete_files_by_relpaths(rels)

    return {"ok": True, "deleted_chunks": deleted, "file_delete": stats}


def _pick_uploaded_at(row: dict) -> str | None:
    """
    uploaded_at 후보들을 순서대로 고르고, 없으면 파일 mtime을 시도.
    ISO8601 문자열(UTC/로컬 무관)을 반환하거나 None.
    """
    for k in ("uploaded_at", "created_at", "updated_at", "ingested_at"):
        v = row.get(k)
        if v:
            try:
                dt = (
                    v
                    if isinstance(v, datetime)
                    else datetime.fromisoformat(str(v).replace("Z", "+00:00"))
                )
                return dt.isoformat()
            except Exception:
                continue

    # 파일 경로가 있으면 mtime을 사용
    rel = (row.get("doc_relpath") or "").replace("\\", "/").lstrip("/")
    if rel:
        try:
            from app.services.storage import DOCS_DIR  # 이미 파일 상단 import 되어 있음

            p = (DOCS_DIR / rel).resolve()
            if p.exists():
                return datetime.fromtimestamp(p.stat().st_mtime).isoformat()
        except Exception:
            pass
    return None
