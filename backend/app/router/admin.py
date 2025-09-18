from __future__ import annotations

from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Header, Query, Path
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db import models as m
from app.services.security import decode_access_token
from app.models.schemas import AuthUser
from app.router.auth import current_user

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
        default=None, description="제목/소유자 username 부분 일치 검색"
    ),
    limit: int = Query(default=500, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
):
    """
    모든 사용자의 문서를 관리자 권한으로 조회.
    기존 /docs/my 가 반환하는 item 형태와 최대한 동일하게 맞춘다.
    """
    _require_admin(
        authorization, db
    )  # 관리자 가드  :contentReference[oaicite:7]{index=7}

    # 1) 모든 사용자 id 로드 (필요하면 q로 1차 필터)
    user_query = db.query(m.User)
    if q:
        like = f"%{q}%"
        user_query = user_query.filter(
            (m.User.username.ilike(like)) | (m.User.name.ilike(like))
        )
    users = user_query.all()

    # 2) 각 사용자별 문서 집계
    items: list[dict] = []
    for u in users:
        docs = list_docs_by_owner(
            int(u.id)
        )  # 기존 유틸 재사용  :contentReference[oaicite:8]{index=8}
        if q:
            # 제목/owner_username 간단 필터
            docs = [
                d
                for d in docs
                if (q.lower() in (d.get("doc_title") or "").lower())
                or (q.lower() in (d.get("owner_username") or "").lower())
            ]
        items.extend(docs)

    # 3) offset/limit 적용
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
