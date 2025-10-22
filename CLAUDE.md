# CLAUDE.md

이 파일은 Claude Code(claude.ai/code)가 이 저장소의 코드를 작업할 때 참고하는 가이드입니다.

## 프로젝트 개요

사내 문서(HR 정책, 매뉴얼 등)를 검색하기 위한 RAG(Retrieval-Augmented Generation) 챗봇 시스템입니다. ChromaDB를 벡터 저장소로 사용하고, OpenAI로 임베딩 및 생성을 처리하며, 인증을 통한 다중 사용자 문서 관리를 지원합니다.

**아키텍처:** FastAPI 백엔드와 React 프론트엔드로 구성된 모노레포

## 핵심 문서 구조

이 프로젝트는 다음 세 가지 핵심 문서를 중심으로 구성됩니다:

@docs/PRD.md
   (제품 요구사항 명세서)
   - 제품 비전, 목표, KPI
   - 핵심 사용자 페르소나 및 시나리오
   - 기능 요구사항 (P0/P1/P2 우선순위)
   - 비기능 요구사항 (성능, 보안, 확장성)
   - 성공 지표 및 릴리즈 계획
   - **용도:** 무엇을 만들어야 하는가? (What & Why)

@docs/LLD/
    (저수준 설계 문서 - 주제별 분할)
   - @docs/LLD/README.md - 개요 및 목차
   - @docs/LLD/1-architecture.md - 시스템 아키텍처 및 기술 스택
   - @docs/LLD/2-database.md - 데이터베이스 스키마
   - @docs/LLD/3-api.md - API 설계
   - @docs/LLD/4-components.md - 핵심 컴포넌트 상세
   - @docs/LLD/5-dataflow.md - 데이터 흐름
   - @docs/LLD/6-security.md - 보안 설계
   - @docs/LLD/7-performance.md - 성능 최적화
   - @docs/LLD/8-error.md - 에러 처리
   - @docs/LLD/9-deployment.md - 배포 및 인프라
   - **용도:** 어떻게 구현할 것인가? (How)
   - **참고:** 필요한 섹션만 선택적으로 참조하세요

@docs/PLAN.md
    (프로젝트 구현 계획 및 로드맵)
   - 전체 로드맵 (M1/M2/M3 마일스톤)
   - 완료/진행 중/남은 작업 항목
   - 각 기능별 담당, 작업 내용, AC (Acceptance Criteria)
   - 의존성 및 위험 관리
   - 릴리즈 체크리스트 및 일정
   - **용도:** 언제, 누가, 어떤 순서로? (When & Who)

**작업 시 참고 순서:**
1. 새 기능 구현 시
   - @docs/PRD.md에서 요구사항 확인
   - @docs/LLD/4-components.md에서 구현 패턴 확인
   - @docs/LLD/3-api.md에서 API 설계 확인
   - @docs/PLAN.md에서 우선순위 및 의존성 확인

2. 버그 수정 시
   - @docs/LLD/4-components.md에서 관련 컴포넌트 구조 파악
   - @docs/LLD/8-error.md에서 에러 처리 전략 확인
   - 코드 수정

3. 성능 개선 시
   - @docs/PRD.md의 NFR 목표 확인
   - @docs/LLD/7-performance.md에서 최적화 전략 확인

4. 데이터베이스 작업 시
   - @docs/LLD/2-database.md에서 스키마 확인

5. 보안 작업 시
   - @docs/LLD/6-security.md에서 인증/권한 확인

6. 배포 작업 시
   - @docs/LLD/9-deployment.md에서 인프라 설정 확인

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

## 상위 수준 아키텍처

### 백엔드 구조

**핵심 RAG 파이프라인** (`/backend/app/`):
- **수집 파이프라인** (`ingest/pipeline.py`): 문서 처리 흐름 조율:
  1. 콘텐츠 해싱 및 중복 감지 (`doc_exists_by_hash`)
  2. 파일 타입 감지 및 파싱 (`parsers/`를 통해 PDF, DOCX, TXT, HTML 처리)
  3. PDF의 경우 페이지 정보를 유지하며 청킹 (`_merge_with_pages`)
  4. LLM을 통한 태그 생성 (`tagger.py`)
  5. 임베딩 생성 및 벡터 저장소 업서트
  6. 작업 상태 추적 (`jobs.py` - job_store)

