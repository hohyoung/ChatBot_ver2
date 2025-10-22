# LLD - 저수준 설계 문서
## Low-Level Design Document

**프로젝트:** 사내 규정 RAG 챗봇 시스템
**버전:** 1.0
**작성일:** 2025-01-21
**담당자:** 개발팀

---

## 목차

이 디렉토리는 시스템의 저수준 설계 문서를 포함합니다. 각 파일은 특정 주제를 다룹니다.

### 📋 문서 목록

1. **[1-architecture.md](./1-architecture.md)** - 시스템 아키텍처
   - 전체 구조 다이어그램
   - 기술 스택 (백엔드/프론트엔드/인프라)
   - 레이어별 구성 (Router/Service/Data Layer)

2. **[2-database.md](./2-database.md)** - 데이터베이스 설계
   - 관계형 DB 스키마 (사용자 관리)
   - 벡터 DB 메타데이터 스키마 (ChromaDB)
   - 피드백 저장소 구조

3. **[3-api.md](./3-api.md)** - API 설계
   - WebSocket 프로토콜 (채팅)
   - REST API 엔드포인트
   - 요청/응답 형식

4. **[4-components.md](./4-components.md)** - 핵심 컴포넌트 상세
   - 스트리밍 마크다운 생성기 + 챗봇 페르소나
   - 표/그림 인식 파이프라인
   - FAQ 관리 시스템
   - 오케스트레이터
   - Retriever, Generator

5. **[5-dataflow.md](./5-dataflow.md)** - 데이터 흐름
   - 문서 업로드 플로우
   - RAG 쿼리 플로우
   - 피드백 플로우

6. **[6-security.md](./6-security.md)** - 보안 설계
   - 인증 플로우 (JWT, 이메일 OTP)
   - 권한 검증 (RBAC)
   - 데이터 암호화
   - 감사 로그

7. **[7-performance.md](./7-performance.md)** - 성능 최적화
   - 3계층 캐싱 전략
   - 문단 압축
   - API 키 라운드로빈
   - 큐잉 시스템

8. **[8-error.md](./8-error.md)** - 에러 처리
   - 에러 분류 및 처리 방법
   - 재시도 로직

9. **[9-deployment.md](./9-deployment.md)** - 배포 및 인프라
   - Docker Compose (개발 환경)
   - 프로덕션 아키텍처
   - CI/CD 파이프라인
   - 모니터링 및 로깅

---

## 사용 가이드

### 작업 시나리오별 참조

1. **새 기능 구현 시**
   - @PRD.md → 요구사항 확인
   - [4-components.md](./4-components.md) → 구현 패턴 확인
   - [3-api.md](./3-api.md) → API 설계 확인

2. **버그 수정 시**
   - [4-components.md](./4-components.md) → 관련 컴포넌트 구조 파악
   - [8-error.md](./8-error.md) → 에러 처리 전략 확인

3. **성능 개선 시**
   - @PRD.md → 비기능 요구사항 확인
   - [7-performance.md](./7-performance.md) → 최적화 전략 확인

4. **데이터베이스 작업 시**
   - [2-database.md](./2-database.md) → 스키마 확인

5. **보안 작업 시**
   - [6-security.md](./6-security.md) → 인증/권한 확인

---

## 변경 이력

| 버전 | 날짜 | 변경 내용 | 작성자 |
|-----|------|----------|--------|
| 1.0 | 2025-01-21 | 초안 작성 (단일 파일) | 개발팀 |
| 1.1 | 2025-01-22 | 주제별 파일 분할 | 개발팀 |
