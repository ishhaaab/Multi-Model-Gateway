"""Agent package — re-exports the public surface so `from app.services.agent import run_agent` keeps working."""

from app.services.agent.runtime import AgentRuntime, AgentRuntimeCtx  # noqa: F401

# Legacy run_agent lives in agent.py (sibling file) — import it lazily to avoid cycle on package import.
# `from app.services.agent import run_agent` resolves via this package's attribute fallback.
from importlib import import_module as _import_module


def __getattr__(name: str):  # PEP 562
    if name == "run_agent":
        return _import_module("app.services.agent.agent").run_agent
    if name in ("get_allowed_tools", "get_allowed_tools_for_agent", "_resolve_agent", "_ensure_conversation_agent_binding"):
        return getattr(_import_module("app.services.agent.agent"), name)
    raise AttributeError(name)
