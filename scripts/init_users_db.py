#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path

# repo root(chatBot_ver2) 를 sys.path 에 추가
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# 루트 기준으로 import
from backend.app.db.database import Base, engine  # noqa: E402
from backend.app.db import models  # noqa: F401,E402  # 모델 import가 있어야 테이블 생성됨

def main():
    Base.metadata.create_all(bind=engine)
    print(f"[OK] users DB initialized. url={engine.url}")

if __name__ == "__main__":
    main()
