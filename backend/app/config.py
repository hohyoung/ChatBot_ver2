import os
import logging
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv

# 이 config.py 파일의 위치를 기준으로 .env 파일의 절대 경로를 계산합니다.
# (config.py -> app 폴더 -> backend 폴더)
backend_dir = Path(__file__).resolve().parent.parent
dotenv_path = backend_dir / ".env"

# 💡 계산된 절대 경로를 사용하여 .env 파일을 명시적으로 로드합니다.
load_dotenv(dotenv_path=dotenv_path)

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

    # API 키 풀 (라운드로빈용) - P0-7
    # OPENAI_API_KEYS 환경변수로 콤마 구분 키 지정 가능
    # 예: OPENAI_API_KEYS=sk-key1,sk-key2,sk-key3
    openai_api_keys: list[str] = field(
        default_factory=lambda: [
            key.strip()
            for key in (os.getenv("OPENAI_API_KEYS") or "").split(",")
            if key.strip()
        ] or [os.getenv("OPENAI_API_KEY", "")]  # 폴백: 기존 단일 키
    )

    # 새 이름(권장)과 구 이름 둘 다 허용
    openai_base_url: str | None = _norm_openai_base(
        _getenv("OPENAI_BASE_URL") or _getenv("OPENAI_API_BASE")
    )
    openai_model: str = _getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
    # 고급 모델: 복잡한 추론이 필요한 작업용 (답변 생성, 리랭킹, Vision)
    openai_advanced_model: str = _getenv("OPENAI_ADVANCED_MODEL", "gpt-4o")
    openai_embed_model: str = _getenv("OPENAI_EMBED_MODEL", "text-embedding-3-large")

    # Vector DB (Chroma)
    chroma_persist_dir: str = (
        _getenv("CHROMA_PERSIST_DIR", "./data/chroma") or "./data/chroma"
    )
    collection_name: str = (
        _getenv("COLLECTION_NAME", "knowledge_base") or "knowledge_base"
    )

    # Auth (문서 업로드 보호용) — JWT 초 단위(exp)로 통일
    jwt_secret: str | None = _getenv("JWT_SECRET")
    # 우선순위: JWT_EXPIRES_IN(초) > JWT_EXPIRE_MINUTES(분) > 기본 3600
    _expires_in_env = _getenv("JWT_EXPIRES_IN")
    _expire_minutes_env = _getenv("JWT_EXPIRE_MINUTES")
    jwt_expires_in: int = (
        int(_expires_in_env)
        if _expires_in_env
        else (int(_expire_minutes_env) * 60 if _expire_minutes_env else 3600)
    )

    # 내부 메일 도메인(회원가입 허용 도메인) — 콤마로 여러 개 지정 가능
    # 예: INTERNAL_EMAIL_DOMAIN=soosan.com,soosan.co.kr
    internal_email_domains: list[str] = field(
        default_factory=lambda: [
            d.strip().lower()
            for d in (
                os.getenv("INTERNAL_EMAIL_DOMAIN") or "soosan.com,soosan.co.kr"
            ).split(",")
            if d.strip()
        ]
    )

    # CORS
    cors_allow_origins: str = (
        _getenv("CORS_ALLOW_ORIGINS", "http://localhost:5173")
        or "http://localhost:5173"
    )

    require_auth_upload: bool = (
        _getenv("REQUIRE_AUTH_UPLOAD", "false") or "false"
    ).lower() in ("1", "true", "yes")


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
