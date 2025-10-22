# 3. API 설계

## 3.1 WebSocket 프로토콜 (채팅)

### 연결: `WS /api/chat/`

**클라이언트 → 서버 (텍스트):**
```
"연차는 몇 일인가요?"
```

**서버 → 클라이언트 (JSON 이벤트):**

### 타입 1: 토큰 이벤트 (스트리밍)
```json
{
  "type": "token",
  "token": "입사 "
}
```

### 타입 2: 최종 이벤트
```json
{
  "type": "final",
  "data": {
    "answer": "입사 2년차의 경우 연차는 15일입니다.",
    "chunks": [
      {
        "chunk_id": "doc_abc123_0005",
        "doc_id": "doc_abc123",
        "doc_title": "인사규정",
        "content": "제10조 (연차휴가) 1. 입사 2년차: 15일...",
        "page_start": 3,
        "page_end": 3,
        "doc_url": "/static/docs/hr_policy.pdf"
      }
    ],
    "answer_id": "ans_xyz789",
    "used_tags": ["hr-policy", "vacation"],
    "latency_ms": 1234,
    "version": "v1",
    "created_at": "2025-01-21T12:34:56.789Z"
  }
}
```

### 타입 3: 에러 이벤트
```json
{
  "type": "error",
  "data": {
    "message": "OpenAI API 오류",
    "code": "internal"
  }
}
```

---

## 3.2 REST API 엔드포인트

### 인증 (`/api/auth/`)
- `POST /register` - 회원가입
- `POST /login` - 로그인
- `POST /me` - 사용자 정보 조회
- `GET /check-username` - 아이디 중복 체크
- `POST /logout` - 로그아웃

### 문서 관리 (`/api/docs/`)
- `POST /upload` - 문서 업로드 (multipart/form-data)
- `GET /{job_id}/status` - 업로드 작업 상태
- `GET /my` - 내 문서 목록
- `DELETE /my/{doc_id}` - 내 문서 삭제
- `GET /locate` - PDF 내 텍스트 위치 찾기
- `GET /search` - 문서 검색 (P0-4)

### 피드백 (`/api/feedback`)
- `POST /` - 피드백 제출

### FAQ (`/api/faq`) (P0-3)
- `GET /` - FAQ 목록 조회

### 관리자 (`/api/admin/`)
- `GET /users` - 사용자 목록
- `PATCH /users/{user_id}` - 사용자 수정
- `DELETE /users/{user_id}` - 사용자 삭제
- `GET /docs` - 전체 문서 목록
- `DELETE /docs/{doc_id}` - 문서 삭제

### 헬스 체크
- `GET /health` - 서버 상태

---

## 3.3 주요 요청/응답 예시

### 문서 업로드
**Request:**
```http
POST /api/docs/upload
Authorization: Bearer {token}
Content-Type: multipart/form-data

files: [file1.pdf, file2.pdf]
doc_type: "policy-manual"
visibility: "public"
```

**Response (202 Accepted):**
```json
{
  "job_id": "ingest_abc123",
  "accepted": 2,
  "skipped": 0
}
```

### 채팅 (WebSocket)
**Client → Server:**
```
연차는 몇 일인가요?
```

**Server → Client (Final):**
```json
{
  "type": "final",
  "data": {
    "answer": "입사 2년차의 경우 연차는 **15일**입니다...",
    "chunks": [...],
    "answer_id": "ans_xyz789",
    "used_tags": ["hr-policy", "vacation"],
    "latency_ms": 1234
  }
}
```

### 피드백 제출
**Request:**
```http
POST /api/feedback
Authorization: Bearer {token}
Content-Type: application/json

{
  "chunk_id": "doc_abc123_0001",
  "vote": "up",
  "query": "연차 규정은?"
}
```

**Response:**
```json
{
  "ok": true,
  "updated": {
    "chunk_id": "doc_abc123_0001",
    "delta": 0.1,
    "new_boost": 1.2
  }
}
```
