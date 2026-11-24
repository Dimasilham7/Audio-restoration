"""Single-worker job queue with SSE progress."""

from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from audiorestorer_engine.pipeline.progress import CancelledError, JobContext
from audiorestorer_engine.pipeline.restore import analyze_media, process_media
from audiorestorer_engine.schemas import RestorationSettings


class JobKind(str, Enum):
    analyze = "analyze"
    process = "process"


class JobState(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


@dataclass
class JobRecord:
    id: str
    kind: JobKind
    state: JobState = JobState.queued
    progress: float = 0.0
    stage: str = ""
    message: str = ""
    media_path: str = ""
    output_path: str | None = None
    work_dir: str | None = None
    settings: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: str | None = None
    cancel_flag: bool = False
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    events: deque = field(default_factory=lambda: deque(maxlen=200))
    event_cond: threading.Condition = field(default_factory=threading.Condition)


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._queue: deque[str] = deque()
        self._lock = threading.Lock()
        self._worker = threading.Thread(target=self._run_worker, name="engine-worker", daemon=True)
        self._worker.start()

    def create(
        self,
        kind: JobKind,
        media_path: str,
        *,
        output_path: str | None = None,
        work_dir: str | None = None,
        settings: dict[str, Any] | None = None,
    ) -> JobRecord:
        job = JobRecord(
            id=str(uuid.uuid4()),
            kind=kind,
            media_path=media_path,
            output_path=output_path,
            work_dir=work_dir,
            settings=settings or {},
        )
        with self._lock:
            self._jobs[job.id] = job
            self._queue.append(job.id)
        self._emit(job, {"type": "queued", "progress": 0.0})
        return job

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> JobRecord | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            job.cancel_flag = True
            if job.state == JobState.queued:
                job.state = JobState.cancelled
                job.updated_at = time.time()
                try:
                    self._queue.remove(job_id)
                except ValueError:
                    pass
            self._emit(job, {"type": "cancelled", "progress": job.progress})
            return job

    def snapshot(self, job: JobRecord) -> dict[str, Any]:
        return {
            "id": job.id,
            "kind": job.kind.value,
            "state": job.state.value,
            "progress": job.progress,
            "stage": job.stage,
            "message": job.message,
            "media_path": job.media_path,
            "output_path": job.output_path,
            "error": job.error,
            "result": job.result,
        }

    def _emit(self, job: JobRecord, event: dict[str, Any]) -> None:
        event = {**event, "job_id": job.id, "stage": job.stage, "message": job.message}
        with job.event_cond:
            job.events.append(event)
            job.event_cond.notify_all()

    def _run_worker(self) -> None:
        while True:
            job_id = None
            with self._lock:
                if self._queue:
                    job_id = self._queue.popleft()
                    job = self._jobs.get(job_id)
                    if job and job.state == JobState.queued:
                        job.state = JobState.running
                        job.updated_at = time.time()
                    else:
                        job_id = None
            if not job_id:
                time.sleep(0.05)
                continue
            self._execute(job_id)

    def _execute(self, job_id: str) -> None:
        job = self.get(job_id)
        if not job:
            return

        def on_progress(p: float, stage: str, message: str | None) -> None:
            job.progress = p
            job.stage = stage
            job.message = message or ""
            job.updated_at = time.time()
            self._emit(
                job,
                {"type": "progress", "progress": p, "stage": stage, "message": message},
            )

        ctx = JobContext(
            progress=on_progress,
            is_cancelled=lambda: job.cancel_flag,
        )
        try:
            settings = RestorationSettings(**job.settings) if job.settings else RestorationSettings()
            if job.kind == JobKind.analyze:
                report = analyze_media(job.media_path, work_dir=job.work_dir, ctx=ctx)
            else:
                report = process_media(
                    job.media_path,
                    job.output_path,
                    settings=settings,
                    work_dir=job.work_dir,
                    ctx=ctx,
                )
            job.result = report.model_dump()
            job.state = JobState.completed
            job.progress = 1.0
            job.updated_at = time.time()
            self._emit(job, {"type": "completed", "progress": 1.0, "result": job.result})
        except CancelledError:
            job.state = JobState.cancelled
            job.updated_at = time.time()
            self._emit(job, {"type": "cancelled", "progress": job.progress})
        except Exception as exc:  # noqa: BLE001
            job.state = JobState.failed
            job.error = str(exc)
            job.updated_at = time.time()
            self._emit(job, {"type": "failed", "progress": job.progress, "error": str(exc)})


manager = JobManager()
