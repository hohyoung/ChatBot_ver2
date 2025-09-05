import os
import logging
from dataclasses import dataclass
from dotenv import load_dotenv

# .env 로드 (운영 배포에서는 OS 환경변수/시크릿 매니저로 주입 권장)
load_dotenv()


def _getenv(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, default)

def _norm_openai_base(url: str | None) -> str | None:
    if not url:
        return None
    u = url.strip().rstrip("/")
    # api.openai.com이면 /v1 보장
    if "api.openai.com" in u and not u.endswith("/v1"):
        return u + "/v1"
    return u


@dataclass(frozen=True)
class Settings:
    # App
    app_env: str = _getenv("APP_ENV", "dev") or "dev"
    strict_env: bool = (_getenv("STRICT_ENV", "false") or "false").lower() in (
        "1",
        "true",
        "yes",
    )

    openai_api_key: str = _getenv("OPENAI_API_KEY", "")
    # 새 이름(권장)과 구 이름 둘 다 허용
    openai_base_url: str | None = _norm_openai_base(
        _getenv("OPENAI_BASE_URL") or _getenv("OPENAI_API_BASE")
    )
    openai_model: str = _getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
    openai_embed_model: str = _getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")

    
    # Vector DB (Chroma)
    chroma_persist_dir: str = (
        _getenv("CHROMA_PERSIST_DIR", "./data/chroma") or "./data/chroma"
    )
    collection_name: str = (
        _getenv("COLLECTION_NAME", "knowledge_base") or "knowledge_base"
    )
    


    # Auth (문서 업로드 보호용)
    jwt_secret: str | None = _getenv("JWT_SECRET")
    jwt_expires_in: int = int(_getenv("JWT_EXPIRES_IN", "3600") or "3600")

    # CORS
    cors_allow_origins: str = (
        _getenv("CORS_ALLOW_ORIGINS", "http://localhost:5173")
        or "http://localhost:5173"
        
    )
    
    require_auth_upload: bool = (_getenv("REQUIRE_AUTH_UPLOAD", "false") or "false").lower() in ("1", "true", "yes")



settings = Settings()


def validate_on_startup() -> None:
    """
    STRICT_ENV=true 일 때 필수 환경변수를 강제 검증.
    개발 단계에서는 경고만 출력하고 서버는 뜨도록 함.
    """
    if settings.strict_env:
        missing = []
        if not settings.openai_api_key:
            missing.append("OPENAI_API_KEY")
        if missing:
            raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")
    else:
        if not settings.openai_api_key:
            logging.warning(
                "[config] OPENAI_API_KEY not set — chat/generation/tagging 기능은 키 설정 전까지 동작하지 않습니다."
            )
