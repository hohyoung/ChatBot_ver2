# 서버 배포 가이드 (Windows + IIS + Nginx)

## 개요

이 문서는 사내 규정 RAG 챗봇 시스템을 Windows 서버에 배포하는 방법을 설명합니다.

**서버 환경:**
- OS: Windows Server
- 웹 서버: IIS (프론트엔드 정적 파일 서빙)
- 리버스 프록시: Nginx (API 프록시)
- 버전 관리: Git

---

## 1. 사전 요구사항

서버에 다음이 설치되어 있어야 합니다 (ver1과 동일):

| 구성 요소 | 버전 | 확인 명령어 |
|----------|------|------------|
| Python | 3.11+ | `python --version` |
| Node.js | 18+ | `node --version` |
| Git | 2.40+ | `git --version` |
| ODBC Driver | 17 | 제어판 → ODBC 데이터 원본 |
| Redis | 7+ | `redis-cli ping` |

---

## 2. 프로젝트 가져오기

```powershell
# 배포 디렉토리로 이동
cd C:\inetpub\wwwroot

# Git에서 프로젝트 클론
git clone https://github.com/hohyoung/vacationChecklist.git chatBot_ver2

# 또는 기존 디렉토리에서 pull
cd chatBot_ver2
git pull origin main
```

---

## 3. 백엔드 설정

### 3.1 가상환경 생성 및 의존성 설치

```powershell
cd C:\inetpub\wwwroot\chatBot_ver2\backend

# 가상환경 생성
python -m venv venv

# 가상환경 활성화
.\venv\Scripts\Activate.ps1

# 의존성 설치
pip install -r requirements.txt
```

### 3.2 환경변수 설정

`backend\.env` 파일 생성:

```ini
# ====================================================================
# OpenAI API 설정
# ====================================================================
OPENAI_API_KEY=sk-proj-YOUR_API_KEY_HERE

# 여러 API 키 사용 시 (라운드로빈)
OPENAI_API_KEYS=sk-key1,sk-key2,sk-key3

OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_CHAT_MODEL=gpt-4o-mini
OPENAI_EMBED_MODEL=text-embedding-3-small

# ====================================================================
# GAR Feature Flags
# ====================================================================
GAR_PHASE2_ENABLED=true
GAR_PHASE3_ENABLED=true

# ====================================================================
# 인증 설정
# ====================================================================
REQUIRE_AUTH_UPLOAD=true

JWT_SECRET=YOUR_SECRET_KEY_HERE
JWT_EXPIRE_MINUTES=3600

# ====================================================================
# 데이터베이스
# ====================================================================
DATABASE_URL=mssql+pyodbc://username:password@192.68.10.249/ChatBot?driver=ODBC+Driver+17+for+SQL+Server&Encrypt=no&TrustServerCertificate=yes

# ====================================================================
# CORS 설정 (프로덕션 도메인)
# ====================================================================
CORS_ALLOW_ORIGINS=http://your-server-domain

# ====================================================================
# 로깅
# ====================================================================
LOG_LEVEL=INFO
LOG_TO_FILE=true
CONSOLE_LOG_LEVEL=WARNING

# ====================================================================
# 기타
# ====================================================================
INTERNAL_EMAIL_DOMAIN=soosan.co.kr
```

### 3.3 디렉토리 생성

```powershell
# 필요한 디렉토리 생성
mkdir -Force backend\data
mkdir -Force backend\logs
mkdir -Force backend\storage\docs
```

### 3.4 백엔드 실행 테스트

```powershell
cd C:\inetpub\wwwroot\chatBot_ver2\backend
.\venv\Scripts\Activate.ps1

# 테스트 실행
uvicorn app.main:app --host 127.0.0.1 --port 8000

# 브라우저에서 확인: http://localhost:8000/health
```

---

## 4. 프론트엔드 빌드

### 4.1 의존성 설치 및 빌드

```powershell
cd C:\inetpub\wwwroot\chatBot_ver2\frontend

# 의존성 설치
npm install

# 프로덕션 빌드
npm run build
```

빌드 결과물은 `frontend\dist` 폴더에 생성됩니다.

### 4.2 환경변수 설정

`frontend\.env` 파일:

```ini
VITE_API_BASE=/api
```

---

## 5. IIS 설정 (프론트엔드 서빙)

### 5.1 사이트 생성

1. **IIS 관리자** 실행
2. **사이트** → **웹 사이트 추가**
3. 설정:
   - 사이트 이름: `ChatBot_Frontend`
   - 실제 경로: `C:\inetpub\wwwroot\chatBot_ver2\frontend\dist`
   - 바인딩: `http`, 포트 `80` (또는 원하는 포트)

### 5.2 URL Rewrite 규칙 (SPA 라우팅)

