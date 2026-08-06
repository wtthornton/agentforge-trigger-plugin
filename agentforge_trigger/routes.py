"""HTTP routes for the trigger-test plugin (TAP-760).

Endpoints:
  GET    /api/trigger-test/status                — health / version
  POST   /api/trigger-test/submit                — enqueue a job via AgentScheduler
  GET    /api/trigger-test/jobs                  — list all jobs
  DELETE /api/trigger-test/jobs/{job_id}         — cancel a job

  POST   /api/trigger-demo/interval/start        — start an interval driver
  POST   /api/trigger-demo/cron/start            — start a cron driver (test-clock)
  GET    /api/trigger-demo/counter               — how many times drivers have fired
  DELETE /api/trigger-demo/drivers               — stop + remove all drivers

TAP-760 AC references ``DELETE /api/plugins/trigger-demo``; the core plugin
registry's ``DELETE /api/plugins/{id}`` is a *soft disable* that flips a flag
but does not notify plugins to stop background tasks. This plugin exposes its
own lifecycle endpoint with the same intent (``DELETE /api/trigger-demo/drivers``)
— wiring that to the registry's disable hook is a follow-up.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, time, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from agentforge_trigger import __version__
from agentforge_trigger.trigger_driver import (
    CronDriver,
    IntervalDriver,
    _BaseDriver,
)

router = APIRouter(prefix="/api/trigger-test", tags=["trigger-test"])
demo_router = APIRouter(prefix="/api/trigger-demo", tags=["trigger-demo"])


class SubmitRequest(BaseModel):
    agent_name: str = "trigger-test-agent"
    prompt: str = "test"
    priority: int = 0


@router.get("/status")
async def status() -> dict[str, Any]:
    return {"status": "ok", "plugin": "trigger-test", "version": __version__}


@router.post("/submit")
async def submit(body: SubmitRequest, request: Request) -> dict[str, Any]:
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is None:
        return {"submitted": False, "reason": "no scheduler on app.state"}
    job = await scheduler.submit(body.agent_name, body.prompt, priority=body.priority)
    return {"submitted": True, "job_id": job.id, "state": job.state}


@router.get("/jobs")
async def list_jobs(request: Request) -> dict[str, Any]:
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is None:
        return {"jobs": []}
    jobs = scheduler.list_jobs()
    return {"jobs": [j.model_dump() for j in jobs]}


@router.delete("/jobs/{job_id}")
async def cancel_job(job_id: str, request: Request) -> dict[str, Any]:
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is None:
        raise HTTPException(status_code=404, detail="no scheduler")
    cancelled = await scheduler.cancel(job_id)
    return {"cancelled": cancelled, "job_id": job_id}


# ---------------------------------------------------------------------------
# Trigger demo routes (interval + cron)
# ---------------------------------------------------------------------------


_COUNTER_STATE_KEY = "_trigger_demo_state"


class _DemoState:
    def __init__(self) -> None:
        self.drivers: list[_BaseDriver] = []
        self.counter: int = 0
        self.skipped: int = 0

    async def tick(self) -> None:
        self.counter += 1


def _get_state(request: Request) -> _DemoState:
    state = getattr(request.app.state, _COUNTER_STATE_KEY, None)
    if state is None:
        state = _DemoState()
        setattr(request.app.state, _COUNTER_STATE_KEY, state)
    return state


class IntervalStartRequest(BaseModel):
    interval_seconds: float = Field(gt=0.0, le=10.0)
    market_hours_only: bool = False


@demo_router.post("/interval/start")
async def start_interval(
    body: IntervalStartRequest, request: Request
) -> dict[str, Any]:
    state = _get_state(request)
    gate = _default_market_hours_gate if body.market_hours_only else None
    driver = IntervalDriver(state.tick, body.interval_seconds, market_hours_gate=gate)
    driver.start()
    state.drivers.append(driver)
    return {"started": True, "interval_seconds": body.interval_seconds}


class CronStartRequest(BaseModel):
    # Pretend-cron: just wait this many seconds to each next fire, as computed
    # against the plugin's own clock. Kept simple so tests can inject a fake
    # clock via app.state and drive the scheduler deterministically.
    interval_seconds: float = Field(gt=0.0, le=10.0)
    market_hours_only: bool = False


@demo_router.post("/cron/start")
async def start_cron(body: CronStartRequest, request: Request) -> dict[str, Any]:
    state = _get_state(request)
    clock = getattr(request.app.state, "trigger_demo_clock", datetime.now)
    step = timedelta(seconds=body.interval_seconds)

    def _next(now: datetime) -> datetime:
        return now + step

    gate = _default_market_hours_gate if body.market_hours_only else None
    driver = CronDriver(state.tick, _next, market_hours_gate=gate, clock=clock)
    driver.start()
    state.drivers.append(driver)
    return {"started": True, "step_seconds": body.interval_seconds}


@demo_router.get("/counter")
async def counter(request: Request) -> dict[str, Any]:
    state = _get_state(request)
    total_ticks = sum(d.tick_count for d in state.drivers)
    skipped = sum(d.skipped_count for d in state.drivers)
    return {
        "counter": state.counter,
        "driver_ticks": total_ticks,
        "skipped": skipped,
        "running_drivers": sum(1 for d in state.drivers if d.running),
    }


@demo_router.delete("/drivers")
async def stop_all_drivers(request: Request) -> dict[str, Any]:
    state = _get_state(request)
    stopped = 0
    for d in state.drivers:
        if d.running:
            await d.stop()
            stopped += 1
    # Small yield so any in-flight cancellations settle.
    await asyncio.sleep(0)
    state.drivers.clear()
    return {"stopped": stopped}


def _default_market_hours_gate(now: datetime) -> bool:
    """Simplistic gate: allow ticks only during 09:30–16:00 local time (any day).

    Real market-hours logic would consult a calendar for holidays; this test rig
    only cares about the gate shape, not the trading calendar.
    """
    return time(9, 30) <= now.time() <= time(16, 0)
