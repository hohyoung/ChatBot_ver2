# 10. 팀별 문서 격리 기능 설계

## 10.1 개요

### 목적
기존 인사팀 전용 시스템을 다른 팀(경영팀, IT팀 등)도 사용할 수 있도록 확장하되,
**팀별로 문서를 격리**하여 질의 시 해당 팀의 문서만 참조하도록 함.

### 핵심 요구사항
| # | 요구사항 | 설명 |
|---|---------|------|
| 1 | 팀 관리 | 관리자가 팀을 추가/삭제할 수 있어야 함 |
| 2 | 유저-팀 배정 | 관리자가 유저의 팀 정보를 수정할 수 있어야 함 |
| 3 | 업로드 제한 | 팀 소속이 배정된 유저만 문서 업로드 가능 (자신의 소속팀에 업로드) |
| 4 | 질의 시 팀 선택 | 유저가 질의할 때 답변팀을 선택할 수 있어야 함 |

### 설계 원칙
- **메타데이터 필터 방식**: 벡터 DB를 여러 개 만들지 않고, 단일 컬렉션에서 `team_id` 메타데이터로 격리
- **유연한 팀 관리**: 관리자가 팀을 동적으로 추가/삭제 가능
- **단일 팀 소속**: 사용자는 하나의 팀에만 소속 (다대다 관계 불필요)

---

## 10.2 데이터베이스 스키마 변경

### 10.2.1 신규 테이블: `teams`

```sql
CREATE TABLE teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(50) NOT NULL UNIQUE,      -- 팀 이름 (예: "인사팀", "경영팀")
    description VARCHAR(200),               -- 팀 설명 (선택)
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 초기 데이터: 기존 문서를 위한 기본 팀
INSERT INTO teams (name, description) VALUES ('인사팀', '인사 관련 문서');
```

### 10.2.2 기존 테이블 변경: `users`

```sql
-- team_id 컬럼 추가 (외래키, NULL 허용, 팀 삭제 시 NULL로 설정)
ALTER TABLE users ADD COLUMN team_id INTEGER
    REFERENCES teams(id) ON DELETE SET NULL;

-- 인덱스 추가
CREATE INDEX idx_users_team_id ON users(team_id);
```

**필드 설명:**
- `team_id`: 사용자 소속 팀 (NULL = 팀 미배정 → 업로드 불가)

**ON DELETE SET NULL 동작:**
- 팀이 삭제되면 해당 팀 소속 유저들의 `team_id`가 자동으로 `NULL`로 변경
- 유저는 삭제되지 않고 "팀 미배정" 상태가 됨
- 관리자가 다시 다른 팀을 배정해줘야 문서 업로드 가능

### 10.2.3 ERD

```
┌─────────────┐         ┌─────────────┐
│   teams     │         │   users     │
├─────────────┤         ├─────────────┤
│ id (PK)     │◄────────│ team_id (FK)│
│ name        │    1:N  │ id (PK)     │
│ description │         │ name        │
│ is_active   │         │ username    │
│ created_at  │         │ ...         │
└─────────────┘         └─────────────┘
```

---

## 10.3 벡터 DB 메타데이터 확장

### 10.3.1 ChromaDB 메타데이터 스키마 변경

기존 메타데이터에 `team_id` 필드 추가:

```python
{
    # 기존 필드
    "chunk_id": str,
    "doc_id": str,
    "doc_title": str,
    "owner_id": str,
    "visibility": str,
    ...

    # 신규 필드
    "team_id": str,         # 팀 ID (문자열로 저장)
    "team_name": str,       # 팀 이름 (검색/표시용)
}
```

### 10.3.2 기존 문서 마이그레이션

기존 문서(team_id 없음)는 기본 팀에 배정하거나, 전체 공개로 처리:

```python
# 마이그레이션 전략 A: 기본 팀 배정
default_team_id = "1"  # 인사팀

# 마이그레이션 전략 B: team_id 없으면 모든 팀에서 검색 가능 (현재 방식 유지)
# → 점진적 마이그레이션 가능
```

**권장**: 전략 B (하위 호환성 유지)

---

## 10.4 API 설계

### 10.4.1 팀 관리 API (`/api/admin/teams/`)

| 메서드 | 경로 | 설명 | 권한 |
|--------|------|------|------|
| GET | `/api/admin/teams` | 팀 목록 조회 | 관리자 |
| POST | `/api/admin/teams` | 팀 생성 | 관리자 |
| PATCH | `/api/admin/teams/{team_id}` | 팀 수정 | 관리자 |
| DELETE | `/api/admin/teams/{team_id}` | 팀 삭제 | 관리자 |

