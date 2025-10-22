# 4. 핵심 컴포넌트 상세

## 4.1 스트리밍 마크다운 생성기 + 챗봇 페르소나 (P0-1)

**위치:** `backend/app/rag/generator.py`

### 챗봇 페르소나

**정체성:** 사내 규정 안내 전문가 (Knowledge Navigator)
**톤:** 전문적이면서도 친근한 어조
**목표:** 직원들이 규정을 쉽고 빠르게 이해하도록 돕기
**제약:** 제공된 문서의 내용에만 근거

### 시스템 프롬프트

```python
SYSTEM_PROMPT_MARKDOWN = """
당신은 사내 규정 안내 전문가입니다.

## 답변 작성 원칙
1. 제공된 규정 문서의 내용에만 근거
2. 친절하고 명확하게 핵심만 전달
3. 관련 규정의 조항을 함께 언급
4. 표 형식으로 정리 가능한 데이터는 마크다운 테이블 사용
5. 답변이 어려운 경우 솔직하게 안내

## 응답 구조
1. **핵심 답변**: 첫 문단에 결론 명확히 제시
2. **상세 설명**: 필요 시 추가 설명 (표, 리스트)
3. **관련 규정**: 조항 명시 (예: **제10조**)
4. **출처**: 문서명과 페이지
"""
```

### 스트리밍 구현

```python
async def generate_answer_stream(
    question: str,
    candidates: List[ScoredChunk],
    websocket: WebSocket
):
    # 1) 청크 선별
    used_chunks = _select_chunks(candidates, max_chars=6000)

    # 2) 컨텍스트 구성
    context = _build_context(used_chunks)

    # 3) 스트리밍 모드 LLM 호출
    client = get_client()
    stream = client.chat.completions.create(
        model=settings.openai_model,
        messages=[...],
        temperature=0.2,
        stream=True
    )

    # 4) 토큰 단위 전송
    answer_buffer = ""
    for chunk in stream:
        if chunk.choices[0].delta.content:
            token = chunk.choices[0].delta.content
            answer_buffer += token

            await websocket.send_json({
                "type": "token",
                "token": token
            })

    # 5) 최종 이벤트
    await websocket.send_json({
        "type": "final",
        "data": {
            "answer": answer_buffer,
            "chunks": [c.model_dump() for c in used_chunks],
            ...
        }
    })
```

---

## 4.2 표/그림 인식 파이프라인 (P0-2)

**위치:** `backend/app/ingest/vision.py`, `backend/app/ingest/parsers/pdf.py`

### 이미지 추출

```python
import fitz  # PyMuPDF

async def extract_tables_and_figures(pdf_path: str, doc_id: str):
    doc = fitz.open(pdf_path)
    images_dir = Path(f"storage/docs/images/{doc_id}")
    images_dir.mkdir(parents=True, exist_ok=True)

    extracted = []

    for page_num, page in enumerate(doc, start=1):
        # 표 추출
        tables = page.find_tables()
        for table_idx, table in enumerate(tables):
            rect = table.bbox
            pix = page.get_pixmap(clip=rect, matrix=fitz.Matrix(2, 2))
            img_path = images_dir / f"table_p{page_num}_{table_idx}.png"
            pix.save(img_path)

            extracted.append({
                "type": "table",
                "page": page_num,
                "image_path": str(img_path)
            })

    return extracted
```

### Vision API 표 변환

```python
async def convert_table_to_markdown(image_path: str) -> str:
    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode()

    client = get_client()
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": "이 표를 마크다운 형식으로 변환해라."},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_data}"}}
            ]
        }],
        max_tokens=1000
    )

    return response.choices[0].message.content
```

---

## 4.3 FAQ 관리 시스템 (P0-3)

**위치:** `backend/app/services/faq.py`

### 질문 로그 저장

