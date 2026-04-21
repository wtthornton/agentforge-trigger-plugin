"""Plugin entry-point for agentforge-trigger-plugin.

Exposes the FastAPI router for registration by the AgentForge plugin system.
"""

from __future__ import annotations

from agentforge_trigger.routes import router

__all__ = ["router"]
