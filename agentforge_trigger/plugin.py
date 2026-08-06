"""Plugin entry-point for agentforge-trigger-plugin.

Exposes the FastAPI router for registration by the AgentForge plugin system.
"""

from __future__ import annotations

from typing import Any

from agentforge_trigger.routes import demo_router, router

__all__ = ["demo_router", "router"]


def register(app: Any) -> None:  # type: ignore[valid-type]
    """Mount both routers onto ``app``.

    Follows the plugin-registration pattern from `agentforge-echo-plugin` /
    `agentforge-workflow-plugin` — the core registry looks up this callable
    and invokes it when the plugin is registered.
    """
    app.include_router(router)
    app.include_router(demo_router)