```python
async def log_question(question: str, answer_id: str):
    embedding = embed_texts([question])[0]

    log_entry = {
        "question": question,
        "question_embedding": embedding.tolist(),
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "answer_id": answer_id
    }

    with open("data/queries.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
```

### 클러스터링

```python
from sklearn.cluster import DBSCAN

async def cluster_questions():
    # 최근 7일 질문 로드
    questions = []
    embeddings = []

    cutoff_time = datetime.utcnow() - timedelta(days=7)

    with open("data/queries.jsonl", "r", encoding="utf-8") as f:
        for line in f:
            entry = json.loads(line)
            timestamp = datetime.fromisoformat(entry["timestamp"].rstrip("Z"))
            if timestamp >= cutoff_time:
                questions.append(entry)
                embeddings.append(entry["question_embedding"])

    # DBSCAN 클러스터링
    embeddings_array = np.array(embeddings)
    clustering = DBSCAN(eps=0.3, min_samples=5, metric='cosine')
    labels = clustering.fit_predict(embeddings_array)

    # Top-10 FAQ 추출
    faq_list = []
    for label in set(labels):
        if label == -1:
            continue

        cluster_questions = [q for i, q in enumerate(questions) if labels[i] == label]
        # 가장 많이 나온 질문 선정
        ...

    return faq_list[:10]
```

---

## 4.4 오케스트레이터 (P0-5)

**위치:** `backend/app/rag/orchestrator.py`

### 의도 분류 및 라우팅

```python
async def orchestrate(question: str) -> Response:
    # 1) 의도 분류
    intent = await classify_intent(question)

    if intent == "doc_request":
        # 문서 검색 경로
        docs = await search_documents(question)
        return DocumentListResponse(items=docs)

    elif intent == "info_request":
        # RAG 경로
        tags = await tag_query(question)
        candidates = await retrieve(question, tags)

        # 마스터 인덱스 기반 문서 선별
        top_docs = select_top_documents(candidates, max_docs=3)

        # 답변 생성
        answer, chunks = await generate_answer(question, top_docs)
        return ChatFinalEvent(data=ChatAnswer(answer=answer, chunks=chunks))
```

---

## 4.5 Retriever (검색)

**위치:** `backend/app/rag/retriever.py`

```python
async def retrieve(question: str, tags: List[str]) -> List[ScoredChunk]:
    # 1) 질문 임베딩
    q_emb = embed_texts([question])[0]

    # 2) 태그 필터
    tag_filter = {"$or": [{"tags": {"$contains": tag}} for tag in tags]}

    # 3) 벡터 검색
    results = query_by_embedding(q_emb, n_results=10, where=tag_filter)

    # 4) 스코어링 (유사도 + 피드백 부스트)
    candidates = []
    for i, (doc, meta, dist) in enumerate(zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0]
    )):
        similarity = 1.0 - dist
        fb_pos = meta.get("fb_pos", 0)
        fb_neg = meta.get("fb_neg", 0)
        boost = 1.0 + (fb_pos - fb_neg) * 0.1
        final_score = similarity * boost

        candidates.append(ScoredChunk(chunk=Chunk(**meta, content=doc), final_score=final_score))

    # 5) 정렬
    candidates.sort(key=lambda x: x.final_score, reverse=True)
    return candidates[:5]
```

---

## 4.6 Generator (답변 생성)

**위치:** `backend/app/rag/generator.py`

```python
async def generate_answer(
    question: str,
    candidates: List[ScoredChunk]
) -> Tuple[str, List[Chunk]]:
    # 1) 청크 선별 (최대 6000자)
    used_chunks = _select_chunks(candidates, max_chars=6000)

    # 2) 컨텍스트 구성
    context = _build_context(used_chunks)

    # 3) LLM 호출
    client = get_client()
    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"질문: {question}\n\n관련 문서:\n{context}"}
        ],
        temperature=0.2
    )

    return response.choices[0].message.content, used_chunks
```
