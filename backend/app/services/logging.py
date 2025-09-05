from __future__ import annotations
import os, logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]  # backend/
LOGS_DIR = BASE_DIR / "logs"

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

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
