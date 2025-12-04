from __future__ import annotations
from dataclasses import dataclass, field
from threading import Lock
from typing import Dict, List, Optional
from datetime import datetime
from app.models.schemas import IngestJobStatus
from app.services.logging import get_logger

log = get_logger("app.ingest.jobs")


@dataclass
class _Job:
    status: str = "pending"  # pending | running | succeeded | failed
    processed: int = 0
    total: int = 0
    errors: List[str] = field(default_factory=list)
    owner_id: Optional[int] = None  # 업로드한 사용자 ID
    created_at: datetime = field(default_factory=datetime.utcnow)


class JobStore:
    """
    업로드 작업 상태 관리 (인메모리)

    특징:
    - 사용자별 진행 중인 job 추적
    - 스레드 안전 (Lock 사용)
    - 서버 재시작 시 소실됨 (영구 저장 필요 시 Redis/DB 사용)
    """

    def __init__(self):
        self._jobs: Dict[str, _Job] = {}
        self._user_jobs: Dict[int, List[str]] = {}  # owner_id -> [job_id, ...]
        self._lock = Lock()

    def start(self, job_id: str, total: int, owner_id: Optional[int] = None):
        """새 작업 시작"""
        with self._lock:
            self._jobs[job_id] = _Job(
                status="running",
                processed=0,
                total=total,
                errors=[],
                owner_id=owner_id,
                created_at=datetime.utcnow(),
            )
            # 사용자별 job 매핑 추가
            if owner_id is not None:
                if owner_id not in self._user_jobs:
                    self._user_jobs[owner_id] = []
                self._user_jobs[owner_id].append(job_id)
        log.info("job start job_id=%s total=%d owner_id=%s", job_id, total, owner_id)

    def inc(self, job_id: str):
        """진행률 증가"""
        with self._lock:
            j = self._jobs.get(job_id)
            if j:
                j.processed += 1
                cur = j.processed
        log.debug(
            "job progress job_id=%s processed=%s",
            job_id,
            cur if "cur" in locals() else "?",
        )

    def add_error(self, job_id: str, msg: str):
        """에러 추가"""
        with self._lock:
            j = self._jobs.get(job_id)
            if j:
                j.errors.append(msg)
        log.error("job error job_id=%s %s", job_id, msg)

    def finish(self, job_id: str):
        """작업 완료 처리"""
        with self._lock:
            j = self._jobs.get(job_id)
            status = "failed"
            if j and not j.errors:
                j.status = "succeeded"
                status = "succeeded"
            elif j:
                j.status = "failed"
        log.info("job finish job_id=%s status=%s", job_id, status)

    def get(self, job_id: str) -> IngestJobStatus:
        """특정 job 상태 조회"""
        with self._lock:
            j = self._jobs.get(job_id)
            if not j:
                return IngestJobStatus(status="pending", processed=0, total=0, errors=[])
            return IngestJobStatus(
                status=j.status, processed=j.processed, total=j.total, errors=list(j.errors)
            )

    def get_active_jobs_for_user(self, owner_id: int) -> List[Dict]:
        """
        특정 사용자의 진행 중인 job 목록 조회

        Returns:
            [{"job_id": str, "status": str, "processed": int, "total": int}, ...]
        """
        with self._lock:
            job_ids = self._user_jobs.get(owner_id, [])
            active_jobs = []

            for job_id in job_ids:
                j = self._jobs.get(job_id)
                if j and j.status in ("pending", "running"):
                    active_jobs.append({
                        "job_id": job_id,
                        "status": j.status,
                        "processed": j.processed,
                        "total": j.total,
                        "created_at": j.created_at.isoformat() if j.created_at else None,
                    })

            return active_jobs

    def cleanup_old_jobs(self, max_age_hours: int = 24):
        """
        오래된 완료 job 정리 (메모리 관리)

        Args:
            max_age_hours: 이보다 오래된 완료 job 삭제
        """
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)

        with self._lock:
            to_delete = []
            for job_id, j in self._jobs.items():
                if j.status in ("succeeded", "failed") and j.created_at < cutoff:
                    to_delete.append(job_id)

            for job_id in to_delete:
                j = self._jobs.pop(job_id, None)
                if j and j.owner_id is not None:
                    user_jobs = self._user_jobs.get(j.owner_id, [])
                    if job_id in user_jobs:
                        user_jobs.remove(job_id)

            if to_delete:
                log.info("cleanup_old_jobs: removed %d jobs", len(to_delete))


job_store = JobStore()
