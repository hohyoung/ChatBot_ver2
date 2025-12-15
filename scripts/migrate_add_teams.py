#!/usr/bin/env python3
"""
팀별 문서 격리 기능을 위한 DB 마이그레이션 스크립트

변경 사항:
1. teams 테이블 생성
2. users 테이블에 team_id 컬럼 추가

사용법:
    python scripts/migrate_add_teams.py
"""
from __future__ import annotations
import sys
from pathlib import Path

# repo root(chatBot_ver2)와 backend를 sys.path에 추가
ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from sqlalchemy import text, inspect
from app.db.database import engine, Base
from app.db import models  # noqa: F401 - 모델 import 필요


def check_table_exists(table_name: str) -> bool:
    """테이블 존재 여부 확인"""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def check_column_exists(table_name: str, column_name: str) -> bool:
    """컬럼 존재 여부 확인"""
    inspector = inspect(engine)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def migrate_sqlite():
    """SQLite용 마이그레이션"""
    with engine.connect() as conn:
        # 1. teams 테이블 생성 (없으면)
        if not check_table_exists("teams"):
            print("[1/3] teams 테이블 생성 중...")
            conn.execute(text("""
                CREATE TABLE teams (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(50) NOT NULL UNIQUE,
                    description VARCHAR(200),
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.commit()
            print("      teams 테이블 생성 완료")
        else:
            print("[1/3] teams 테이블이 이미 존재합니다.")

        # 2. users 테이블에 team_id 컬럼 추가 (없으면)
        if not check_column_exists("users", "team_id"):
            print("[2/3] users.team_id 컬럼 추가 중...")
            conn.execute(text("""
                ALTER TABLE users ADD COLUMN team_id INTEGER REFERENCES teams(id)
            """))
            conn.commit()
            print("      users.team_id 컬럼 추가 완료")
        else:
            print("[2/3] users.team_id 컬럼이 이미 존재합니다.")

        # 3. 인덱스 생성 (없으면)
        print("[3/3] 인덱스 확인 중...")
        try:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_users_team_id ON users(team_id)
            """))
            conn.commit()
            print("      인덱스 생성/확인 완료")
        except Exception as e:
            print(f"      인덱스 생성 스킵 (이미 존재할 수 있음): {e}")


def migrate_mssql():
    """MSSQL용 마이그레이션"""
    with engine.connect() as conn:
        # 1. teams 테이블 생성 (없으면)
        if not check_table_exists("teams"):
            print("[1/3] teams 테이블 생성 중...")
            conn.execute(text("""
                CREATE TABLE teams (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    name NVARCHAR(50) NOT NULL UNIQUE,
                    description NVARCHAR(200),
                    is_active BIT NOT NULL DEFAULT 1,
                    created_at DATETIME2 DEFAULT SYSUTCDATETIME()
                )
            """))
            conn.commit()
            print("      teams 테이블 생성 완료")
        else:
            print("[1/3] teams 테이블이 이미 존재합니다.")

        # 2. users 테이블에 team_id 컬럼 추가 (없으면)
        if not check_column_exists("users", "team_id"):
            print("[2/3] users.team_id 컬럼 추가 중...")
            conn.execute(text("""
                ALTER TABLE users ADD team_id INT NULL
            """))
            conn.commit()

            # 외래키 제약 추가
            conn.execute(text("""
                ALTER TABLE users ADD CONSTRAINT FK_users_team_id
                FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE SET NULL
            """))
            conn.commit()
            print("      users.team_id 컬럼 및 외래키 추가 완료")
        else:
            print("[2/3] users.team_id 컬럼이 이미 존재합니다.")

        # 3. 인덱스 생성 (없으면)
        print("[3/3] 인덱스 확인 중...")
        try:
            # 인덱스 존재 여부 확인
            result = conn.execute(text("""
                SELECT 1 FROM sys.indexes
                WHERE name = 'idx_users_team_id' AND object_id = OBJECT_ID('users')
            """))
            if not result.fetchone():
                conn.execute(text("""
                    CREATE INDEX idx_users_team_id ON users(team_id)
                """))
                conn.commit()
                print("      인덱스 생성 완료")
            else:
                print("      인덱스가 이미 존재합니다.")
        except Exception as e:
            print(f"      인덱스 생성 스킵: {e}")


def create_default_team():
    """기본 팀 생성 (인사팀)"""
    with engine.connect() as conn:
        # 기본 팀이 없으면 생성
        result = conn.execute(text("SELECT id FROM teams WHERE name = '인사팀'"))
        if not result.fetchone():
            print("[추가] 기본 팀 '인사팀' 생성 중...")
            if str(engine.url).startswith("sqlite"):
                conn.execute(text("""
                    INSERT INTO teams (name, description) VALUES ('인사팀', '인사 관련 문서')
                """))
            else:
                conn.execute(text("""
                    INSERT INTO teams (name, description) VALUES (N'인사팀', N'인사 관련 문서')
                """))
            conn.commit()
            print("      기본 팀 생성 완료")
        else:
            print("[추가] 기본 팀 '인사팀'이 이미 존재합니다.")


def main():
    print("=" * 60)
    print("팀별 문서 격리 기능 - DB 마이그레이션")
    print("=" * 60)
    print(f"Database URL: {engine.url}")
    print()

    # DB 유형에 따라 마이그레이션 실행
    if str(engine.url).startswith("sqlite"):
        print("[SQLite 모드]")
        migrate_sqlite()
    else:
        print("[MSSQL 모드]")
        migrate_mssql()

    print()

    # 기본 팀 생성
    create_default_team()

    print()
    print("=" * 60)
    print("마이그레이션 완료!")
    print("=" * 60)


if __name__ == "__main__":
    main()
