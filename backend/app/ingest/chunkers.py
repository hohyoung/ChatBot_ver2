from __future__ import annotations
from typing import Iterable, List


def merge_blocks_to_chunks(
    blocks: Iterable[str],
    *,
    min_chars: int = 500,
    max_chars: int = 1200,
    overlap: int = 150,
) -> List[str]:
    """
    문단 리스트를 받아 길이 범위에 맞춰 청크로 병합.
    - 너무 짧은 것은 이전/다음과 합치고, 너무 긴 것은 적당히 잘라서 겹침(overlap) 부여.
    """
    chunks: List[str] = []
    buf: List[str] = []
    size = 0

    def flush():
        nonlocal buf, size
        if buf:
            text = "\n".join(buf).strip()
            if text:
                chunks.append(text)
            buf, size = [], 0

    for block in blocks:
        b = block.strip()
        if not b:
            continue
        if size + len(b) + 1 <= max_chars:
            buf.append(b)
            size += len(b) + 1
            continue

        # 현재 buf를 청크로 내보내기
        if size >= min_chars:
            flush()
            buf.append(b)
            size = len(b)
        else:
            # 최소 길이 미달이면 조금 오버해도 합치기
            buf.append(b)
            size += len(b) + 1
            flush()

    flush()

    # 긴 청크는 잘라서 overlap 부여
    final: List[str] = []
    for ch in chunks:
        if len(ch) <= max_chars:
            final.append(ch)
            continue
        start = 0
        while start < len(ch):
            end = min(len(ch), start + max_chars)
            part = ch[start:end]
            final.append(part.strip())
            if end == len(ch):
                break
            start = end - overlap  # 겹침
            if start < 0:
                start = 0
    return [c for c in final if c]
