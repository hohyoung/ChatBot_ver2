# 📚 프로젝트 문서

이 디렉토리는 사내 규정 RAG 챗봇 시스템의 모든 설계 및 계획 문서를 포함합니다.

---

## 📋 문서 구조

### 핵심 문서 (3개)

1. **[PRD.md](./PRD.md)** - 제품 요구사항 명세서
   - 제품 비전, 목표, KPI
   - 사용자 페르소나 및 시나리오
   - 기능 요구사항 (P0/P1/P2)
   - 비기능 요구사항 (성능, 보안)
   - **언제 참조**: 새 기능 추가 시, 요구사항 확인 시

2. **[PLAN.md](./PLAN.md)** - 프로젝트 구현 계획 및 로드맵
   - 전체 로드맵 (M1/M2/M3)
   - 작업 체크리스트 (완료/진행/예정)
   - 우선순위 및 의존성
   - **언제 참조**: 다음 작업 확인 시, 일정 조율 시

3. **[LLD/](./LLD/)** - 저수준 설계 문서 (주제별 분할)
   - [README.md](./LLD/README.md) - 개요 및 목차
   - [1-architecture.md](./LLD/1-architecture.md) - 시스템 아키텍처
   - [2-database.md](./LLD/2-database.md) - 데이터베이스 설계
   - [3-api.md](./LLD/3-api.md) - API 설계
   - [4-components.md](./LLD/4-components.md) - 핵심 컴포넌트
   - [5-dataflow.md](./LLD/5-dataflow.md) - 데이터 흐름
   - [6-security.md](./LLD/6-security.md) - 보안 설계
   - [7-performance.md](./LLD/7-performance.md) - 성능 최적화
   - [8-error.md](./LLD/8-error.md) - 에러 처리
   - [9-deployment.md](./LLD/9-deployment.md) - 배포 및 인프라
   - **언제 참조**: 구현 시, 아키텍처 확인 시

---

## 🎯 작업별 문서 가이드

### 새 기능 개발
```
1. PRD.md → 요구사항 확인
2. LLD/4-components.md → 구현 패턴 확인
3. LLD/3-api.md → API 설계 확인
4. PLAN.md → 우선순위 확인
```

### 버그 수정
```
1. LLD/4-components.md → 컴포넌트 구조 파악
2. LLD/8-error.md → 에러 처리 전략 확인
```

### 성능 최적화
```
1. PRD.md → NFR 목표 확인
2. LLD/7-performance.md → 최적화 전략 확인
```

### 데이터베이스 작업
```
1. LLD/2-database.md → 스키마 확인
```

### 보안 작업
```
1. LLD/6-security.md → 인증/권한 확인
```

### 배포 작업
```
1. LLD/9-deployment.md → 인프라 설정 확인
```

---

## 📝 기타 파일

- **todolist.txt** - 임시 작업 메모 (레거시, PLAN.md 사용 권장)

---

## 🔄 문서 유지보수

### 문서 업데이트 원칙
1. **코드 변경 시**: 관련 LLD 섹션도 함께 업데이트
2. **새 요구사항**: PRD.md 업데이트 → LLD 설계 추가 → PLAN.md 일정 반영
3. **완료된 작업**: PLAN.md 체크리스트 업데이트

### 정기 검토
- **분기별**: 전체 문서 정확성 검토
- **릴리즈 전**: 문서-코드 일치성 확인

---

## 📖 문서 히스토리

| 날짜 | 변경 내용 | 작성자 |
|-----|----------|--------|
| 2025-01-21 | PRD, LLD, PLAN 초안 작성 | 개발팀 |
| 2025-01-22 | LLD 주제별 분할 (1개 → 9개 파일) | 개발팀 |
| 2025-01-22 | docs/ 디렉토리 구조화 | 개발팀 |
