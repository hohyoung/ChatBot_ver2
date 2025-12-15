from __future__ import annotations
import logging
import os
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

    콘솔: WARNING 이상만 출력 (최소한의 로그)
    파일: DEBUG/INFO 포함 상세 로그 저장 (log.txt)

    .env:
      LOG_LEVEL=INFO|DEBUG  (파일 로그 레벨)
      LOG_TO_FILE=true|false
      CONSOLE_LOG_LEVEL=WARNING|INFO|DEBUG  (콘솔 로그 레벨, 기본 WARNING)
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # 파일 로그 레벨 (상세)
    file_level_name = (os.getenv("LOG_LEVEL") or "INFO").upper()
    file_level = getattr(logging, file_level_name, logging.INFO)

    # 콘솔 로그 레벨 (최소)
    console_level_name = (os.getenv("CONSOLE_LOG_LEVEL") or "WARNING").upper()
    console_level = getattr(logging, console_level_name, logging.WARNING)

    fmt = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    fmt_console = "%(levelname)s [%(name)s] %(message)s"  # 콘솔은 간결하게

    handlers: list[logging.Handler] = []

    # 콘솔 핸들러 (WARNING 이상만)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(logging.Formatter(fmt_console))
    handlers.append(console_handler)

    # 파일 핸들러 (상세 로그)
    if (os.getenv("LOG_TO_FILE", "true") or "true").lower() in ("1", "true", "yes"):
        fh = RotatingFileHandler(
            LOGS_DIR / "log.txt", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        fh.setLevel(file_level)
        fh.setFormatter(logging.Formatter(fmt))
        handlers.append(fh)

    # 루트 로거는 가장 낮은 레벨로 설정 (핸들러에서 필터링)
    logging.basicConfig(level=logging.DEBUG, format=fmt, handlers=handlers, force=True)

    # 외부 라이브러리 로그 레벨 조정 (WARNING 이상만 출력)
    for logger_name in QUIET_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