- **RAG 쿼리 흐름** (`router/chat.py` → `rag/`):
  1. **태깅** (`ingest/tagger.py`): 사용자 질문에서 의미론적 태그 추출
  2. **검색** (`rag/retriever.py`): 임베딩 + 태그 필터로 ChromaDB 쿼리
  3. **생성** (`rag/generator.py`): 청크로 컨텍스트 구성, 시스템 프롬프트와 함께 OpenAI 호출

- **벡터 저장소** (`vectorstore/store.py`):
  - 지연 초기화(lazy initialization)를 사용하는 ChromaDB 싱글톤
  - 메타데이터 정제 (Chroma의 제약사항에 맞춰 리스트/딕셔너리 → JSON 변환)
  - 소유권 인식 작업 (`list_docs_by_owner`, `delete_doc_for_owner`)
  - 소유자/가시성 범위를 고려한 해시 기반 중복 감지

**인증 및 사용자** (`db/`, `router/auth.py`, `router/admin.py`):
- SQLAlchemy 모델, 이중 모드 데이터베이스: SQLite(개발) 또는 MSSQL(프로덕션, `DATABASE_URL` 환경변수 사용)
- JWT 기반 인증 (`services/security.py`)
- 도메인 제한 회원가입 (config의 `INTERNAL_EMAIL_DOMAIN`)
- 역할 기반 접근: 일반 사용자, 관리자, 마스터 관리자

**문서 관리**:
- 업로드 작업: 진행 상황 추적을 통한 비동기 백그라운드 처리
- 저장소: 접근 가능한 파일을 위한 `storage/docs/public/`, `/static/docs/`에 마운트
- 가시성 레벨: `public`, `org`, `private`
- 메타데이터 추적: `uploaded_at` (UTC ISO8601), PDF용 `page_start`/`page_end`

**설정** (`config.py`):
- 모든 설정은 `backend/.env`에서 로드
- 환경 모드: `APP_ENV=dev|prod`, 검증용 `STRICT_ENV=true`
- OpenAI: API 키, 베이스 URL 정규화, 모델 선택
- ChromaDB: 영구 저장 디렉토리, 컬렉션 이름
- JWT: 시크릿, 만료 시간 (`JWT_EXPIRES_IN` 및 레거시 `JWT_EXPIRE_MINUTES` 모두 지원)

### 프론트엔드 구조

**페이지** (`/frontend/src/pages/`):
- `QueryPage.jsx`: WebSocket 연결을 사용하는 메인 채팅 인터페이스
- `UploadPage.jsx`: 작업 진행 폴링을 통한 문서 업로드
- `SettingsPage.jsx`: 사용자 문서 관리 (본인 문서 목록/삭제)
- `AdminSettingsPage.jsx`: 모든 문서를 위한 관리자 패널

**API 레이어** (`/frontend/src/api/`):
- `ws.js`: `/api/chat/`용 WebSocket 클라이언트 (스트리밍 채팅)
- `http.js`: REST API 유틸리티

**라우팅** (`App.jsx`):
- 사이드바 네비게이션과 함께 React Router 사용
- `vite.config.js`의 프록시 설정이 `/api` 및 `/static`을 백엔드로 포워딩

### 데이터 흐름: 문서 업로드

1. 프론트엔드 파일 업로드 → `POST /api/docs/upload` (multipart/form-data)
2. 백엔드가 작업(job) 생성, `storage/uploads/{job_id}/`에 저장
3. `job_id`를 즉시 반환, 백그라운드에서 `process_job()` 시작
4. 프론트엔드가 상태 확인을 위해 `GET /api/docs/jobs/{job_id}` 폴링
5. 파이프라인: 해시 → 중복 체크 → 파싱 → 청킹 → 태깅 → 임베딩 → 업서트 → 정리
6. 최종 파일은 `storage/docs/public/`으로 이동되어 `/static/docs/`에서 제공

### 데이터 흐름: RAG 쿼리

1. 프론트엔드 WebSocket → `WS /api/chat/`
2. 백엔드: `tag_query()`가 질문에서 의미론적 태그 추출
3. `retrieve()`가 쿼리 임베딩 생성, 태그 필터와 함께 ChromaDB 검색
4. `generate_answer()`가 상위 청크 선택 (6000자 제한), 컨텍스트 구성, OpenAI 호출
5. 답변, 출처(페이지 번호가 포함된 청크), 태그, 지연 시간이 포함된 JSON 반환

## 중요한 구현 세부사항

