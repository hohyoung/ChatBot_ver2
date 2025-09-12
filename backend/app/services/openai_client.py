from openai import OpenAI
from app.config import settings

# settings.openai_base_url 은 config에서 /v1 보정된 값이 들어옴
_client = (
    OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
    if settings.openai_base_url
    else OpenAI(api_key=settings.openai_api_key)
)


def get_client() -> OpenAI:
    """모든 모듈에서 재사용할 OpenAI 싱글턴 클라이언트"""
    return _client
