# 9. 배포 및 인프라

## 9.1 Docker Compose (개발 환경)

```yaml
# docker-compose.yml
version: '3.8'

services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    volumes:
      - ./backend:/app
      - ./data:/app/data
      - ./storage:/app/storage
    environment:
      - APP_ENV=dev
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - DATABASE_URL=sqlite:///data/users.db
    command: uvicorn app.main:app --host 0.0.0.0 --reload

  frontend:
    build: ./frontend
    ports:
      - "5173:5173"
    volumes:
      - ./frontend:/app
      - /app/node_modules
    command: npm run dev

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
```

---

## 9.2 프로덕션 아키텍처

```
                    Internet
                        |
                        v
                  [CloudFlare CDN]
                        |
                        v
                  [Load Balancer]
                        |
        ┌───────────────┴───────────────┐
        v                               v
   [Nginx (Reverse Proxy)]    [Nginx (Reverse Proxy)]
        |                               |
        v                               v
   [Uvicorn Workers x4]          [Uvicorn Workers x4]
        |                               |
        └───────────────┬───────────────┘
                        v
              ┌─────────────────┐
              │   Shared Layer  │
              ├─────────────────┤
              │  ChromaDB (PVC) │
              │  Redis (Cache)  │
              │  MSSQL (RDS)    │
              │  S3 (Storage)   │
              └─────────────────┘
```

### 스케일링 전략
- **수평 확장:** Uvicorn workers 증가 (4 → 8 → 16)
- **Auto Scaling:** CPU 사용률 >70% 시 자동 확장
- **로드 밸런싱:** Round-robin (Nginx)

---

## 9.3 CI/CD 파이프라인

### GitHub Actions

```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run backend tests
        run: |
          cd backend
          pip install -r requirements.txt
          pytest
      - name: Run frontend tests
        run: |
          cd frontend
          npm install
          npm run lint

  deploy-staging:
    needs: test
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to staging
        run: |
          ssh staging "cd /app && git pull && docker-compose up -d"

  deploy-production:
    needs: test
    if: startsWith(github.ref, 'refs/tags/v')
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to production
        run: |
          ssh production "cd /app && git pull && docker-compose up -d"
```

---

## 9.4 모니터링 및 로깅

### 로그 스키마 (JSONL)

```json
{
  "timestamp": "2025-01-21T12:34:56.789Z",
  "level": "INFO",
  "logger": "app.router.chat",
  "event": "rag.query",
  "user_id": 1,
  "question_hash": "abc123...",
  "question_length": 25,
  "intent": "info_request",
  "tags": ["hr-policy", "vacation"],
  "candidates_count": 5,
  "used_chunks_count": 3,
  "latency_ms": 1234,
  "latency_breakdown": {
    "tagging_ms": 234,
    "retrieval_ms": 456,
    "generation_ms": 544
  },
  "openai_tokens": {
    "prompt": 512,
    "completion": 128,
    "total": 640
  },
  "cost_usd": 0.0032,
  "sources": ["doc_abc123_0005", "doc_xyz789_0010"]
}
```

### 대시보드 지표 (Grafana)

**트래픽:**
- 시간당 요청 수
- 동시 사용자 수
- 채팅/업로드/검색 분포

**성능:**
- p50/p90/p99 응답 시간
- 첫 토큰 지연 (스트리밍)
- 캐시 적중률

**정확도:**
- 피드백 긍정률
- 오답 신고율
- 검색 결과 없음 비율

**비용:**
- OpenAI API 사용량 (토큰/비용)
- 일간/월간 비용 추이

**에러:**
- 에러율 (429, 5xx)
- 실패한 작업 수
- 재시도 성공률

**시스템:**
- CPU/메모리 사용률
- 디스크 용량
- 네트워크 I/O

---

## 9.5 환경변수 목록

```bash
# .env.example

# App
APP_ENV=dev  # dev | prod
STRICT_ENV=false

# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_CHAT_MODEL=gpt-4o-mini
OPENAI_EMBED_MODEL=text-embedding-3-small

# Vector DB
CHROMA_PERSIST_DIR=./data/chroma
COLLECTION_NAME=knowledge_base

# Auth
JWT_SECRET=your-secret-key-here
JWT_EXPIRES_IN=3600

# Email Domain
INTERNAL_EMAIL_DOMAIN=soosan.com,soosan.co.kr

# CORS
CORS_ALLOW_ORIGINS=http://localhost:5173,http://localhost:3000

# Database
DATABASE_URL=sqlite:///data/users.db

# Redis
REDIS_URL=redis://localhost:6379/0
```

---

## 9.6 백업 및 복구

### 백업 대상
- **사용자 DB**: 일 1회 전체 백업
- **ChromaDB**: 주 1회 전체 백업
- **문서 파일**: 증분 백업 (daily)
- **로그**: 월 1회 아카이브

### 복구 절차
1. 서비스 중지
2. 백업에서 데이터 복원
3. 데이터 무결성 검증
4. 서비스 재시작
5. 헬스 체크

### RTO/RPO 목표
- **RTO (복구 시간 목표)**: 4시간 이내
- **RPO (복구 시점 목표)**: 24시간 이내
