# 6. 보안 설계

## 6.1 인증 플로우

### 회원가입 (사내 메일 인증, P0-6)

```
1. [Client] POST /api/auth/internal-signup {email}
2. [Backend] 도메인 검증 (@soosan.com, @soosan.co.kr)
3. [Backend] OTP 생성 (6자리) → 이메일 전송
4. [Backend] Redis에 임시 저장 (TTL 10분)
5. [Client] POST /api/auth/internal-verify {email, code, username, password}
6. [Backend] OTP 검증 → 사용자 생성 → JWT 발급
```

### 로그인

```
1. [Client] POST /api/auth/login {username, password}
2. [Backend] 사용자 조회 + 비밀번호 검증 (bcrypt)
3. [Backend] JWT 생성 (exp: 3600초)
4. [Client] localStorage에 토큰 저장
```

### 인증 헤더

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

---

## 6.2 권한 검증 (RBAC)

### 권한 매트릭스

| 기능 | 일반(3) | 파워유저(2) | 관리자(1) |
|-----|--------|------------|----------|
| 채팅 | ✓ | ✓ | ✓ |
| 문서 검색 | ✓ | ✓ | ✓ |
| 문서 업로드 | ✗ | ✓ | ✓ |
| 내 문서 삭제 | ✗ | ✓ | ✓ |
| 타인 문서 삭제 | ✗ | ✗ | ✓ |
| 사용자 관리 | ✗ | ✗ | ✓ |

### 구현 (Dependency)

```python
def require_level(min_level: int):
    def decorator(user: AuthUser = Depends(current_user)):
        if user.security_level > min_level:
            raise HTTPException(403, "권한이 부족합니다.")
        return user
    return decorator

# 사용 예시
@router.post("/upload")
async def upload(user: AuthUser = Depends(require_level(2))):
    ...
```

---

## 6.3 데이터 암호화

### 전송 중 암호화
- **HTTPS/WSS**: TLS 1.2+
- **인증서**: Let's Encrypt 또는 사내 CA

### 저장 데이터 암호화
- **비밀번호**: bcrypt (cost factor: 12)
- **JWT**: HS256 (시크릿 키: 환경변수)
- **문서**: 평문 (민감 정보 없음 가정)

---

## 6.4 감사 로그

### 로그 형식 (JSONL)

```json
{
  "timestamp": "2025-01-21T12:34:56Z",
  "event": "document.upload",
  "user_id": 1,
  "username": "admin",
  "doc_id": "doc_abc123",
  "visibility": "public",
  "ip_address": "192.168.1.100",
  "user_agent": "Mozilla/5.0..."
}
```

### 기록 대상

- 로그인/로그아웃
- 문서 업로드/삭제
- 사용자 생성/수정/삭제
- 관리자 작업 (권한 변경 등)
- API 키 사용 (OpenAI)

---

## 6.5 보안 체크리스트

### 입력 검증
- [ ] SQL Injection 방지 (SQLAlchemy 파라미터 바인딩)
- [ ] XSS 방지 (DOMPurify)
- [ ] CSRF 방지 (SameSite 쿠키)
- [ ] 파일 업로드 검증 (확장자, MIME 타입, 크기)

### 인증/권한
- [ ] JWT 만료 시간 설정
- [ ] 비밀번호 정책 (최소 8자)
- [ ] 계정 잠금 (5회 실패 시)
- [ ] 역할 기반 접근 제어

### 데이터 보호
- [ ] 민감 정보 로깅 금지 (비밀번호, 토큰)
- [ ] 환경변수로 시크릿 관리
- [ ] HTTPS 강제 (프로덕션)

### 모니터링
- [ ] 실패한 로그인 시도 추적
- [ ] 비정상적인 API 사용 패턴 감지
- [ ] 권한 변경 알림
