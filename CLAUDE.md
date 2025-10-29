# CLAUDE.md

이 파일은 Claude Code가 이 프로젝트를 작업할 때 참고하는 **가이드맵**입니다.
구체적인 구현 상세는 `docs/` 폴더의 문서들을 참조하세요.

## 프로젝트 개요

**이름:** 사내 규정 RAG 챗봇 시스템
**목표:** 사내 문서(HR 정책, 매뉴얼 등)를 검색하고 정확한 답변 제공
**기술:** FastAPI 백엔드 + React 프론트엔드, ChromaDB 벡터 저장소, OpenAI API

## 문서 구조 (필요할 때만 참조)

이 프로젝트는 3가지 핵심 문서로 구성됩니다:

| 문서 | 용도 | 언제 참조? |
|------|------|----------|
| **@docs/PRD.md** | 제품 요구사항 명세 (What & Why) | 새 기능 구현 시 요구사항 확인 |
| **@docs/LLD/** | 저수준 설계 (How) - 9개 파일로 분할 | 구현 방법, API, 아키텍처 확인 |
| **@docs/PLAN.md** | 구현 계획 및 로드맵 (When & Who) | 우선순위, 일정, 진행상황 확인 |

**LLD 문서 목록:**
- `1-architecture.md` - 시스템 아키텍처
- `2-database.md` - DB 스키마
- `3-api.md` - API 설계
- `4-components.md` - 핵심 컴포넌트
- `5-dataflow.md` - 데이터 흐름
- `6-security.md` - 보안
- `7-performance.md` - 성능 최적화
- `8-error.md` - 에러 처리
- `9-deployment.md` - 배포

## 작업별 참조 가이드

| 작업 유형 | 참조 문서 |
|----------|----------|
| **새 기능 구현** | PRD.md → LLD/4-components.md → LLD/3-api.md |
| **버그 수정** | LLD/4-components.md → LLD/8-error.md |
| **성능 개선** | PRD.md (NFR) → LLD/7-performance.md |
| **DB 작업** | LLD/2-database.md |
| **보안 작업** | LLD/6-security.md |
| **배포 작업** | LLD/9-deployment.md |

## 개발 명령어

### 백엔드 (FastAPI)

```bash
# 백엔드 디렉토리로 이동
cd backend

# 의존성 설치
pip install -r requirements.txt

# 개발 서버 실행 (기본: http://localhost:8000)
uvicorn app.main:app --reload

# API 문서 접근
# http://localhost:8000/docs

# 헬스 체크
# GET http://localhost:8000/health
```

### 프론트엔드 (React + Vite)

```bash
# 프론트엔드 디렉토리로 이동
cd frontend

# 의존성 설치
npm install

# 개발 서버 실행 (기본: http://localhost:5173)
npm run dev

# 프로덕션 빌드
npm run build

# 린트
npm run lint
```

### 테스트 및 유틸리티

```bash
# /scripts 디렉토리에 위치
python scripts/test_chat.py          # 채팅 기능 테스트
python scripts/test_search.py        # 검색/리트리버 테스트
python scripts/test_connection.py    # 데이터베이스 연결 테스트
python scripts/create_master_user.py # 초기 관리자 생성
python scripts/init_users_db.py      # 사용자 데이터베이스 초기화
python scripts/db_manage.py          # 데이터베이스 관리 유틸리티
```

## 주요 디렉토리 구조

```
backend/
  app/
    ingest/     # 문서 수집 파이프라인
    rag/        # RAG 쿼리 (retriever, generator)
    router/     # API 엔드포인트
    db/         # 데이터베이스 모델
    vectorstore/# ChromaDB 관리
    services/   # 공통 서비스 (logging, security)
  storage/      # 파일 저장소
  data/         # DB 파일

frontend/
  src/
    pages/      # QueryPage, UploadPage, SettingsPage
    api/        # WebSocket, HTTP 클라이언트
    components/ # 재사용 컴포넌트

docs/           # 프로젝트 문서
```

**상세한 아키텍처 설명:** @docs/LLD/1-architecture.md 참조

## 현재 브랜치

**브랜치:** `test/performance-logging`
**주요 변경:** RAG 파이프라인 성능 계측 추가 (타이밍, 토큰 사용량)
**성능 병목:** 태깅(LLM) → 검색(벡터) → 생성(LLM)

## 핵심 기술 정보

### API
- **베이스 URL:** http://localhost:8000
- **인증:** JWT Bearer Token
- **주요 엔드포인트:**
  - `WS /api/chat/` - WebSocket 채팅
  - `POST /api/docs/upload` - 문서 업로드
  - `GET /api/docs/my` - 내 문서 목록
  - `POST /api/feedback` - 피드백 제출
  - 관리자: `/api/admin/*`

**상세 API 명세:** @docs/LLD/3-api.md 참조

### 데이터베이스
- **관계형:** SQLite (개발) / MSSQL (프로덕션)
- **벡터:** ChromaDB (컬렉션: knowledge_base)
- **캐시:** Redis (OTP, 검색 결과)

**상세 스키마:** @docs/LLD/2-database.md 참조

## 코딩 규칙

1. **로깅:** `get_logger(__name__)` 사용
2. **비동기:** 모든 RAG 작업은 async/await
3. **메타데이터:** ChromaDB 업서트 전 `sanitize_metadata()` 필수
4. **환경변수:** `backend/.env`에서 로드 (루트 `.env` 아님)

**상세 제약사항:** @docs/LLD/4-components.md, @docs/LLD/7-performance.md 참조

---

## GitHub 작업 지침

**저장소:** https://github.com/hohyoung/vacationChecklist
**주요 브랜치:** main (PR 대상)

### 커밋 및 푸시
- gh CLI 사용 권장
- 큰 변경사항은 작은 커밋으로 분할
- 진행상황은 @docs/PLAN.md에 체크리스트 업데이트

### PR 생성 시
- @docs/PLAN.md의 완료된 항목 확인
- 커밋 메시지에 관련 이슈/작업 명시

---

## 마지막으로

이 문서는 **가이드맵**입니다. 구체적인 구현 상세는 `docs/` 폴더의 문서들을 참조하세요:
- **PRD.md** - 무엇을, 왜?
- **LLD/** - 어떻게?
- **PLAN.md** - 언제, 누가?