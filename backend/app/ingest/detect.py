from __future__ import annotations
from pathlib import Path


def detect_type(p: Path) -> str:
    ext = p.suffix.lower()
    if ext in {".pdf"}:
        return "pdf"
    if ext in {".docx"}:
        return "docx"
    if ext in {".txt"}:
        return "txt"
    if ext in {".html", ".htm"}:
        return "html"
    return "unknown"
