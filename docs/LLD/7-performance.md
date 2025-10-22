# 7. 성능 최적화

## 7.1 캐싱 전략 (P1-1)

### 3계층 캐싱

#### L1: 임베딩 캐시 (In-Memory)
```python
# services/embedding.py
@lru_cache(maxsize=10000)
def embed_text_cached(text: str) -> List[float]:
    return openai.embeddings.create(
        model="text-embedding-3-small",
        input=text
    ).data[0].embedding
```

**특징:**
- 최대 10,000개 캐싱
- LRU 정책
- 메모리 사용량: ~600MB

#### L2: 검색 결과 캐시 (Redis)
```python
# rag/retriever.py
async def retrieve_cached(question: str, tags: List[str]) -> List[ScoredChunk]:
    cache_key = f"search:{hash(question)}:{','.join(sorted(tags))}"

    # Redis 조회
    cached = redis.get(cache_key)
    if cached:
        return json.loads(cached)

    # 미스 시 검색
    results = await retrieve(question, tags)

    # 캐시 저장 (TTL 1시간)
    redis.setex(cache_key, 3600, json.dumps([r.model_dump() for r in results]))

    return results
```

**특징:**
- TTL: 1시간
- 키 형식: `search:{hash}:{tags}`
- 적중률 목표: >60%

#### L3: 문서 메타데이터 캐시 (In-Memory)
```python
# vectorstore/store.py
_doc_meta_cache = {}

def get_doc_metadata(doc_id: str) -> dict:
    if doc_id in _doc_meta_cache:
        return _doc_meta_cache[doc_id]

    # DB 조회
    meta = ...
    _doc_meta_cache[doc_id] = meta
    return meta
```

**특징:**
- 문서 메타데이터만 캐싱
- 무제한 (문서 수 적음 가정)

---

## 7.2 문단 압축 (P0-5)

### 전략: 스코어 기반 선별 + 문장 추출

```python
def compress_chunks(chunks: List[Chunk], max_chars: int = 6000) -> List[Chunk]:
    selected = []
    total_chars = 0

    for chunk in sorted(chunks, key=lambda c: c.final_score, reverse=True):
        if total_chars + len(chunk.content) > max_chars:
            # 중요 문장만 추출
            sentences = chunk.content.split(". ")
            important = sentences[:2]  # 처음 2문장만
            chunk.content = ". ".join(important)

        selected.append(chunk)
        total_chars += len(chunk.content)

        if len(selected) >= 3:  # 최대 3개 문서
            break

    return selected
```

**목표:**
- 컨텍스트 윈도우: 6000자
- 문서 수: 최대 3개
- 정보 손실: <10%

---

## 7.3 API 키 라운드로빈 (P0-7)

### 키 풀 관리

```python
# services/openai_client.py
class OpenAIClientPool:
    def __init__(self, api_keys: List[str]):
        self.keys = api_keys
        self.current = 0
        self.usage = {key: 0 for key in api_keys}

    def get_client(self) -> OpenAI:
        key = self.keys[self.current]
        self.current = (self.current + 1) % len(self.keys)
        self.usage[key] += 1
        return OpenAI(api_key=key)

    def get_usage_stats(self) -> dict:
        return self.usage

# 사용
pool = OpenAIClientPool(api_keys=[
    os.getenv("OPENAI_API_KEY_1"),
    os.getenv("OPENAI_API_KEY_2"),
])

def get_client() -> OpenAI:
    return pool.get_client()
```

**목표:**
- 키 수: 2~5개
- 부하 분산: 균등 분배
- 사용량 모니터링: 대시보드

---

## 7.4 재시도 로직 (P0-7)

### 지수 백오프

```python
# services/retry.py
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

            # 429 또는 5xx만 재시도
            if hasattr(e, 'status_code') and e.status_code in (429, 500, 502, 503):
                await asyncio.sleep(min(delay, max_delay))
                delay *= backoff_factor
            else:
                raise
```

**목표:**
- 최대 재시도: 3회
- 초기 지연: 1초
- 최대 지연: 60초
- 백오프 계수: 2.0

---

## 7.5 큐잉 시스템 (P0-7)

### asyncio Queue

```python
# services/queue.py
class TaskQueue:
    def __init__(self, max_workers: int = 5):
        self.queue = asyncio.Queue()
        self.workers = []
        for _ in range(max_workers):
            self.workers.append(asyncio.create_task(self._worker()))

    async def _worker(self):
        while True:
            task, callback = await self.queue.get()
            try:
                result = await task()
                callback(result, None)
            except Exception as e:
                callback(None, e)
            finally:
                self.queue.task_done()

    async def enqueue(self, task: Callable, callback: Callable):
        await self.queue.put((task, callback))
```

**목표:**
- 워커 수: 5~10
- 큐 크기: 무제한
- 처리 시간: <30초

---

## 7.6 성능 목표

| 지표 | 목표 | 현재 (추정) |
|-----|------|------------|
| p50 응답 시간 | ≤15초 | ~12초 |
| p90 응답 시간 | ≤22초 | ~18초 |
| 첫 토큰 (스트리밍) | ≤2초 | ~1.5초 |
| 캐시 적중률 | >60% | ~40% |
| 동시 요청 | ≥100 | ~50 |
| API 비용 | ≤$1,000/월 | ~$500/월 |
