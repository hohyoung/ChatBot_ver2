from __future__ import annotations

import os
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session

# ─────────────────────────────────────────────────────────
# 1) DATABASE_URL이 있으면 MSSQL(또는 지정 DB)로 연결
#    없으면 로컬 SQLite로 폴백
# ─────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    # 로컬 개발용 SQLite 폴백 (기존 경로 유지)
    APP_DIR = Path(__file__).resolve().parents[1]
    DB_DIR = APP_DIR / "db"
    DB_DIR.mkdir(parents=True, exist_ok=True)
    DB_PATH = DB_DIR / "users.sqlite3"
    DATABASE_URL = f"sqlite:///{DB_PATH.as_posix()}"

# SQLAlchemy Engine 옵션
engine_args: dict = dict(pool_pre_ping=True)

# MSSQL(pyodbc)일 때 대량 insert 성능옵션(선택)
if DATABASE_URL.startswith("mssql+pyodbc://"):
    engine_args["fast_executemany"] = True

engine: Engine = create_engine(DATABASE_URL, **engine_args)

# SQLite일 때만 PRAGMA 안전성 설정
if DATABASE_URL.startswith("sqlite:///"):

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA synchronous=FULL;")
        cur.execute("PRAGMA busy_timeout=30000;")
        cur.execute("PRAGMA foreign_keys=ON;")
        cur.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI 의존성: 요청 생명주기 동안 DB 세션 제공"""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
