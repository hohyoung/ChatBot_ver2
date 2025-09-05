from __future__ import annotations
from pathlib import Path
from typing import List

def parse_txt(path: Path) -> List[str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    # 빈 줄 기준 문단 분리
    blocks = [b.strip() for b in text.splitlines() if b.strip()]
    return blocks
