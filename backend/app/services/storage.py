from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Iterable, Optional, Tuple, List

from fastapi import UploadFile

# 디렉터리 설정
BASE_DIR = Path(__file__).resolve().parents[2]  # backend/
DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"  # 업로드 원본이 job_id별로 저장되는 곳
DOCS_DIR = BASE_DIR / "storage" / "docs"  # 최종 공개/비공개 문서 저장소
PUBLIC_DIR = DOCS_DIR / "public"
PRIVATE_DIR = DOCS_DIR / "private"

# 디렉터리 보장
for _d in (UPLOADS_DIR, PUBLIC_DIR, PRIVATE_DIR):
    _d.mkdir(parents=True, exist_ok=True)


# -----------------------------
# 유틸
# -----------------------------
def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _slugify(name: str) -> str:
    # 공백 -> 언더스코어, 허용 문자만 남김
    name = name.strip().replace(" ", "_")
    name = re.sub(r"[^\w\-.]+", "", name)
    return name or "doc"


def _unique_path(dst_dir: Path, filename: str) -> Path:
    """
    파일명이 중복될 경우 -1, -2 ... 를 붙여 고유 경로 생성
    """
    base = Path(filename).stem
    ext = Path(filename).suffix
    cand = dst_dir / f"{base}{ext}"
    i = 1
    while cand.exists():
        cand = dst_dir / f"{base}-{i}{ext}"
        i += 1
    return cand


# -----------------------------
# 업로드 저장 (router/docs.py에서 사용)
# -----------------------------
def save_upload_file(dst_dir: Path, uf: UploadFile) -> Path:
    """
    단일 UploadFile을 dst_dir로 저장하고 저장된 경로를 반환.
    """
    ensure_dir(dst_dir)
    # 업로드 파일명 정리
    filename = _slugify(uf.filename or "file")
    out_path = _unique_path(dst_dir, filename)

    # SpooledTemporaryFile 대응: 스트리밍으로 저장
    with out_path.open("wb") as f:
        while True:
            chunk = uf.file.read(1024 * 1024)  # 1MB
            if not chunk:
                break
            f.write(chunk)

    return out_path


def save_batch(job_id: str, files: Iterable[UploadFile]) -> Tuple[int, int, List[Path]]:
    """
    여러 업로드 파일을 한 번에 저장.
    반환: (accepted_count, skipped_count, saved_paths)
    - 저장 위치: UPLOADS_DIR / job_id
    """
    dst = UPLOADS_DIR / job_id
    ensure_dir(dst)

    saved: List[Path] = []
    accepted, skipped = 0, 0

    for uf in files:
        try:
            p = save_upload_file(dst, uf)
            saved.append(p)
            accepted += 1
        except Exception:
            skipped += 1

    return accepted, skipped, saved


# -----------------------------
# 문서 퍼블리시(가시성 반영)
#  - 파이프라인에서 호출하여 storage/docs/{public|private}로 이동/복사
#  - public만 /static/docs/* URL 반환
# -----------------------------
def publish_doc(
    src: Path,
    *,
    strategy: str = "move",  # "move"|"copy" 등
    visibility: str = "org",  # "public"이면 공개
) -> Tuple[Path, Optional[str]]:
    """
    업로드 원본(src)을 storage/docs/{public|private}로 이동/복사하고,
    외부 미리보기 가능한 경우에만 URL을 반환한다.

    return: (dest_path, url_or_none)
    """
    vis = (visibility or "org").lower().strip()
    is_public = vis in {"public", "pub", "open"}

    dst_dir = PUBLIC_DIR if is_public else PRIVATE_DIR

    # 파일명 정리 + 중복 방지
    filename = _slugify(src.name)
    dst = _unique_path(dst_dir, filename)

    # 이동/복사 수행
    try:
        ensure_dir(dst.parent)
        if strategy == "move":
            # 같은 드라이브면 rename, 아니면 내부적으로 copy+삭제
            shutil.move(str(src), str(dst))
        else:
            shutil.copy2(str(src), str(dst))
    except Exception:
        # 문제가 생기면 복사로 폴백 후 원본 삭제 시도
        shutil.copy2(str(src), str(dst))
        try:
            src.unlink(missing_ok=True)
        except Exception:
            pass

    # URL은 public만 제공
    url = f"/static/docs/{dst.name}" if is_public else None
    return dst, url


def delete_files_by_relpaths(relpaths: Iterable[str]) -> dict:
    """
    storage/docs 하위 상대경로 목록을 받아 실제 파일을 삭제.
    반환: {"requested": N, "deleted": M, "errors": [(rel, str(err)), ...]}
    """
    base = DOCS_DIR.resolve()
    deleted, errors = 0, []
    rels = list(relpaths or [])
    for rel in rels:
        try:
            if not rel:
                continue
            target = (base / rel).resolve()
            # 안전장치: storage/docs 바깥을 가리키면 무시
            if not str(target).startswith(str(base)):
                errors.append((rel, "outside-docs"))
                continue
            if target.exists() and target.is_file():
                target.unlink()
                deleted += 1
        except Exception as e:
            errors.append((rel, str(e)))
    return {"requested": len(rels), "deleted": deleted, "errors": errors}
