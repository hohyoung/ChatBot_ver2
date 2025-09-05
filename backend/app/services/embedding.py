from __future__ import annotations
from typing import Iterable, List
from openai import OpenAI
from app.config import settings


def _client() -> OpenAI:
    if settings.openai_base_url:
        return OpenAI(
            api_key=settings.openai_api_key, base_url=settings.openai_base_url
        )
    return OpenAI(api_key=settings.openai_api_key)


def embed_texts(
    texts: Iterable[str], *, model: str | None = None, dimensions: int | None = None
) -> List[List[float]]:
    texts_list = [t if isinstance(t, str) else str(t) for t in texts]
    if not texts_list:
        return []
    client = _client()
    resp = client.embeddings.create(
        model=(model or settings.openai_embed_model),
        input=texts_list,
        **({"dimensions": dimensions} if dimensions else {}),
    )
    return [d.embedding for d in resp.data]
