"""Background jobs with progress, ETA and a persisted record (survives restarts as history)."""
from __future__ import annotations

import logging
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

from sqlalchemy import select

from .db import Job, session_scope

logger = logging.getLogger("jobs")
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="job")
_cancel: Dict[str, threading.Event] = {}


class JobContext:
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.started = time.time()
        self._last_write = 0.0

    @property
    def cancelled(self) -> bool:
        ev = _cancel.get(self.job_id)
        return bool(ev and ev.is_set())

    def progress(self, fraction: float, message: str = "", force: bool = False) -> None:
        fraction = max(0.0, min(1.0, fraction))
        now = time.time()
        if not force and now - self._last_write < 0.5:
            return
        self._last_write = now
        elapsed = now - self.started
        eta = (elapsed / fraction - elapsed) if fraction > 0.01 else None
        with session_scope() as s:
            j = s.get(Job, self.job_id)
            if j:
                j.progress = round(fraction, 4)
                j.eta_seconds = round(eta, 1) if eta is not None else None
                if message:
                    j.message = message
        if self.cancelled:
            raise JobCancelled()


class JobCancelled(Exception):
    pass


def job_dict(j: Job) -> Dict[str, Any]:
    return {"job_id": j.id, "kind": j.kind, "league": j.league, "status": j.status, "progress": j.progress,
            "eta_seconds": j.eta_seconds, "message": j.message, "params": j.params, "result": j.result,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "started_at": j.started_at.isoformat() if j.started_at else None,
            "finished_at": j.finished_at.isoformat() if j.finished_at else None}


def submit(kind: str, fn: Callable[[JobContext], Any], league: Optional[str] = None,
           params: Optional[Dict[str, Any]] = None) -> str:
    job_id = str(uuid.uuid4())
    with session_scope() as s:
        s.add(Job(id=job_id, kind=kind, league=league, status="queued", params=params or {}, message="Queued"))
    _cancel[job_id] = threading.Event()

    def run():
        ctx = JobContext(job_id)
        with session_scope() as s:
            j = s.get(Job, job_id)
            j.status, j.started_at, j.message = "running", datetime.now(timezone.utc), "Started"
        try:
            result = fn(ctx)
            with session_scope() as s:
                j = s.get(Job, job_id)
                j.status, j.progress, j.eta_seconds = "completed", 1.0, 0
                j.result = result
                j.message = (result or {}).get("message", "Completed") if isinstance(result, dict) else "Completed"
                j.finished_at = datetime.now(timezone.utc)
            logger.info("Job %s (%s %s) completed", job_id[:8], kind, league or "")
        except JobCancelled:
            with session_scope() as s:
                j = s.get(Job, job_id)
                j.status, j.message, j.finished_at = "cancelled", "Cancelled", datetime.now(timezone.utc)
        except Exception as e:
            logger.error("Job %s (%s %s) failed: %s", job_id[:8], kind, league or "", e)
            with session_scope() as s:
                j = s.get(Job, job_id)
                j.status, j.message, j.finished_at = "failed", str(e), datetime.now(timezone.utc)
                j.result = {"error": str(e), "trace": traceback.format_exc()[-2000:]}
        finally:
            _cancel.pop(job_id, None)

    _executor.submit(run)
    return job_id


def cancel(job_id: str) -> bool:
    ev = _cancel.get(job_id)
    if ev:
        ev.set()
        return True
    return False


def get(job_id: str) -> Optional[Dict[str, Any]]:
    with session_scope() as s:
        j = s.get(Job, job_id)
        return job_dict(j) if j else None


def recent(limit: int = 50, kind: Optional[str] = None):
    with session_scope() as s:
        q = select(Job).order_by(Job.created_at.desc()).limit(limit)
        if kind:
            q = q.where(Job.kind == kind)
        return [job_dict(j) for j in s.execute(q).scalars()]


def mark_interrupted() -> None:
    """Jobs left running by a previous process are marked failed so clients don't wait forever."""
    with session_scope() as s:
        for j in s.execute(select(Job).where(Job.status.in_(["queued", "running"]))).scalars():
            j.status, j.message = "failed", "Interrupted by server restart (re-run to resume)"
