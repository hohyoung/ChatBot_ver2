from __future__ import annotations
from dataclasses import dataclass, field
from threading import Lock
from typing import Dict, List
from app.models.schemas import IngestJobStatus
from app.services.logging import get_logger

log = get_logger("app.ingest.jobs")


@dataclass
class _Job:
    status: str = "pending"  # pending | running | succeeded | failed
    processed: int = 0
    total: int = 0
    errors: List[str] = field(default_factory=list)


class JobStore:
    def __init__(self):
        self._jobs: Dict[str, _Job] = {}
        self._lock = Lock()

    def start(self, job_id: str, total: int):
        with self._lock:
            self._jobs[job_id] = _Job(
                status="running", processed=0, total=total, errors=[]
            )
        log.info("job start job_id=%s total=%d", job_id, total)

    def inc(self, job_id: str):
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
        with self._lock:
            j = self._jobs.get(job_id)
            if j:
                j.errors.append(msg)
        log.error("job error job_id=%s %s", job_id, msg)

    def finish(self, job_id: str):
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
        with self._lock:
            j = self._jobs.get(job_id)
            if not j:
                return IngestJobStatus(status="pending", processed=0, total=0, errors=[])
            return IngestJobStatus(
                status=j.status, processed=j.processed, total=j.total, errors=list(j.errors)
            )


job_store = JobStore()
