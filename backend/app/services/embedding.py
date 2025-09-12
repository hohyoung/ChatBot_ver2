# backend/app/services/embedding.py
from typing import List, Optional
from app.services.openai_client import get_client
from app.config import settings




_client_singleton = get_client()


def embed_texts(
    texts: List[str],
    model: Optional[str] = None,
    dimensions: Optional[int] = None,
) -> List[List[float]]:
    """여러 텍스트를 한 번에 임베딩"""
    if not texts:
        return []
    resp = _client_singleton.embeddings.create(
        model=(model or settings.openai_embed_model),
        input=texts,
        **({"dimensions": dimensions} if dimensions else {}),
    )
    # openai v1: resp.data[*].embedding
    return [d.embedding for d in resp.data]


def embed_query(text: str, model: Optional[str] = None) -> List[float]:
    """질의 한 건 임베딩 → retriever에서 기대하는 인터페이스"""
    embs = embed_texts([text], model=model)
    return embs[0] if embs else []