#### 요청/응답 예시

**팀 목록 조회:**
```http
GET /api/admin/teams
Authorization: Bearer {admin_token}
```
```json
{
  "teams": [
    {"id": 1, "name": "인사팀", "description": "인사 관련 문서", "user_count": 5, "doc_count": 120},
    {"id": 2, "name": "경영팀", "description": "경영 관련 문서", "user_count": 3, "doc_count": 45}
  ]
}
```

**팀 생성:**
```http
POST /api/admin/teams
Authorization: Bearer {admin_token}
Content-Type: application/json

{"name": "IT팀", "description": "IT/보안 관련 문서"}
```
```json
{"id": 3, "name": "IT팀", "description": "IT/보안 관련 문서"}
```

**팀 삭제:**
```http
DELETE /api/admin/teams/3
Authorization: Bearer {admin_token}
```
```json
{"ok": true, "message": "팀이 삭제되었습니다. 소속 유저의 팀 배정이 해제됩니다."}
```

### 10.4.2 유저 팀 배정 API

기존 `/api/admin/users/{user_id}` PATCH 엔드포인트 확장:

```http
PATCH /api/admin/users/123
Authorization: Bearer {admin_token}
Content-Type: application/json

{"team_id": 2}  // 경영팀으로 변경
```

### 10.4.3 팀 목록 조회 API (일반 유저용)

```http
GET /api/teams
Authorization: Bearer {token}
```
```json
{
  "teams": [
    {"id": 1, "name": "인사팀"},
    {"id": 2, "name": "경영팀"}
  ]
}
```

### 10.4.4 채팅 API 변경

WebSocket 연결 시 팀 ID를 쿼리 파라미터로 전달:

```
WS /api/chat/?token={jwt}&team_id={team_id}
```

또는 첫 메시지에 팀 정보 포함:

```json
{"question": "연차는 몇 일인가요?", "team_id": 1}
```

**권장**: 쿼리 파라미터 방식 (기존 구조와 호환)

---

## 10.5 백엔드 구현 상세

### 10.5.1 파일별 수정 내역

| 파일 | 수정 내용 | 코드량 |
|------|----------|--------|
| `backend/app/db/models.py` | Team 모델 추가, User에 team_id 추가 | ~40줄 |
| `backend/app/router/admin.py` | 팀 CRUD API, 유저 팀 배정 | ~100줄 |
| `backend/app/router/teams.py` | 일반 유저용 팀 목록 API (신규) | ~30줄 |
| `backend/app/router/docs.py` | 업로드 시 팀 검증, team_id 메타데이터 추가 | ~20줄 |
| `backend/app/router/chat.py` | team_id 파라미터 처리 | ~15줄 |
| `backend/app/rag/retriever.py` | 검색 필터에 team_id 조건 추가 | ~25줄 |
| `backend/app/ingest/pipeline.py` | 메타데이터에 team_id 포함 | ~10줄 |
| `backend/app/vectorstore/store.py` | sanitize_metadata에 team_id 추가 | ~5줄 |

### 10.5.2 모델 정의

```python
# backend/app/db/models.py

class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False, unique=True)
    description = Column(String(200), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 관계
    users = relationship("User", back_populates="team")


class User(Base):
    __tablename__ = "users"

    # 기존 필드...

    # 신규 필드
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=True)

    # 관계
    team = relationship("Team", back_populates="users")
```

### 10.5.3 검색 필터 로직

```python
# backend/app/rag/retriever.py

async def retrieve(
    question: str,
    team_id: Optional[int] = None,  # 신규 파라미터
    tags: Optional[List[str]] = None,
    k: int = 5
) -> List[ScoredChunk]:
    q_vec = await embed_query_async(question)

    # 필터 구성
    base_filter = {"visibility": {"$in": ["org", "public"]}}

    if team_id:
        # 팀 필터 적용: 해당 팀 문서 + team_id 없는 레거시 문서
        where = {
            "$and": [
                base_filter,
                {
                    "$or": [
                        {"team_id": {"$eq": str(team_id)}},
                        {"team_id": {"$eq": ""}},      # 빈 문자열
                        {"team_id": {"$exists": False}} # 필드 없음 (레거시)
                    ]
                }
            ]
        }
    else:
        where = base_filter

    raw = query_by_embedding(q_vec, n_results=..., where=where)
    # ... 이후 로직 동일
```

### 10.5.4 업로드 시 팀 검증

