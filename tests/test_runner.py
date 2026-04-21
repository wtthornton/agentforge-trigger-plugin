"""Tests for TriggerRunner."""

from __future__ import annotations

import asyncio

import pytest

from agentforge_trigger.agents.trigger_test_agent.runner import TriggerRunner


def test_run_returns_trigger_ok():
    runner = TriggerRunner()
    result = asyncio.run(runner.run("hello"))
    assert result == "trigger:ok"


def test_run_ignores_extra_kwargs():
    runner = TriggerRunner()
    result = asyncio.run(runner.run("anything", extra="ignored"))
    assert result == "trigger:ok"
