"""TriggerRunner — deterministic test runner for the trigger-test agent (TAP-760).

Returns a fixed "trigger:ok" result so the scheduler smoke tests can verify
job submission, state transitions, and cancellation without a real agent.
"""

from __future__ import annotations


class TriggerRunner:
    """Minimal runner that always succeeds with a fixed result."""

    async def run(self, prompt: str, **_kwargs: object) -> str:
        return "trigger:ok"
