# 5. 데이터 흐름

## 5.1 문서 업로드 플로우

```
[Client] --POST /api/docs/upload--> [FastAPI Router]
                                          |
                                          v
                                    [save_batch()]
                                          |
                                          v
                              storage/uploads/{job_id}/
                                          |
                                          v
                                [job_store.start()]
                                          |
                                          v
                        asyncio.create_task(process_job)
                                          |
         ┌────────────────────────────────┴─────────┐
         v                                          v
    [Pipeline]                            [Client polls]
         |                                 GET /api/docs/{job_id}/status
         v
    Hash → Duplicate Check → Parse → Chunk → Tag → Embed → Upsert
         |
         v
    storage/docs/public/
         |
         v
    [job_store.finish()]
```

### 주요 단계

1. **파일 업로드**: 클라이언트가 multipart/form-data로 전송
2. **임시 저장**: `storage/uploads/{job_id}/`에 저장
3. **작업 생성**: job_store에 작업 등록, job_id 반환
4. **백그라운드 처리**:
   - 해시 계산 (SHA-256)
   - 중복 체크 (`doc_exists_by_hash`)
   - 파싱 (PDF/DOCX/TXT/HTML)
   - 청킹 (1200자, PDF는 페이지 정보 유지)
   - 태깅 (LLM)
   - 임베딩 (OpenAI)
   - 벡터 저장소 업서트
5. **파일 이동**: `storage/docs/public/`로 이동
6. **정리**: 임시 파일 삭제, 작업 완료 표시

---

## 5.2 RAG 쿼리 플로우

```
[Client] --WS /api/chat/--> [FastAPI Router]
                                    |
                                    v
                          [Orchestrator]
                                    |
                      ┌─────────────┴─────────────┐
                      v                           v
                [doc_request]              [info_request]
                      |                           |
                      v                           v
              [search_documents()]          [tag_query()]
                      |                           |
                      |                           v
                      |                     [retrieve()]
                      |                           |
                      |                           v
                      |                  [generate_answer()]
                      |                           |
                      └───────────┬───────────────┘
                                  v
                          [WebSocket Response]
                                  |
                                  v
                              [Client]
```

### 주요 단계

1. **질문 수신**: WebSocket으로 텍스트 질문 수신
2. **의도 분류**: Orchestrator가 doc_request/info_request 판단
3. **문서 검색 경로** (doc_request):
   - 문서 메타데이터 검색
   - 문서 리스트 반환
4. **RAG 경로** (info_request):
   - **태깅**: LLM으로 의미론적 태그 추출
   - **검색**: 질문 임베딩 + 태그 필터로 ChromaDB 쿼리
   - **생성**: 상위 청크 선택, 컨텍스트 구성, OpenAI 호출
5. **스트리밍 응답**: 토큰 단위로 전송 (P0-1)
6. **최종 응답**: 답변 + 출처 + 메타데이터 반환

---

## 5.3 피드백 플로우

```
[Client] --POST /api/feedback--> [FastAPI Router]
                                        |
                                        v
                                [feedback_store.upsert_boost()]
                                        |
                    ┌───────────────────┴───────────────┐
                    v                                   v
            [Update fb_pos/fb_neg]            [Recalculate factor]
                    |                                   |
                    v                                   v
            [ChromaDB metadata update]         [JSONL append]
```

### 주요 단계

1. **피드백 제출**: chunk_id, vote (up/down), query
2. **메타데이터 업데이트**:
   - fb_pos 또는 fb_neg 증가
   - 부스트 팩터 재계산: `1.0 + (fb_pos - fb_neg) * 0.1`
3. **ChromaDB 업데이트**: 해당 청크 메타데이터 갱신
4. **로그 저장**: JSONL 파일에 피드백 기록
5. **응답**: 업데이트된 부스트 점수 반환
