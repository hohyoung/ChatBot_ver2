# 2. 데이터베이스 설계

## 2.1 관계형 DB (사용자 관리)

### 테이블: `users`
```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    email VARCHAR(255),  -- 선택값 (향후 도메인 인증용)
    security_level INTEGER NOT NULL DEFAULT 3,  -- 1=admin, 2=power, 3=user, 4=restricted
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_email ON users(email);
```

**필드 설명:**
- `security_level`: 1=관리자, 2=파워유저(업로드 가능), 3=일반, 4=제한
- `is_active`: 계정 활성화 여부 (비활성화 시 로그인 차단)

---

## 2.2 벡터 DB (ChromaDB) 메타데이터 스키마

### 컬렉션: `knowledge_base`
```python
{
    "chunk_id": str,           # 예: "doc_abc123_0001"
    "doc_id": str,             # 예: "doc_abc123" (해시 기반)
    "doc_hash": str,           # SHA-256 해시 (중복 감지용)
    "doc_type": str,           # 예: "policy-manual"
    "doc_title": str,          # 예: "인사규정"
    "doc_url": str,            # 예: "/static/docs/hr_policy.pdf"
    "doc_relpath": str,        # 예: "public/hr_policy.pdf"
    "visibility": str,         # "public" | "org" | "private"
    "tags": str,               # CSV: "hr-policy,vacation" (검색용)
    "tags_json": str,          # JSON: ["hr-policy", "vacation"] (원본)
    "owner_id": str,           # 업로더 ID (문자열 변환)
    "owner_username": str,     # 업로더 username
    "page_start": int,         # PDF 시작 페이지 (1-base)
    "page_end": int,           # PDF 끝 페이지 (1-base)
    "fb_pos": int,             # 긍정 피드백 수
    "fb_neg": int,             # 부정 피드백 수
    "uploaded_at": str,        # ISO8601 UTC (예: "2025-01-21T12:00:00Z")
}
```

**청크 콘텐츠:**
- `documents`: 실제 텍스트 (최대 1200자)
- `embeddings`: 임베딩 벡터 (1536차원, text-embedding-3-small)

---

## 2.3 피드백 저장소

### JSONL 파일 구조 (`data/feedback.jsonl`)
```json
{
  "chunk_id": "doc_abc123_0001",
  "vote": "up",
  "query": "연차는 몇 일인가요?",
  "query_tags": ["hr-policy", "vacation"],
  "user_id": 1,
  "timestamp": "2025-01-21T12:34:56Z",
  "delta": 0.1,
  "new_boost": 1.2
}
```

---

## 2.4 마스터 인덱스 스키마 (P0-3)

```python
{
    "doc_id": str,
    "doc_title": str,
    "sections": [
        {
            "section_id": str,       # 예: "section_01"
            "title": str,            # 예: "제1장 총칙"
            "keywords": List[str],   # 예: ["총칙", "목적", "정의"]
            "chunk_ids": List[str]   # 이 섹션에 속한 청크들
        }
    ],
    "terms": [
        {
            "term": str,             # 예: "연차휴가"
            "definition": str,       # LLM 추출
            "chunk_ids": List[str]
        }
    ],
    "metadata": {
        "year": int,                 # 예: 2025
        "category": str,             # 예: "인사규정"
        "revision": str              # 예: "2025-01"
    }
}
```
