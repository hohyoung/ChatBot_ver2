from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Tuple
from fastapi import UploadFile

BASE_DIR = Path(__file__).resolve().parents[2]  # backend/
DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"

def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def save_upload_file(dst_dir: Path, uf: UploadFile) -> Path:
    """
    단일 업로드 파일을 dst_dir에 저장하고 실제 경로를 반환.
    파일명 충돌 시 자동으로 뒤에 숫자를 붙임.
    """
    ensure_dir(dst_dir)
    name = Path(uf.filename or "upload.bin").name
    stem, suffix = os.path.splitext(name)
    candidate = dst_dir / name
    i = 1
    while candidate.exists():
        candidate = dst_dir / f"{stem}_{i}{suffix}"
        i += 1
    with candidate.open("wb") as f:
        # FastAPI UploadFile은 SpooledTemporaryFile; chunks로 저장
        while True:
            chunk = uf.file.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
    return candidate

def save_batch(job_id: str, files: Iterable[UploadFile]) -> Tuple[int, int, list[Path]]:
    """
    여러 업로드 파일을 한 번에 저장.
    반환: (accepted_count, skipped_count, saved_paths)
    """
    dst = UPLOADS_DIR / job_id
    ensure_dir(dst)
    saved: list[Path] = []
    accepted, skipped = 0, 0
    for uf in files:
        try:
            p = save_upload_file(dst, uf)
            saved.append(p)
            accepted += 1
        except Exception:
            skipped += 1
    return accepted, skipped, saved
