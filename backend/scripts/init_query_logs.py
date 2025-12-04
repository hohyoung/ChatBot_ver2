#!/usr/bin/env python3
"""
Query Logs 테이블 초기화 스크립트

QueryLog 테이블을 생성합니다.
"""
import sys
from pathlib import Path

# 상위 디렉토리를 sys.path에 추가
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.db.database import engine, Base
from app.db.models import QueryLog

def main():
    print("QueryLog 테이블 생성 시작...")

    try:
        # QueryLog 테이블만 생성
        QueryLog.__table__.create(engine, checkfirst=True)
        print("[SUCCESS] QueryLog 테이블 생성 완료")
        print(f"   - 테이블명: {QueryLog.__tablename__}")
        print(f"   - 컬럼: id, question, answer_id, user_id, created_at")
        print(f"   - 인덱스: created_at, user_id")

    except Exception as e:
        print(f"[ERROR] 테이블 생성 실패: {e}")
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())
