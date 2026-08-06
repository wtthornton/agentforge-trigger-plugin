"""Interval / cron trigger drivers for the trigger-test rig (TAP-760).

A driver holds one `asyncio.Task` that fires a user-supplied coroutine on a
schedule. Two flavours are supported:

- :class:`IntervalDriver` — sleeps ``interval_seconds`` between ticks.
- :class:`CronDriver` — asks a ``clock`` + a ``next_fire`` callback for the
  next scheduled datetime, waits until then, ticks. Both flavours honour an
  optional ``market_hours_gate`` callable that returns ``False`` to skip a
  fire without cancelling the schedule.

Neither driver is clever about drift or catch-up — this is a test rig; the
point is to prove the shape (start / stop / no leak), not to replace APScheduler.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime

logger = logging.getLogger(__name__)

Tick = Callable[[], Awaitable[None]]
Clock = Callable[[], datetime]
MarketHoursGate = Callable[[datetime], bool]
NextFire = Callable[[datetime], datetime]


class _BaseDriver:
    """Common start / stop plumbing shared by interval + cron drivers."""

    def __init__(
        self,
        tick: Tick,
        *,
        market_hours_gate: MarketHoursGate | None = None,
        clock: Clock = datetime.now,
    ) -> None:
        self._tick = tick
        self._gate = market_hours_gate
        self._clock = clock
        self._task: asyncio.Task[None] | None = None
        self._tick_count = 0
        self._skipped_count = 0

    @property
    def tick_count(self) -> int:
        return self._tick_count

    @property
    def skipped_count(self) -> int:
        return self._skipped_count

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def _fire_once(self) -> None:
        """Run the tick if market-hours allows, else bump ``skipped_count``."""
        if self._gate is not None and not self._gate(self._clock()):
            self._skipped_count += 1
            return
        self._tick_count += 1
        try:
            await self._tick()
        except Exception:  # noqa: BLE001 — tick errors must not kill the driver
            logger.warning("trigger tick raised", exc_info=True)

    def start(self) -> None:
        if self.running:
            return
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _loop(self) -> None:
        raise NotImplementedError


class IntervalDriver(_BaseDriver):
    """Fire ``tick`` every ``interval_seconds`` wall-clock seconds."""

    def __init__(
        self,
        tick: Tick,
        interval_seconds: float,
        *,
        market_hours_gate: MarketHoursGate | None = None,
        clock: Clock = datetime.now,
    ) -> None:
        super().__init__(tick, market_hours_gate=market_hours_gate, clock=clock)
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be > 0")
        self._interval = interval_seconds

    async def _loop(self) -> None:
        while True:
            await self._fire_once()
            await asyncio.sleep(self._interval)


class CronDriver(_BaseDriver):
    """Fire ``tick`` at each ``next_fire(now)`` datetime returned by the callback.

    Uses ``asyncio.sleep`` for the wait. Tests can inject a fake ``clock`` +
    ``next_fire`` to drive the scheduler in < 1ms of wall-clock.
    """

    def __init__(
        self,
        tick: Tick,
        next_fire: NextFire,
        *,
        market_hours_gate: MarketHoursGate | None = None,
        clock: Clock = datetime.now,
    ) -> None:
        super().__init__(tick, market_hours_gate=market_hours_gate, clock=clock)
        self._next_fire = next_fire

    async def _loop(self) -> None:
        while True:
            now = self._clock()
            target = self._next_fire(now)
            delay = max(0.0, (target - now).total_seconds())
            await asyncio.sleep(delay)
            await self._fire_once()