### PDF 페이지 추적
- PDF는 `page_start`/`page_end` 메타데이터가 보존된 채로 청킹됨
- `_pdf_blocks_with_pages()`가 페이지별로 파싱, `_merge_with_pages()`가 페이지 범위 유지
- 비-PDF 문서는 `page_start=None, page_end=None`

### 콘텐츠 해싱 및 중복 제거
- 파일 콘텐츠로부터 SHA256 해시를 파싱 전에 계산
- `doc_id` 형식: `doc_{hash[:12]}`
- 중복 체크는 `(doc_hash, owner_id, visibility)` 범위로 제한되어, 서로 다른 사용자/컨텍스트에서 동일 파일 허용

### 태그 시스템
- LLM으로 문서와 질문 모두에 대해 태그 생성 (`tagger.py`의 `tag_query()`)
- ChromaDB 쿼리에서 메타데이터 필터로 사용되어 검색 정밀도 향상
- 폴백: 생성 실패 시 `["hr-policy"]`

### WebSocket 채팅 프로토콜
- 클라이언트가 텍스트 질문 전송
- 서버가 단일 JSON 이벤트로 응답:
  - `ChatFinalEvent`: `{data: {answer, chunks, answer_id, used_tags, latency_ms}}`
  - `ChatErrorEvent`: `{data: {message, code}}`

### 메타데이터 정제
- ChromaDB는 메타데이터에서 `str|int|float|bool|None`만 허용
- 리스트/딕셔너리 변환: `tags` → CSV 문자열 + 전체 JSON을 포함한 `tags_json`
- `vectorstore/store.py`의 `sanitize_metadata()` 참조

### 환경 설정 경로
- 백엔드 `.env` 로딩은 `config.py` 위치에서 절대 경로 해석 사용
- 경로: `backend/.env` (루트 `.env` 아님)

### 데이터베이스 유연성
- `DATABASE_URL` 환경변수로 SQLite(개발)와 MSSQL(프로덕션) 간 전환
- SQLite 프래그마는 `database.py`에서 WAL 모드, 외래키, 비지 타임아웃으로 설정
- MSSQL은 대량 작업을 위해 `fast_executemany` 사용

### 로깅 및 성능 추적
- `services/logging.py`를 통한 구조화된 로깅
- RAG 파이프라인이 단계별 지연 시간 기록 (태깅, 검색, 생성)
- 최근 브랜치 `test/performance-logging`이 상세한 타이밍 측정 추가

## 현재 브랜치 컨텍스트

**브랜치:** `test/performance-logging`
**수정된 파일:**
- `backend/app/ingest/pipeline.py`
- `backend/app/rag/generator.py`
- `backend/app/router/chat.py`
- `backend/requirements.txt`

이 브랜치는 RAG 파이프라인에 성능 계측을 추가하는 것으로 보입니다. 성능 최적화 작업 시, 세 가지 주요 병목 지점에 집중하세요: 태깅(LLM 호출), 검색(벡터 검색 + 임베딩), 생성(컨텍스트를 포함한 LLM 호출).

## API 통신 규약

### 베이스 경로
- **백엔드 기본 URL:** `http://localhost:8000`
- **프론트엔드 개발 서버:** `http://localhost:5173` (Vite 프록시로 `/api`, `/static` 전달)

### 인증 (JWT)
모든 보호된 엔드포인트는 `Authorization` 헤더 필요:
```
Authorization: Bearer {access_token}
```

**인증 관련 엔드포인트:**

#### `POST /api/auth/register`
회원가입
- **Request Body:**
  ```json
  {
    "name": "홍길동",
    "username": "user123",
    "password": "password123"
  }
  ```
- **Response:**
  ```json
  {
    "access_token": "eyJ...",
    "token_type": "bearer"
  }
  ```

#### `POST /api/auth/login`
로그인
- **Request Body:**
  ```json
  {
    "username": "user123",
    "password": "password123"
  }
  ```
- **Response:** 회원가입과 동일

#### `POST /api/auth/me`
현재 사용자 정보 조회
- **Headers:** `Authorization: Bearer {token}`
- **Response:**
  ```json
  {
    "id": 1,
    "name": "홍길동",
    "username": "user123",
    "security_level": 3,
    "is_active": true
  }
  ```

#### `GET /api/auth/check-username?username=user123`
아이디 사용 가능 여부 확인
- **Response:**
  ```json
  {
    "available": true
  }
  ```

#### `POST /api/auth/logout`
로그아웃 (클라이언트에서 토큰 삭제)
- **Response:**
  ```json
  {
    "ok": true
  }
  ```