```python
# backend/app/router/docs.py

@router.post("/upload")
async def upload_docs(
    files: List[UploadFile],
    visibility: str = Form("org"),
    user: User = Depends(get_current_user),
):
    # 팀 소속 검증
    if not user.team_id:
        raise HTTPException(
            status_code=403,
            detail="팀에 소속되어 있지 않아 문서를 업로드할 수 없습니다. 관리자에게 문의하세요."
        )

    # 파이프라인에 team_id 전달
    asyncio.create_task(
        process_job(
            job_id,
            default_doc_type=doc_type,
            visibility=visibility,
            owner_id=int(user.id),
            owner_username=user.username,
            team_id=user.team_id,        # 신규
            team_name=user.team.name,    # 신규
        )
    )
```

---

## 10.6 프론트엔드 구현 상세

### 10.6.1 파일별 수정 내역

| 파일 | 수정 내용 | 코드량 |
|------|----------|--------|
| `frontend/src/pages/AdminSettingsPage.jsx` | 팀 관리 탭 추가, 유저 테이블에 팀 컬럼 추가 | ~200줄 |
| `frontend/src/pages/UploadPage.jsx` | 팀 미배정 시 업로드 차단 UI | ~30줄 |
| `frontend/src/pages/QueryPage.jsx` | 팀 선택 드롭다운 전달 | ~10줄 |
| `frontend/src/components/ChatPanel/ChatPanel.jsx` | 팀 선택 드롭다운 추가 | ~50줄 |
| `frontend/src/api/http.js` | 팀 API 함수 추가 | ~30줄 |
| `frontend/src/api/ws.js` | WebSocket에 team_id 전달 | ~5줄 |

### 10.6.2 관리자 페이지 - 팀 관리 탭

```jsx
// AdminSettingsPage.jsx - ModeSwitcher 확장

const cards = [
    { key: "docs", title: "문서 관리", desc: "벡터 스토어 내 전체 문서 조회/삭제" },
    { key: "users", title: "유저 관리", desc: "유저 조회/삭제/수정" },
    { key: "teams", title: "팀 관리", desc: "팀 추가/삭제/수정" },  // 신규
];
```

**팀 관리 UI:**
```
┌─────────────────────────────────────────────────────────┐
│ 팀 관리                                    [+ 팀 추가]  │
├─────────────────────────────────────────────────────────┤
│ # │ 팀 이름   │ 설명              │ 인원 │ 문서 │ 동작 │
│───┼───────────┼───────────────────┼──────┼──────┼──────│
│ 1 │ 인사팀    │ 인사 관련 문서    │ 5명  │ 120  │ 편집 │
│ 2 │ 경영팀    │ 경영 관련 문서    │ 3명  │ 45   │ 편집 │
│ 3 │ IT팀      │ IT/보안 문서      │ 8명  │ 67   │ 편집 │
└─────────────────────────────────────────────────────────┘
```

### 10.6.3 관리자 페이지 - 유저 테이블 확장

```jsx
// UsersView 테이블에 팀 컬럼 추가

<thead>
    <tr>
        <th>인덱스</th>
        <th>아이디</th>
        <th>이름</th>
        <th>팀</th>          {/* 신규 */}
        <th>보안등급</th>
        <th>비밀번호 변경</th>
        <th>동작</th>
    </tr>
</thead>

// 편집 모드에서 팀 선택 드롭다운
{editing ? (
    <select value={form.team_id} onChange={...}>
        <option value="">팀 미배정</option>
        {teams.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
    </select>
) : (
    user.team?.name || "미배정"
)}
```

### 10.6.4 업로드 페이지 - 팀 미배정 안내

```jsx
// UploadPage.jsx

// 기존 가드 조건에 팀 체크 추가
const canUploadByLevel = isLoggedIn &&
    Number(user?.security_level) <= MAX_UPLOAD_SECURITY_LEVEL;
const hasTeam = !!user?.team_id;  // 신규
const canUpload = canUploadByLevel && hasTeam;

// 팀 미배정 안내 배너
{!hasTeam && isLoggedIn && (
    <div className="guard-banner">
        <FaLock />
        <div>
            <strong>팀 배정이 필요합니다.</strong>
            <div>관리자에게 팀 배정을 요청하세요. 팀에 소속된 후 문서를 업로드할 수 있습니다.</div>
        </div>
    </div>
)}
```

### 10.6.5 질의 페이지 - 팀 선택 드롭다운

```jsx
// ChatPanel.jsx 헤더 영역

function ChatHeader({ selectedTeam, onTeamChange, teams }) {
    return (
        <div className="chat-header">
            <div className="chat-header__title">질문하기</div>
            <div className="chat-header__team-selector">
                <label>답변팀:</label>
                <select
                    value={selectedTeam || ""}
                    onChange={(e) => onTeamChange(e.target.value)}
                >
                    {teams.map(t => (
                        <option key={t.id} value={t.id}>{t.name}</option>
                    ))}
                </select>
            </div>
        </div>
    );
}
```

