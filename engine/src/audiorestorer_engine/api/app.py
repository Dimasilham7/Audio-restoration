"""FastAPI application for the local engine sidecar."""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from audiorestorer_engine import __version__
from audiorestorer_engine.api.jobs import JobKind, manager
from audiorestorer_engine.pipeline.restore import analyze_media, process_media
from audiorestorer_engine.planning.planner import plan as build_plan
from audiorestorer_engine.schemas import AnalysisResult, Preset, RestorationSettings, TreatmentPlan

app = FastAPI(title="AudioRestorer Engine", version=__version__)


@app.on_event("startup")
def _warmup() -> None:
    # Import heavy modules so first click is fast
    import numpy  # noqa: F401
    import scipy  # noqa: F401
    import soundfile  # noqa: F401

    from audiorestorer_engine.analysis import analyzer  # noqa: F401
    from audiorestorer_engine.dsp import filters  # noqa: F401

    port = os.environ.get("AUDIORESTORER_PORT", "")
    if port:
        print(f"READY port={port}", flush=True)


def _check_token(authorization: str | None) -> None:
    expected = os.environ.get("AUDIORESTORER_TOKEN")
    if not expected:
        return
    if not authorization or authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="Unauthorized")


class AnalyzeRequest(BaseModel):
    audio_path: str | None = None
    media_path: str | None = None
    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class PlanRequest(BaseModel):
    analysis: AnalysisResult
    settings: RestorationSettings | None = None
    preset: Preset | None = None


class RenderRequest(BaseModel):
    media_path: str
    output_path: str | None = None
    settings: RestorationSettings | None = None
    work_dir: str | None = None
    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class CreateJobRequest(BaseModel):
    kind: JobKind
    media_path: str
    output_path: str | None = None
    work_dir: str | None = None
    settings: RestorationSettings | None = None


@app.get("/v1/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.get("/v1/capabilities")
def capabilities(authorization: str | None = Header(default=None)) -> dict:
    _check_token(authorization)
    from audiorestorer_engine.adapters.deepfilternet import is_available as dfn_available

    models = []
    if dfn_available():
        models.append("deepfilternet3")
    return {
        "devices": [{"id": "cpu", "name": "CPU"}],
        "cuda_available": False,
        "installed_models": models,
        "max_chunk_sec": 10,
        "features": ["analyze", "plan", "dsp_restore", "deepfilternet", "remux", "jobs", "sse"],
    }


@app.post("/v1/analyze")
def analyze(req: AnalyzeRequest, authorization: str | None = Header(default=None)) -> dict:
    _check_token(authorization)
    path = req.media_path or req.audio_path
    if not path or not Path(path).exists():
        raise HTTPException(status_code=400, detail="media_path/audio_path required")
    report = analyze_media(path)
    return {
        "job_id": req.job_id,
        "analysis": report.analysis.model_dump(),
        "plan": report.plan.model_dump(),
    }


@app.post("/v1/plan")
def plan_endpoint(
    req: PlanRequest, authorization: str | None = Header(default=None)
) -> TreatmentPlan:
    _check_token(authorization)
    settings = req.settings or RestorationSettings()
    if req.preset:
        settings.preset = req.preset
    return build_plan(req.analysis, settings)


@app.post("/v1/render")
def render(req: RenderRequest, authorization: str | None = Header(default=None)) -> dict:
    _check_token(authorization)
    if not Path(req.media_path).exists():
        raise HTTPException(status_code=400, detail="media_path not found")
    report = process_media(
        req.media_path,
        req.output_path,
        settings=req.settings or RestorationSettings(),
        work_dir=req.work_dir,
    )
    return {
        "job_id": req.job_id,
        "report": report.model_dump(),
    }


@app.post("/v1/jobs")
def create_job(req: CreateJobRequest, authorization: str | None = Header(default=None)) -> dict:
    _check_token(authorization)
    if not Path(req.media_path).exists():
        raise HTTPException(status_code=400, detail="media_path not found")
    settings = req.settings.model_dump() if req.settings else {}
    job = manager.create(
        req.kind,
        req.media_path,
        output_path=req.output_path,
        work_dir=req.work_dir,
        settings=settings,
    )
    return manager.snapshot(job)


@app.get("/v1/jobs/{job_id}")
def get_job(job_id: str, authorization: str | None = Header(default=None)) -> dict:
    _check_token(authorization)
    job = manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return manager.snapshot(job)


@app.post("/v1/jobs/{job_id}/cancel")
def cancel_job(job_id: str, authorization: str | None = Header(default=None)) -> dict:
    _check_token(authorization)
    job = manager.cancel(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return manager.snapshot(job)


@app.get("/v1/jobs/{job_id}/events")
async def job_events(job_id: str, authorization: str | None = Header(default=None)) -> StreamingResponse:
    _check_token(authorization)
    job = manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")

    async def event_stream():
        idx = 0
        while True:
            with job.event_cond:
                while idx >= len(job.events):
                    if job.state.value in ("completed", "failed", "cancelled"):
                        # flush any remaining then stop
                        break
                    await asyncio.to_thread(job.event_cond.wait, 0.5)
                # copy new events
                batch = list(job.events)[idx:]
                idx = len(job.events)
            for ev in batch:
                yield f"data: {json.dumps(ev)}\n\n"
                if ev.get("type") in ("completed", "failed", "cancelled"):
                    return
            if job.state.value in ("completed", "failed", "cancelled") and idx >= len(job.events):
                return
            await asyncio.sleep(0.05)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
