# agentforge-trigger-plugin

Test rig for the AgentForge scheduler/trigger system (TAP-760).

Provides a minimal plugin that exercises job submit, cancel, and lifecycle
transitions via `AgentScheduler` without requiring a real agent or LLM call.

## Structure

```
agentforge_trigger/
  __init__.py          # __version__
  plugin.json          # plugin manifest
  plugin.py            # exposes router
  routes.py            # POST /api/trigger-test/submit
                       # GET  /api/trigger-test/jobs
                       # DELETE /api/trigger-test/jobs/{job_id}
                       # GET  /api/trigger-test/status
  agents/
    trigger_test_agent/
      AGENT.md         # agent manifest
      runner.py        # TriggerRunner.run() -> "trigger:ok"
tests/
  test_runner.py       # unit tests for TriggerRunner
```

## Smoke tests (AgentForge backend)

The scheduler smoke tests live in `backend/tests/test_trigger_smoke.py` in
the main AgentForge repo. They test `AgentScheduler` directly with a stub
`LifecycleManager` and do not require this plugin to be installed. The HTTP
route tests are skipped automatically when the package is not installed.

## Installation (dev)

```bash
cd /path/to/agentforge-trigger-plugin
pip install -e .
```

## Running plugin tests

```bash
cd /path/to/agentforge-trigger-plugin
pytest tests/
```
