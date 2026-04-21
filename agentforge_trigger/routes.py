"""HTTP routes for the trigger-test plugin (TAP-760).

Endpoints:
  GET  /api/trigger-test/status      — health / version
  POST /api/trigger-test/submit      — enqueue a job via AgentScheduler
  GET  /api/trigger-test/jobs        — list all jobs
  DELETE /api/trigger-test/jobs/{job_id} — cancel a job
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from agentforge_trigger import __version__

router = APIRouter(prefix="/api/trigger-test", tags=["trigger-test"])


class SubmitRequest(BaseModel):
    agent_name: str = "trigger-test-agent"
    prompt: str = "test"
    priority: int = 0


@router.get("/status")
async def status() -> dict:
    return {"status": "ok", "plugin": "trigger-test", "version": __version__}


@router.post("/submit")
async def submit(body: SubmitRequest, request: Request) -> dict:
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is None:
        return {"submitted": False, "reason": "no scheduler on app.state"}
    job = await scheduler.submit(body.agent_name, body.prompt, priority=body.priority)
    return {"submitted": True, "job_id": job.id, "state": job.state}


@router.get("/jobs")
async def list_jobs(request: Request) -> dict:
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is None:
        return {"jobs": []}
    jobs = scheduler.list_jobs()
    return {"jobs": [j.model_dump() for j in jobs]}


@router.delete("/jobs/{job_id}")
async def cancel_job(job_id: str, request: Request) -> dict:
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is None:
        raise HTTPException(status_code=404, detail="no scheduler")
    cancelled = await scheduler.cancel(job_id)
    return {"cancelled": cancelled, "job_id": job_id}
