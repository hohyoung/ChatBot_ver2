#!/usr/bin/env python3
"""
DB 관리 스크립트 (Chroma)
루트 구조: backend/ , frontend/ , scripts/

사용 예)
  python scripts/db_manage.py init
  python scripts/db_manage.py status
  python scripts/db_manage.py list
  python scripts/db_manage.py drop-collection
  python scripts/db_manage.py nuke --force
"""
from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Optional

# ---------- 경로 설정 ----------
ROOT_DIR = Path(__file__).resolve().parents[1]  # repo root
BACKEND_DIR = ROOT_DIR / "backend"
APP_DIR = BACKEND_DIR / "app"

# app 패키지 경로를 sys.path 에 추가 (어디서 실행해도 app.* 임포트 가능)
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# ---------- 설정/로깅 불러오기 (실패 시 폴백) ----------
settings = None
get_logger = None

try:
    # backend/app/config.py 의 settings
    from app.config import settings as _settings  # type: ignore

    settings = _settings
except Exception as e:
    logging.warning("[db_manage] app.config import 실패: %s (env 기본값으로 진행)", e)

try:
    # backend/app/services/logging.py 의 get_logger (없으면 기본 logging 사용)
    from app.services.logging import get_logger as _get_logger  # type: ignore

    get_logger = _get_logger
except Exception:
    get_logger = None

# 기본 로깅
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger("scripts.db_manage")
if get_logger:
    # 프로젝트 로거 스타일을 쓰고 싶다면 이 줄로 교체 가능:
    log = get_logger("scripts.db_manage")  # type: ignore

# ---------- .env 로드 (settings 없을 때 폴백용) ----------
try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv()
except Exception:
    pass


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    return os.getenv(name, default)


# ---------- Chroma ----------
try:
    import chromadb  # type: ignore
except ImportError as e:
    print("[ERR] chromadb 미설치. backend/requirements.txt 로 설치하세요.")
    raise


def _resolve_chroma_dir() -> Path:
    """
    settings 가 있으면 settings.chroma_persist_dir 사용,
    없으면 .env → 기본값 순으로 결정.
    상대경로는 backend/ 기준으로 해석.
    """
    raw = None
    if settings and getattr(settings, "chroma_persist_dir", None):
        raw = settings.chroma_persist_dir
    else:
        raw = _env("CHROMA_PERSIST_DIR", "data/chroma")

    p = Path(raw)
    if not p.is_absolute():
        p = (BACKEND_DIR / p).resolve()
    return p


def _collection_name() -> str:
    if settings and getattr(settings, "collection_name", None):
        return settings.collection_name
    return _env("COLLECTION_NAME", "knowledge_base") or "knowledge_base"


def _client() -> "chromadb.PersistentClient":
    path = _resolve_chroma_dir()
    path.mkdir(parents=True, exist_ok=True)
    log.info("Chroma path: %s", path)
    return chromadb.PersistentClient(path=str(path))


def _ensure_collection(client: "chromadb.PersistentClient", name: str):
    try:
        return client.get_collection(name=name)
    except Exception:
        log.info("creating collection: %s", name)
        return client.create_collection(name=name)


# ---------- Commands ----------
def cmd_init(args):
    client = _client()
    _ensure_collection(client, _collection_name())
    print(
        "[OK] init: path=%s, collection=%s"
        % (_resolve_chroma_dir(), _collection_name())
    )


def cmd_status(args):
    path = _resolve_chroma_dir()
    client = _client()
    try:
        col = client.get_collection(_collection_name())
        count = col.count()
        print(f"[STATUS] path={path}\n  collection={_collection_name()}  count={count}")
    except Exception:
        print(f"[STATUS] path={path}\n  collection={_collection_name()}  (없음)")


def cmd_list(args):
    client = _client()
    cols = client.list_collections()
    print("[LIST] collections:")
    if not cols:
        print("  (none)")
        return
    for c in cols:
        name = getattr(c, "name", None) or getattr(c, "name()", None) or str(c)
        print("  -", name)


def cmd_drop_collection(args):
    client = _client()
    try:
        client.delete_collection(_collection_name())
        print(f"[OK] dropped collection: {_collection_name()}")
    except Exception as e:
        print(f"[WARN] drop failed or not exist: {_collection_name()} ({e})")


def cmd_nuke(args):
    """
    저장소 디렉토리 자체를 통째로 삭제 (되돌릴 수 없음)
    """
    if not args.force:
        print("[ABORT] --force 가 필요합니다. 데이터가 전부 삭제됩니다.")
        return
    path = _resolve_chroma_dir()
    if not path.exists():
        print(f"[OK] nothing to delete: {path}")
        return
    shutil.rmtree(path, ignore_errors=True)
    print(f"[OK] nuked: {path}")


def main():
    parser = argparse.ArgumentParser(description="Chroma DB 초기화/관리")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="디렉토리 및 기본 컬렉션 생성").set_defaults(
        func=cmd_init
    )
    sub.add_parser("status", help="경로/컬렉션 상태 출력").set_defaults(func=cmd_status)
    sub.add_parser("list", help="모든 컬렉션 나열").set_defaults(func=cmd_list)
    sub.add_parser("drop-collection", help="기본 컬렉션만 삭제").set_defaults(
        func=cmd_drop_collection
    )

    p_nuke = sub.add_parser("nuke", help="주의: 저장소 디렉토리 전체 삭제")
    p_nuke.add_argument("--force", action="store_true", help="정말 삭제")
    p_nuke.set_defaults(func=cmd_nuke)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