`frontend\dist\web.config` 파일 생성:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
  <system.webServer>
    <rewrite>
      <rules>
        <!-- API 요청은 Nginx로 프록시 (IIS ARR 사용 시) -->
        <rule name="API Proxy" stopProcessing="true">
          <match url="^api/(.*)" />
          <action type="Rewrite" url="http://127.0.0.1:8000/api/{R:1}" />
        </rule>

        <!-- SPA 라우팅: 파일이 없으면 index.html로 -->
        <rule name="SPA Routes" stopProcessing="true">
          <match url=".*" />
          <conditions logicalGrouping="MatchAll">
            <add input="{REQUEST_FILENAME}" matchType="IsFile" negate="true" />
            <add input="{REQUEST_FILENAME}" matchType="IsDirectory" negate="true" />
          </conditions>
          <action type="Rewrite" url="/index.html" />
        </rule>
      </rules>
    </rewrite>

    <!-- 정적 파일 MIME 타입 -->
    <staticContent>
      <mimeMap fileExtension=".json" mimeType="application/json" />
      <mimeMap fileExtension=".woff2" mimeType="font/woff2" />
    </staticContent>
  </system.webServer>
</configuration>
```

---

## 6. Nginx 설정 (리버스 프록시)

### 6.1 Nginx 설정 파일

`nginx.conf` 또는 `conf.d/chatbot.conf`:

```nginx
upstream backend {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name your-server-domain;

    # 프론트엔드 정적 파일 (IIS가 처리하므로 생략 가능)
    # location / {
    #     root C:/inetpub/wwwroot/chatBot_ver2/frontend/dist;
    #     try_files $uri $uri/ /index.html;
    # }

    # API 프록시
    location /api/ {
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket 타임아웃
        proxy_read_timeout 86400;
        proxy_send_timeout 86400;
    }

    # 정적 문서 파일
    location /static/docs/ {
        alias C:/inetpub/wwwroot/chatBot_ver2/backend/storage/docs/;
        expires 1d;
        add_header Cache-Control "public, immutable";
    }

    # 헬스체크
    location /health {
        proxy_pass http://backend/health;
    }
}
```

### 6.2 Nginx 재시작

```powershell
nginx -t          # 설정 테스트
nginx -s reload   # 재시작
```

---

## 7. 백엔드 서비스 등록 (NSSM)

백엔드를 Windows 서비스로 등록하여 자동 시작되도록 설정합니다.

### 7.1 NSSM 설치

[NSSM 다운로드](https://nssm.cc/download) 후 `C:\nssm` 에 압축 해제

### 7.2 서비스 등록

```powershell
# 관리자 권한 PowerShell에서 실행
cd C:\nssm\win64

# 서비스 설치
.\nssm.exe install ChatBot_Backend

# GUI에서 설정:
# - Path: C:\inetpub\wwwroot\chatBot_ver2\backend\venv\Scripts\uvicorn.exe
# - Startup directory: C:\inetpub\wwwroot\chatBot_ver2\backend
# - Arguments: app.main:app --host 127.0.0.1 --port 8000 --workers 4

# 또는 명령어로 직접 설정
.\nssm.exe set ChatBot_Backend Application "C:\inetpub\wwwroot\chatBot_ver2\backend\venv\Scripts\uvicorn.exe"
.\nssm.exe set ChatBot_Backend AppDirectory "C:\inetpub\wwwroot\chatBot_ver2\backend"
.\nssm.exe set ChatBot_Backend AppParameters "app.main:app --host 127.0.0.1 --port 8000 --workers 4"

# 서비스 시작
.\nssm.exe start ChatBot_Backend
```

### 7.3 서비스 관리 명령어

```powershell
# 상태 확인
.\nssm.exe status ChatBot_Backend

# 재시작
.\nssm.exe restart ChatBot_Backend

# 중지
.\nssm.exe stop ChatBot_Backend

# 로그 확인
Get-Content C:\inetpub\wwwroot\chatBot_ver2\backend\logs\log.txt -Tail 100
```

---

## 8. ver1 → ver2 변경 사항

| 항목 | ver1 | ver2 |
|------|------|------|
| **팀 격리** | 없음 | team_id 기반 문서 격리 |
| **GAR 파이프라인** | 기본 RAG | Phase 2/3 추가 (쿼리 확장, 리랭킹) |
| **FAQ 시스템** | 없음 | FAQ 캐시 및 API |
| **로깅** | 콘솔 전체 출력 | 콘솔 WARNING만, 파일에 상세 로그 |
| **환경변수** | 기본 | GAR_PHASE2_ENABLED, GAR_PHASE3_ENABLED 추가 |

---

## 9. 배포 후 체크리스트

### 9.1 필수 확인

- [ ] `http://서버주소/health` 응답 확인 (`{"status":"ok"}`)
- [ ] 로그인 테스트
- [ ] 문서 업로드 테스트
- [ ] 채팅 질의 테스트 (WebSocket 연결)
- [ ] PDF 뷰어 정상 동작