### 채팅 (RAG 쿼리)

#### `WS /api/chat/`
WebSocket 기반 질문-답변
- **연결:** `ws://localhost:8000/api/chat/`
- **클라이언트 → 서버:** 텍스트 질문 전송
- **서버 → 클라이언트:** JSON 이벤트

**성공 응답:**
```json
{
  "type": "final",
  "data": {
    "answer": "답변 텍스트...",
    "chunks": [
      {
        "chunk_id": "doc_abc123_0001",
        "doc_id": "doc_abc123",
        "doc_title": "인사규정",
        "doc_type": "policy-manual",
        "content": "청크 내용...",
        "visibility": "public",
        "tags": ["hr-policy", "vacation"],
        "doc_url": "/static/docs/hr_policy.pdf",
        "page_start": 3,
        "page_end": 5,
        "owner_username": "admin"
      }
    ],
    "answer_id": "ans_xyz789",
    "used_tags": ["hr-policy", "vacation"],
    "latency_ms": 1234,
    "version": "v1",
    "created_at": "2025-01-15T12:34:56.789Z"
  }
}
```

**에러 응답:**
```json
{
  "type": "error",
  "data": {
    "message": "에러 메시지",
    "code": "internal"
  }
}
```

### 문서 관리

#### `POST /api/docs/upload`
문서 업로드 (multipart/form-data)
- **Headers:** `Authorization: Bearer {token}`
- **Form Fields:**
  - `files`: 파일 배열 (required)
  - `doc_type`: 문서 타입 (optional, 기본값: "policy-manual")
  - `visibility`: 가시성 레벨 (optional, 기본값: "public")
- **Response (202 Accepted):**
  ```json
  {
    "job_id": "ingest_abc123",
    "accepted": 3,
    "skipped": 1
  }
  ```

#### `GET /api/docs/{job_id}/status`
업로드 작업 상태 확인
- **Response:**
  ```json
  {
    "status": "running",
    "processed": 2,
    "errors": ["file1.pdf: parsing error"]
  }
  ```
  - `status`: `"pending"` | `"running"` | `"succeeded"` | `"failed"`

#### `GET /api/docs/my`
내 문서 목록 조회
- **Headers:** `Authorization: Bearer {token}`
- **Response:**
  ```json
  {
    "items": [
      {
        "doc_id": "doc_abc123",
        "doc_title": "인사규정",
        "visibility": "public",
        "doc_url": "/static/docs/hr_policy.pdf",
        "uploaded_at": "2025-01-15T12:00:00Z",
        "chunk_count": 15
      }
    ]
  }
  ```

#### `DELETE /api/docs/my/{doc_id}`
내 문서 삭제
- **Headers:** `Authorization: Bearer {token}`
- **Response:**
  ```json
  {
    "ok": true,
    "deleted_chunks": 15,
    "file_delete": {
      "requested": 1,
      "deleted": 1,
      "errors": []
    }
  }
  ```

#### `GET /api/docs/locate`
PDF 내 텍스트 위치 찾기 (페이지 번호 반환)
- **Query Parameters:**
  - `doc_url` 또는 `url`: 문서 URL (예: `/static/docs/file.pdf`)
  - `doc_relpath` 또는 `relpath`: 상대 경로 (폴백, 예: `public/file.pdf`)
  - `q`: 찾을 텍스트 스니펫
- **Response:**
  ```json
  {
    "page": 5,
    "url": "http://localhost:8000/static/docs/file.pdf#page=5"
  }
  ```
  - 텍스트를 찾지 못하면 `page: null`, `url`은 기본 URL 반환

### 피드백

#### `POST /api/feedback`
청크 피드백 제출 (긍정/부정)
- **Request Body:**
  ```json
  {
    "chunk_id": "doc_abc123_0001",
    "vote": "up",
    "query": "연차 규정은?",
    "tag_context": ["hr-policy", "vacation"]
  }
  ```
  - `vote`: `"up"` | `"down"`
  - `query`: 질문 텍스트 (optional, 태그 자동 생성용)
  - `tag_context`: 컨텍스트 태그 (optional)
- **Response:**
  ```json
  {
    "ok": true,
    "updated": {
      "chunk_id": "doc_abc123_0001",
      "delta": 0.1,
      "new_boost": 1.2,
      "meta": {
        "fb_pos": 3,
        "fb_neg": 1,
        "factor": 1.2
      }
    }
  }
  ```

### 관리자 API

**권한 요구사항:** `security_level: 1` (관리자)

