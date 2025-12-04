#!/usr/bin/env python3
"""
MSSQL에 QueryLog 테이블 생성 스크립트
"""
import sys
from pathlib import Path

# 상위 디렉토리를 sys.path에 추가
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.db.database import engine
from sqlalchemy import text

def main():
    print("=" * 60)
    print("MSSQL query_logs 테이블 생성")
    print("=" * 60)

    # SQL 스크립트 파일 읽기
    sql_file = Path(__file__).parent / "create_query_logs_mssql.sql"

    if not sql_file.exists():
        print(f"[ERROR] SQL 파일을 찾을 수 없습니다: {sql_file}")
        return 1

    print(f"\n1. SQL 파일 읽기: {sql_file.name}")

    with open(sql_file, "r", encoding="utf-8") as f:
        sql_content = f.read()

    # 주석과 빈 줄 제거하고 문장별로 분리
    sql_statements = []
    current_statement = []

    for line in sql_content.split('\n'):
        # 한 줄 주석 제거
        if line.strip().startswith('--'):
            continue

        # 빈 줄 무시
        if not line.strip():
            continue

        current_statement.append(line)

        # GO 또는 세미콜론으로 문장 구분
        if line.strip().upper() == 'GO' or line.strip().endswith(';'):
            stmt = '\n'.join(current_statement)
            if stmt.strip() and stmt.strip().upper() != 'GO':
                # 세미콜론 제거 (MSSQL은 세미콜론 선택사항)
                stmt = stmt.rstrip(';').strip()
                if stmt:
                    sql_statements.append(stmt)
            current_statement = []

    # 마지막 문장 추가
    if current_statement:
        stmt = '\n'.join(current_statement).strip()
        if stmt:
            sql_statements.append(stmt)

    print(f"2. 실행할 SQL 문장 수: {len(sql_statements)}개\n")

    # 데이터베이스 연결 및 실행
    try:
        with engine.connect() as connection:
            for i, statement in enumerate(sql_statements, 1):
                print(f"   [{i}/{len(sql_statements)}] 실행 중...")

                # 디버그: 실행할 쿼리 일부 출력
                preview = statement[:80].replace('\n', ' ')
                print(f"        {preview}...")

                try:
                    result = connection.execute(text(statement))
                    connection.commit()

                    # SELECT 문이면 결과 출력
                    if statement.strip().upper().startswith('SELECT'):
                        rows = result.fetchall()
                        for row in rows:
                            print(f"        => {dict(row._mapping)}")

                    print(f"        [SUCCESS]")

                except Exception as stmt_err:
                    # 테이블이 이미 존재하는 경우 무시
                    if 'already exists' in str(stmt_err) or '이미 있습니다' in str(stmt_err):
                        print(f"        [SKIP] 이미 존재함")
                    else:
                        raise

        print("\n" + "=" * 60)
        print("[SUCCESS] query_logs 테이블 생성 완료!")
        print("=" * 60)
        print("\n테이블 정보:")
        print("  - 테이블명: query_logs")
        print("  - 컬럼: id, question, answer_id, user_id, created_at")
        print("  - 인덱스: idx_query_logs_created_at, idx_query_logs_user_id")
        print("  - Foreign Key: user_id -> users(id)")

    except Exception as e:
        print("\n" + "=" * 60)
        print(f"[ERROR] 테이블 생성 실패")
        print("=" * 60)
        print(f"\n오류 내용: {e}")
        print("\n해결 방법:")
        print("  1. DATABASE_URL이 올바르게 설정되어 있는지 확인")
        print("  2. MSSQL 서버에 연결할 수 있는지 확인")
        print("  3. users 테이블이 먼저 생성되어 있는지 확인")
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())