### 9.2 로그 확인

```powershell
# 백엔드 로그
Get-Content C:\inetpub\wwwroot\chatBot_ver2\backend\logs\log.txt -Tail 50 -Wait

# Nginx 에러 로그
Get-Content C:\nginx\logs\error.log -Tail 50

# IIS 로그
Get-Content C:\inetpub\logs\LogFiles\W3SVC1\*.log -Tail 50
```

### 9.3 문제 해결

**WebSocket 연결 실패:**
- Nginx `proxy_read_timeout` 설정 확인
- IIS WebSocket 프로토콜 활성화

**CORS 에러:**
- `backend\.env`의 `CORS_ALLOW_ORIGINS` 확인
- 프로덕션 도메인 추가

**DB 연결 실패:**
- ODBC Driver 17 설치 확인
- 방화벽 포트 1433 열림 확인
- `DATABASE_URL` 연결 문자열 확인

---

## 10. 업데이트 절차

```powershell
# 1. 백엔드 서비스 중지
nssm stop ChatBot_Backend

# 2. Git pull
cd C:\inetpub\wwwroot\chatBot_ver2
git pull origin main

# 3. 백엔드 의존성 업데이트 (필요시)
cd backend
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 4. 프론트엔드 재빌드
cd ..\frontend
npm install
npm run build

# 5. 백엔드 서비스 시작
nssm start ChatBot_Backend

# 6. 헬스체크
curl http://localhost:8000/health
```

---

## 11. 파일 구조 (프로덕션)

```
C:\inetpub\wwwroot\chatBot_ver2\
├── backend\
│   ├── app\                    # 애플리케이션 코드
│   ├── data\                   # ChromaDB, SQLite (개발용)
│   ├── logs\                   # 로그 파일
│   │   └── log.txt            # 상세 로그
│   ├── storage\
│   │   └── docs\              # 업로드된 문서 파일
│   ├── venv\                   # Python 가상환경
│   ├── .env                    # 환경변수 (Git 제외)
│   └── requirements.txt
│
├── frontend\
│   ├── dist\                   # 빌드 결과물 (IIS 서빙)
│   │   ├── index.html
│   │   ├── assets\
│   │   └── web.config         # IIS URL Rewrite 설정
│   ├── src\                    # 소스 코드
│   ├── .env
│   └── package.json
│
└── docs\                       # 문서
```

---

## 부록: 빠른 배포 스크립트

`deploy.ps1`:

```powershell
# 배포 스크립트 (관리자 권한 필요)
param(
    [switch]$SkipBuild = $false
)

$ErrorActionPreference = "Stop"
$projectRoot = "C:\inetpub\wwwroot\chatBot_ver2"

Write-Host "=== ChatBot Ver2 배포 시작 ===" -ForegroundColor Green

# 1. 서비스 중지
Write-Host "1. 백엔드 서비스 중지..." -ForegroundColor Yellow
nssm stop ChatBot_Backend 2>$null

# 2. Git pull
Write-Host "2. Git pull..." -ForegroundColor Yellow
Set-Location $projectRoot
git pull origin main

# 3. 백엔드 의존성
Write-Host "3. 백엔드 의존성 설치..." -ForegroundColor Yellow
Set-Location "$projectRoot\backend"
& .\venv\Scripts\pip.exe install -r requirements.txt -q

# 4. 프론트엔드 빌드
if (-not $SkipBuild) {
    Write-Host "4. 프론트엔드 빌드..." -ForegroundColor Yellow
    Set-Location "$projectRoot\frontend"
    npm install --silent
    npm run build
} else {
    Write-Host "4. 프론트엔드 빌드 스킵" -ForegroundColor Gray
}

# 5. 서비스 시작
Write-Host "5. 백엔드 서비스 시작..." -ForegroundColor Yellow
nssm start ChatBot_Backend

# 6. 헬스체크
Write-Host "6. 헬스체크..." -ForegroundColor Yellow
Start-Sleep -Seconds 3
$health = Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get
if ($health.status -eq "ok") {
    Write-Host "=== 배포 완료! ===" -ForegroundColor Green
} else {
    Write-Host "=== 헬스체크 실패! ===" -ForegroundColor Red
}
```

사용:
```powershell
# 전체 배포
.\deploy.ps1

# 프론트엔드 빌드 스킵 (백엔드만 업데이트)
.\deploy.ps1 -SkipBuild
```
