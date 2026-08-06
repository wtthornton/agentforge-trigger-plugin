"""Unit tests for IntervalDriver / CronDriver (TAP-760).

Pure plugin — no AgentForge deps. Sleeps are short (<= 50ms) so the suite
runs under ~300ms total.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, time, timedelta

import pytest

from agentforge_trigger.trigger_driver import CronDriver, IntervalDriver


async def _make_tick() -> tuple[list[int], callable]:  # type: ignore[type-arg]
    """Helper returning (counter_list, tick_fn)."""
    hits: list[int] = []

    async def _tick() -> None:
        hits.append(1)

    return hits, _tick


async def test_interval_driver_fires_multiple_times() -> None:
    hits, tick = await _make_tick()
    d = IntervalDriver(tick, interval_seconds=0.02)
    d.start()
    await asyncio.sleep(0.15)
    await d.stop()
    assert len(hits) >= 3
    assert d.tick_count == len(hits)


async def test_interval_driver_stop_halts_ticks() -> None:
    hits, tick = await _make_tick()
    d = IntervalDriver(tick, interval_seconds=0.02)
    d.start()
    await asyncio.sleep(0.1)
    await d.stop()
    snapshot = len(hits)
    await asyncio.sleep(0.1)
    assert len(hits) == snapshot, "ticks should not fire after stop()"
    assert not d.running


async def test_interval_driver_double_start_is_idempotent() -> None:
    hits, tick = await _make_tick()
    d = IntervalDriver(tick, interval_seconds=0.02)
    d.start()
    d.start()  # second call no-ops
    await asyncio.sleep(0.08)
    await d.stop()
    # If double-start leaked a task we'd see 2x ticks; assert only one task ran.
    assert len(hits) <= 5  # soft upper bound; single task cannot produce more


async def test_interval_driver_rejects_non_positive() -> None:
    _hits, tick = await _make_tick()
    with pytest.raises(ValueError):
        IntervalDriver(tick, interval_seconds=0)


async def test_market_hours_gate_skips_outside_window() -> None:
    hits, tick = await _make_tick()

    # Clock fixed at 2am (off-market) → gate should skip.
    fixed_clock = lambda: datetime(2026, 4, 24, 2, 0, 0)  # noqa: E731

    def _gate(now: datetime) -> bool:
        return time(9, 30) <= now.time() <= time(16, 0)

    d = IntervalDriver(
        tick, interval_seconds=0.02, market_hours_gate=_gate, clock=fixed_clock
    )
    d.start()
    await asyncio.sleep(0.1)
    await d.stop()
    assert hits == []
    assert d.tick_count == 0
    assert d.skipped_count >= 3


async def test_market_hours_gate_allows_inside_window() -> None:
    hits, tick = await _make_tick()
    fixed_clock = lambda: datetime(2026, 4, 24, 10, 0, 0)  # noqa: E731

    def _gate(now: datetime) -> bool:
        return time(9, 30) <= now.time() <= time(16, 0)

    d = IntervalDriver(
        tick, interval_seconds=0.02, market_hours_gate=_gate, clock=fixed_clock
    )
    d.start()
    await asyncio.sleep(0.1)
    await d.stop()
    assert len(hits) >= 3


async def test_cron_driver_fires_with_injected_clock() -> None:
    hits, tick = await _make_tick()

    # Advancing clock: each call returns start + n * 10ms
    start = datetime(2026, 4, 24, 10, 0, 0)
    step_ms = 10
    counter = {"n": 0}

    def _clock() -> datetime:
        # Read the clock; schedule uses this to compute delay.
        return start + timedelta(milliseconds=step_ms * counter["n"])

    def _next(now: datetime) -> datetime:
        counter["n"] += 1
        # Next fire is "now" per the injected clock = effectively 0 delay.
        return now

    d = CronDriver(tick, _next, clock=_clock)
    d.start()
    await asyncio.sleep(0.1)
    await d.stop()
    assert len(hits) >= 3


async def test_driver_task_cancelled_on_stop_no_leak() -> None:
    """After stop(), the driver's task is done (not pending)."""
    _hits, tick = await _make_tick()
    d = IntervalDriver(tick, interval_seconds=0.02)
    d.start()
    await asyncio.sleep(0.03)
    task_ref = d._task  # type: ignore[attr-defined]
    assert task_ref is not None and not task_ref.done()
    await d.stop()
    assert d._task is None  # type: ignore[attr-defined]
    assert task_ref.done()
    assert task_ref.cancelled() or task_ref.done()


async def test_tick_exception_does_not_kill_driver() -> None:
    """A raising tick must be swallowed so the driver keeps firing."""
    calls: list[int] = []

    async def _bad_tick() -> None:
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("first tick boom")

    d = IntervalDriver(_bad_tick, interval_seconds=0.02)
    d.start()
    await asyncio.sleep(0.1)
    await d.stop()
    assert len(calls) >= 3
