from __future__ import annotations
from pathlib import Path
from typing import List
from bs4 import BeautifulSoup

def parse_html(path: Path) -> List[str]:
    html = path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "html.parser")
    # 스크립트/스타일 제거
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    blocks = [b.strip() for b in text.splitlines() if b.strip()]
    return blocks
