from __future__ import annotations

import os
import re
from pathlib import Path
import shutil
from typing import Iterable, Tuple
from fastapi import UploadFile

BASE_DIR = Path(__file__).resolve().parents[2]  # backend/
DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
DOCS_DIR = BASE_DIR / "storage" / "docs"  # main.py에서 /static/docs 로 서빙됨
STORAGE_DIR = BASE_DIR / "storage"


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


def _slugify(name: str) -> str:
    name = name.strip().replace(" ", "_")
    name = re.sub(r"[^\w\-.]+", "", name)
    return name or "doc"


def publish_doc(src: Path, *, strategy: str = "move") -> tuple[Path, str]:
    """
    업로드 원본을 storage/docs로 복사하고, 프론트에서 열 수 있는 URL을 반환.
    return: (dest_path, url)  // url 예: /static/docs/<filename.pdf>
    """

    ensure_dir(DOCS_DIR)
    filename = _slugify(src.name)
    dst = DOCS_DIR / filename
    # 중복 시 덮어쓰지 않도록 유니크 이름 부여
    if dst.exists():
        stem, suf = os.path.splitext(filename)
        i = 1
        while True:
            cand = DOCS_DIR / f"{stem}__{i}{suf}"
            if not cand.exists():
                dst = cand
                break
            i += 1
    try:
        if strategy == "hardlink":
            # 같은 드라이브일 때 하드링크 시도 (Windows 권한에 따라 실패 가능)
            os.link(src, dst)
            # 하드링크는 원본 삭제 시에도 데이터 유지됨. 원본을 지워 중복 방지:
            try:
                src.unlink(missing_ok=True)
            except Exception:
                pass
        elif strategy == "move":
            shutil.move(
                src, dst
            )  # 같은 드라이브면 O(1) rename, 다르면 copy 후 원본 삭제
        else:
            shutil.copy2(src, dst)  # 백업 옵션
    except Exception:
        # 안전망: 복사로 폴백
        shutil.copy2(src, dst)
        try:
            src.unlink(missing_ok=True)
        except Exception:
            pass
    url = f"/static/docs/{dst.name}"
    return dst, url
