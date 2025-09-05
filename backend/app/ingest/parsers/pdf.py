from __future__ import annotations
from pathlib import Path
from typing import List
from pypdf import PdfReader

def parse_pdf(path: Path) -> List[str]:
    """페이지 단위 텍스트 리스트 반환."""
    out: List[str] = []
    with path.open("rb") as f:
        reader = PdfReader(f)
        for page in reader.pages:
            text = (page.extract_text() or "").strip()
            if text:
                out.append(text)
    return out