### 10.6.6 WebSocket 연결 수정

```javascript
// frontend/src/api/ws.js

export function openChatSocket(question, handlers, teamId = null) {
    const token = localStorage.getItem("auth_token");
    let url = `${WS_BASE}/api/chat/?token=${encodeURIComponent(token)}`;

    // 팀 ID 추가
    if (teamId) {
        url += `&team_id=${encodeURIComponent(teamId)}`;
    }

    const ws = new WebSocket(url);
    // ... 이후 동일
}
```

---

## 10.7 화면 흐름

### 10.7.1 관리자: 팀 생성 → 유저 배정

```
1. 관리자 로그인
2. 관리자 설정 > 팀 관리 탭
3. [+ 팀 추가] 클릭
4. 팀 이름/설명 입력 → 저장
5. 유저 관리 탭 이동
6. 유저 편집 → 팀 드롭다운에서 팀 선택 → 저장
```

### 10.7.2 일반 유저: 문서 업로드

```
1. 로그인 (팀 배정된 계정)
2. 업로드 페이지 이동
3. 파일 선택 → 업로드 (자동으로 소속 팀에 업로드)
4. 성공 메시지 확인
```

### 10.7.3 일반 유저: 질의

```
1. 로그인
2. 질의 페이지 이동
3. 답변팀 드롭다운에서 팀 선택 (기본: 첫 번째 팀)
4. 질문 입력 → 전송
5. 선택한 팀의 문서만 참조하여 답변 수신
```

---

## 10.8 보안 고려사항

### 10.8.1 권한 검증

| 동작 | 검증 항목 |
|------|----------|
| 팀 CRUD | 관리자(security_level=1)만 가능 |
| 유저 팀 배정 | 관리자만 가능 |
| 문서 업로드 | team_id가 있는 유저만 가능 |
| 질의 | 모든 로그인 유저 가능 (팀 선택은 자유) |

### 10.8.2 크로스팀 접근 방지

- 검색 필터에서 `team_id` 조건 강제 적용
- 레거시 문서(team_id 없음)는 모든 팀에서 접근 가능 (선택적)

### 10.8.3 팀 삭제 시 처리

```python
# 팀 삭제 시:
# 1. 소속 유저의 team_id를 NULL로 설정
# 2. 해당 팀의 문서는 유지 (team_id 메타데이터 그대로)
#    → 관리자가 별도로 문서 삭제 또는 재배정
```

---

## 10.9 마이그레이션 계획

### Phase 1: DB 스키마 (Day 1)
1. teams 테이블 생성
2. users 테이블에 team_id 컬럼 추가
3. 기본 팀("인사팀") 생성
4. 기존 유저 중 필요한 경우 기본 팀 배정

### Phase 2: 백엔드 API (Day 2-3)
1. Team 모델 및 관계 정의
2. 팀 CRUD API 구현
3. 유저 PATCH API에 team_id 처리 추가
4. 업로드 시 팀 검증 로직 추가
5. 검색 필터에 team_id 조건 추가

### Phase 3: 프론트엔드 (Day 4-5)
1. 관리자 페이지에 팀 관리 탭 추가
2. 유저 테이블에 팀 컬럼 추가
3. 업로드 페이지에 팀 미배정 안내 추가
4. 질의 페이지에 팀 선택 드롭다운 추가

### Phase 4: 테스트 및 배포 (Day 6-7)
1. 단위 테스트
2. 통합 테스트 (팀별 검색 격리 확인)
3. 기존 문서 접근 테스트
4. 배포

---

## 10.10 예상 이슈 및 대응

| 이슈 | 대응 방안 |
|------|----------|
| 기존 문서에 team_id 없음 | team_id 없는 문서는 모든 팀에서 검색 가능하도록 처리 |
| 팀 삭제 시 문서 처리 | 문서는 유지, 관리자가 수동 정리 |
| 유저가 팀 변경 시 기존 업로드 문서 | 문서의 team_id는 유지 (업로드 시점 기준) |
| 다중 팀 소속 요구 | 현재 설계는 단일 팀, 추후 확장 가능 |

---

## 10.11 검토 체크리스트

- [ ] DB 스키마 변경 검토
- [ ] API 설계 검토
- [ ] 프론트엔드 UI/UX 검토
- [ ] 보안 검토
- [ ] 마이그레이션 계획 검토
- [ ] 테스트 계획 검토
