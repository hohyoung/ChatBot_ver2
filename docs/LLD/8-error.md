# 8. 에러 처리

## 8.1 에러 분류

| 에러 코드 | 설명 | HTTP 상태 | 처리 방법 |
|----------|------|-----------|----------|
| `auth.invalid_token` | JWT 만료/유효하지 않음 | 401 | 재로그인 |
| `auth.insufficient_permission` | 권한 부족 | 403 | 에러 메시지 표시 |
| `doc.duplicate` | 중복 문서 | 409 | 스킵 (로그만) |
| `doc.parse_failed` | 파싱 실패 | 500 | 재시도 또는 수동 처리 |
| `rag.no_results` | 검색 결과 없음 | 200 | "관련 정보를 찾을 수 없습니다" |
| `rag.no_sources` | 근거 누락 | 500 | 재생성 시도 |
| `openai.rate_limit` | 429 Too Many Requests | 429 | 백오프 + 재시도 |
| `openai.api_error` | OpenAI API 오류 | 502 | 사용자에게 안내 |

---

## 8.2 에러 응답 형식

### REST API 에러
```json
{
  "error": {
    "code": "auth.invalid_token",
    "message": "JWT 토큰이 만료되었습니다.",
    "details": {
      "expired_at": "2025-01-21T12:00:00Z"
    }
  }
}
```

### WebSocket 에러
```json
{
  "type": "error",
  "data": {
    "code": "openai.api_error",
    "message": "OpenAI API 호출 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
  }
}
```

---

## 8.3 재시도 로직

### 재시도 대상
- **429 (Rate Limit)**: 지수 백오프 재시도
- **500, 502, 503**: 최대 3회 재시도
- **408 (Timeout)**: 최대 2회 재시도

### 재시도 금지
- **400 (Bad Request)**: 클라이언트 오류
- **401, 403**: 인증/권한 오류
- **404**: 리소스 없음

### 구현

```python
async def retry_with_backoff(
    func: Callable[..., T],
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0
) -> T:
    delay = initial_delay

    for attempt in range(max_retries):
        try:
            return await func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise

            # 재시도 가능한 에러인지 확인
            if hasattr(e, 'status_code') and e.status_code in (429, 500, 502, 503):
                logger.warning(f"Retrying after {delay}s (attempt {attempt+1}/{max_retries})")
                await asyncio.sleep(min(delay, max_delay))
                delay *= backoff_factor
            else:
                raise

# 사용 예시
result = await retry_with_backoff(
    lambda: openai.chat.completions.create(...)
)
```

---

## 8.4 에러 로깅

### 로그 레벨
- **ERROR**: 재시도 후에도 실패한 경우
- **WARNING**: 재시도 중인 경우
- **INFO**: 정상 처리된 에러 (중복 문서 등)

### 로그 형식
```json
{
  "timestamp": "2025-01-21T12:34:56.789Z",
  "level": "ERROR",
  "logger": "app.rag.generator",
  "event": "openai.api_error",
  "error": {
    "type": "RateLimitError",
    "message": "Rate limit exceeded",
    "status_code": 429
  },
  "context": {
    "user_id": 1,
    "question_hash": "abc123",
    "retry_count": 3
  }
}
```

---

## 8.5 사용자 친화적 에러 메시지

### 원칙
1. **명확성**: 무엇이 문제인지 명확히 설명
2. **해결 방법**: 사용자가 취할 수 있는 조치 안내
3. **기술 용어 배제**: 전문 용어 최소화

### 예시

**기술적 메시지 (피하기):**
```
OpenAI API returned 429: Rate limit exceeded for model gpt-4o-mini
```

**사용자 친화적 메시지:**
```
현재 요청이 많아 답변 생성에 지연이 발생하고 있습니다.
잠시 후 다시 시도해 주세요. (약 1분 후)
```

---

## 8.6 에러 모니터링

### 알림 조건
- 5분 동안 10회 이상 같은 에러 발생
- 429 에러율 >10%
- 5xx 에러율 >5%
- 평균 응답 시간 >30초

### 대시보드 지표
- 시간당 에러 수
- 에러 유형별 분포
- 에러율 추이
- 재시도 성공률
