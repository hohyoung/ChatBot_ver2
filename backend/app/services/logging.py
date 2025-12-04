from __future__ import annotations
import os, logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]  # backend/
LOGS_DIR = BASE_DIR / "logs"

# 로그 레벨을 WARNING 이상으로 설정할 외부 라이브러리들
QUIET_LOGGERS = [
    "httpx",           # HTTP Request: POST ... 매번 출력 방지
    "httpcore",        # httpx 내부
    "openai",          # OpenAI SDK 내부 로그
    "chromadb",        # ChromaDB 내부 로그
    "urllib3",         # HTTP 라이브러리
    "asyncio",         # 비동기 내부
    "watchfiles",      # 파일 감시
    "apscheduler",     # 스케줄러 상세 로그
]


def setup_logging() -> None:
    """
    콘솔 + 파일 로깅 설정.
    .env:
      LOG_LEVEL=INFO|DEBUG
      LOG_TO_FILE=true|false
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    level_name = (os.getenv("LOG_LEVEL") or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    fmt = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    handlers: list[logging.Handler] = [logging.StreamHandler()]

    if (os.getenv("LOG_TO_FILE", "true") or "true").lower() in ("1", "true", "yes"):
        fh = RotatingFileHandler(
            LOGS_DIR / "app.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        fh.setFormatter(logging.Formatter(fmt))
        handlers.append(fh)

    logging.basicConfig(level=level, format=fmt, handlers=handlers, force=True)

    # 외부 라이브러리 로그 레벨 조정 (WARNING 이상만 출력)
    for logger_name in QUIET_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