#### `GET /api/admin/users`
사용자 목록 조회
- **Headers:** `Authorization: Bearer {token}`
- **Query Parameters:**
  - `q`: 검색어 (username 또는 name 부분 일치)
  - `limit`: 최대 개수 (기본값: 100)
  - `offset`: 오프셋 (기본값: 0)
- **Response:**
  ```json
  [
    {
      "id": 1,
      "name": "홍길동",
      "username": "user123",
      "security_level": 3,
      "is_active": true
    }
  ]
  ```

#### `PATCH /api/admin/users/{user_id}`
사용자 정보 수정
- **Headers:** `Authorization: Bearer {token}`
- **Request Body (모든 필드 optional):**
  ```json
  {
    "name": "새이름",
    "username": "newusername",
    "password": "newpassword",
    "security_level": 2,
    "is_active": false
  }
  ```
  - `security_level`: `1` (관리자), `2` (파워유저), `3` (일반), `4` (제한)

#### `DELETE /api/admin/users/{user_id}`
사용자 삭제
- **Headers:** `Authorization: Bearer {token}`
- **Response:**
  ```json
  {
    "ok": true
  }
  ```

#### `GET /api/admin/docs`
전체 문서 목록 조회
- **Headers:** `Authorization: Bearer {token}`
- **Query Parameters:**
  - `q`: 검색어 (제목/업로더 이름/아이디 부분 일치)
  - `limit`: 최대 개수 (기본값: 500)
  - `offset`: 오프셋 (기본값: 0)
- **Response:**
  ```json
  {
    "items": [
      {
        "doc_id": "doc_abc123",
        "doc_title": "인사규정",
        "visibility": "public",
        "owner_id": 1,
        "owner_username": "admin",
        "owner_name": "관리자",
        "doc_url": "/static/docs/hr_policy.pdf",
        "uploaded_at": "2025-01-15T12:00:00Z",
        "chunk_count": 15
      }
    ]
  }
  ```

#### `DELETE /api/admin/docs/{doc_id}`
문서 삭제 (모든 사용자의 문서)
- **Headers:** `Authorization: Bearer {token}`
- **Response:**
  ```json
  {
    "ok": true,
    "deleted_chunks": 15,
    "file_delete": {
      "requested": 1,
      "deleted": 1,
      "errors": []
    }
  }
  ```

### 헬스 체크

#### `GET /health` 또는 `GET /api/health`
서버 상태 확인
- **Response:**
  ```json
  {
    "status": "ok",
    "env": "dev",
    "vector_collection": "knowledge_base",
    "openai_model": "gpt-4o-mini"
  }
  ```

## 주요 제약사항 및 패턴

1. **로깅은 항상 `get_logger(__name__)` 사용** - 중앙화된 로깅 설정
2. **청크 콘텐츠 제한:** 청크당 1200자 (PDF), 컨텍스트 윈도우: 총 6000자
3. **ChromaDB 메타데이터:** 업서트 전 `sanitize_metadata()` 사용, JSON 직렬화 처리
4. **Async/await:** 모든 RAG 작업 (tag, retrieve, generate)은 비동기
5. **작업 정리:** 성공적으로 처리된 파일은 스테이징에서 삭제, 실패한 파일은 `_failed/`로 이동
6. **URL 규약:** `doc_relpath`는 항상 `public/`으로 시작, `doc_url`은 항상 `/static/docs/{rel_core}`
7. **소유자 격리:** 사용자는 자신의 문서만 삭제 가능; 관리자는 `delete_doc_any()`를 통해 모든 문서 삭제 가능




## 깃허브를 위한 지침
1. **저장소 정보:**
   - GITHUB 저장소 주소: https://github.com/hohyoung/vacationChecklist
   - GIT HUB의 Personal Access Token: 환경변수 사용 (보안상 여기에 기록 금지)

2. **GitHub CLI 사용:**
   - gh CLI를 사용하여 GitHub 작업 처리
   - 인증은 `gh auth login` 사용

3. **푸시 전략:**
   - HTTP 버퍼 크기 증가 필요 시: `git config http.postBuffer 524288000`
   - 큰 변경사항은 작은 커밋으로 분할하여 푸시
   - 에러 발생 시 작은 변경사항만 포함하는 새 커밋 생성

4. **진행상황 관리:**
   - @docs/PLAN.md 파일의 작업이 한 단계 진행될 때마다 체크리스트 업데이트
   - 변경사항을 GitHub에 반영