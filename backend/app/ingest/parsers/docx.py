from __future__ import annotations
from pathlib import Path
from typing import List
import docx  # python-docx

def parse_docx(path: Path) -> List[str]:
    """문단 단위 텍스트 리스트."""
    d = docx.Document(str(path))
    paras = [p.text.strip() for p in d.paragraphs if p.text and p.text.strip()]
    return paras
