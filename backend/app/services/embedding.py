# backend/app/services/embedding.py
from typing import List, Optional
from openai import OpenAI
from app.config import settings


def _client() -> OpenAI:
    if settings.openai_base_url:
        return OpenAI(
            api_key=settings.openai_api_key, base_url=settings.openai_base_url
        )
    return OpenAI(api_key=settings.openai_api_key)


_client_singleton = _client()


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
