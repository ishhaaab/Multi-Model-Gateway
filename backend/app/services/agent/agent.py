"""Agent loop: model to and fro w tool execution, streamed over structured SSE.

Each round calls the model non streamed with the user's allowed tool schemas
(tool-decision rounds are not token streamed; only completed events are pushed). 
Tool calls are executed
through the registry with permissions checked and timeout bounded and the
results are appended as role:"tool" messages before re calling the model.
The loop ends when the model answers without tool calls, the iteration cap
is reached, or the token budget is spent both force a final tool less round.
<insert no bitches megamind gif>

SSE schema is one JSON object per `data:` line. This is richer than the plain
token stream of /chat/completions, so the frontend needs a dedicated parser
for this route:
  {"type":"tool_call",   "id", "name", "arguments"}
  {"type":"tool_result", "id", "name", "content"}
  {"type":"token",       "content"}
  {"type":"error",       "message"}
  {"type":"done",        "conversation_id"}
"""
import asyncio
import json
import logging
import time

from openai import APIError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.metrics import record_metrics
from app.core.background import spawn
from app.core.stream_guard import release_stream_slot
from app.db import AsyncSessionLocal
from app.models.presets import (
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_K,
    DEFAULT_MIN_P,
    DEFAULT_REPEAT_PENALTY,
)
from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.tool_permissions import ToolPermission
from app.services.convo import conversation, load_history, save_messages
from app.services.memory import store_exchange_memories
from app.services.memory_curation import enqueue_curation
from app.services.memory_files import safe_build_memory_context
from app.services.provider_router import ProviderRouter
from app.services.router import ChatRequest
from app.services.tools import registry

logger = logging.getLogger(__name__)

# M2: memory tools that mutate the file store — their paths are captured so the
# background curation pass skips them (it must never clobber an in-turn write).
_MEMORY_WRITE_TOOLS = ("memory_write", "memory_str_replace", "memory_append", "memory_delete")


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _estimate_tokens(messages: list) -> int:
    """Rough token estimate for a message list: 4 tokens of overhead per
    message plus one token per ~4 characters of content. Used to keep the
    agent payload inside the model's context window (R2)."""
    total = 0
    for m in messages:
        content = str(m.get("content") or "")
        total += len(content) // 4 + 4
    return total


_CONTEXT_ERROR_HINTS = (
    "context_length",
    "context window",
    "maximum context",
    "too many tokens",
    "token limit",
    "input is too long",
    "context overflow",
    "prompt is too long",
    "context length",
)


def _is_context_error(e: BaseException) -> bool:
    """True when the provider error reads like the prompt outgrew the model's
    context window, as opposed to a transient network/rate-limit failure."""
    text = str(e).lower()
    return any(hint in text for hint in _CONTEXT_ERROR_HINTS)


def _prune_old_tool_rounds(messages: list, max_tokens: int, drop_all: bool = False) -> list:
    """Drop the oldest tool-call rounds until the estimate fits max_tokens.

    The essential prefix — leading system messages plus the first user
    message — is never touched. A round's tool results die with the assistant
    message that made the calls, so the "tool follows the assistant that
    called it" API invariant holds for whatever survives. Mutates and returns
    the list."""
    essential_end = 0
    for msg in messages:
        if msg.get("role") in ("system", "user"):
            essential_end += 1
            if msg.get("role") == "user":
                break
        else:
            break

    while drop_all or _estimate_tokens(messages) > max_tokens:
        victim = None
        for i in range(essential_end, len(messages)):
            if "tool_calls" in messages[i]:
                victim = i
                break
        if victim is None:
            break
        end = victim + 1
        while end < len(messages) and messages[end].get("role") == "tool":
            end += 1
        del messages[victim:end]
    return messages


async def get_allowed_tools(user_id: str, db: AsyncSession) -> list[registry.Tool]:
    """Per-tenant policy: an explicit grant/deny row wins; otherwise
    first-party tools are allowed and MCP tools are denied."""
    result = await db.execute(
        select(ToolPermission).where(ToolPermission.user_id == user_id)
    )
    overrides = {row.tool_name: row.allowed for row in result.scalars().all()}
    return [t for t in registry.all_tools() if overrides.get(t.name, t.first_party)]


# Code-execution tools gated by the master switch (Q8 C). When
# ENABLE_CODE_EXECUTION is False these are never offered, even if the
# per-user ToolPermission says allowed — the switch is the hard ceiling.
_CODE_TOOLS = frozenset({"bash", "edit_patch", "edit_lines", "write_file"})


async def get_allowed_tools_for_agent(
    agent_id: str | None,
    agent_version: int | None,
    user_id: str,
    db: AsyncSession,
) -> list[registry.Tool]:
    """Per-agent filtered tool list with the full safety ceiling.

    Intersection: agent.allowed_tools ∩ per-user ToolPermission ∩ master switch.
    When agent_id is None, delegates to the legacy global path (backward compat).
    """
    if agent_id is None:
        return await get_allowed_tools(user_id, db)

    # Lazy import to avoid circular deps on startup
    from app.models.agents import Agent

    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise NotFoundError("agent not found")
    # Public agents are readable by anyone authed; private need owner
    if not agent.is_public and str(agent.user_id) != str(user_id):
        raise ForbiddenError("unauthorised")

    # Requested set from the agent row (JSONB list of names)
    requested = set(agent.allowed_tools or [])

    # Per-user ceiling — same query as get_allowed_tools
    perm_result = await db.execute(
        select(ToolPermission).where(ToolPermission.user_id == user_id)
    )
    overrides = {row.tool_name: row.allowed for row in perm_result.scalars().all()}

    def _is_allowed(tool: registry.Tool) -> bool:
        # Must be requested by the agent AND allowed for this user
        if tool.name not in requested:
            return False
        if not overrides.get(tool.name, tool.first_party):
            return False
        # Master switch gates code-execution tools
        if tool.name in _CODE_TOOLS and not settings.ENABLE_CODE_EXECUTION:
            return False
        return True

    return [t for t in registry.all_tools() if _is_allowed(t)]


async def _execute_tool(tool: registry.Tool, raw_args: str, ctx: registry.ToolContext) -> str:
    """Run one tool call. Failures come back as strings so the model can
    see what went wrong and adapt instead of the whole run dying."""
    try:
        args = json.loads(raw_args) if raw_args else {}
    except ValueError:
        return "Error: tool arguments were not valid JSON"
    if not isinstance(args, dict):
        return "Error: tool arguments must be a JSON object"

    try:
        result = await asyncio.wait_for(
            tool.handler(args, ctx), timeout=settings.TOOL_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        return f"Error: tool '{tool.name}' timed out after {settings.TOOL_TIMEOUT_SECONDS}s"
    except Exception as e:
        logger.warning("tool '%s' failed: %r", tool.name, e)
        return f"Error: tool '{tool.name}' failed: {e}"

    if len(result) > settings.TOOL_RESULT_MAX_CHARS:
        result = result[: settings.TOOL_RESULT_MAX_CHARS] + "\n[truncated]"
    return result


async def _resolve_agent(request: ChatRequest, user_id: str, db: AsyncSession):
    """Resolve agent_id/version from the request, or (None, None, None) when not running as an agent."""
    agent_id = getattr(request, "agent_id", None)
    agent_version = getattr(request, "agent_version", None)
    if not agent_id:
        return None, None, None
    from app.models.agents import Agent

    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise NotFoundError("agent not found")
    if not agent.is_public and str(agent.user_id) != str(user_id):
        raise ForbiddenError("unauthorised")
    return agent_id, agent_version, agent


async def _ensure_conversation_agent_binding(conversation_id: str, agent_id: str, agent_version, agent, db: AsyncSession) -> None:
    """Ensure the conversation row is stamped with agent_id/version for scoping."""
    if not agent_id:
        return
    from app.models.conversations import Conversation as ConvRow

    cres = await db.execute(select(ConvRow).where(ConvRow.id == conversation_id))
    crow = cres.scalar_one_or_none()
    if crow is not None and crow.agent_id is None:
        crow.agent_id = agent_id
        crow.agent_version = agent_version if agent_version is not None else agent.version
        await db.commit()


async def run_agent(request: ChatRequest, user_id: str, preset, db: AsyncSession):
    """Thin adapter: resolve history/provider/tools, build AgentRuntimeCtx, stream via runtime.

    No loop logic lives here — all loop/budget/prune/dispatch is inside
    `services.agent.runtime.AgentRuntime`. This function owns DB resolution and
    SSE framing (`_sse`) only, so routers stay thin and tests can inject a fake
    provider without a DB.
    """
    from app.services.agent.runtime import AgentRuntime, AgentRuntimeCtx

    agent_id, agent_version, agent = await _resolve_agent(request, user_id, db)

    conversation_id = None
    # `run_agent` is itself the StreamingResponse generator — it must also own
    # stream_guard release on paths that fail *before* the runtime starts
    # streaming (e.g. resolve_agent 404/403). Runtime owns the in-loop finally,
    # but early errors need a local guard here.
    # We track whether we ever entered the runtime's generator.
    entered_runtime = False
    try:
        conversation_id = await conversation(request, user_id, db)
        await _ensure_conversation_agent_binding(conversation_id, agent_id, agent_version, agent, db)
        user_content = request.messages[-1].content
        history = await load_history(conversation_id, user_content, db)
        messages = history + [{"role": "user", "content": user_content}]
        effective_system_prompt = (agent.system_prompt if agent and agent.system_prompt else None) or (
            preset.system_prompt if preset and preset.system_prompt else None
        )
        if effective_system_prompt:
            messages = [{"role": "system", "content": effective_system_prompt}] + messages

        memory_context = await safe_build_memory_context(db, user_id, agent_id=agent_id)
        if memory_context:
            if effective_system_prompt:
                messages[0]["content"] = effective_system_prompt + "\n\n" + memory_context
            else:
                messages = [{"role": "system", "content": memory_context}] + messages

        tool_ctx = registry.ToolContext(user_id=user_id, conversation_id=conversation_id, db=db)
        tool_ctx.agent_id = agent_id  # type: ignore[attr-defined]
        if agent_id:
            allowed = await get_allowed_tools_for_agent(agent_id, agent_version, user_id, db)
        else:
            allowed = await get_allowed_tools(user_id, db)

        resolved = await ProviderRouter().resolve(request, user_id, db)
        provider, model, _role = resolved.provider, resolved.model, resolved.role
        is_cloud = getattr(provider, "is_cloud", False)
        resolved_provider = "openrouter" if is_cloud else "local"
        extra_sampling = {} if is_cloud else {
            "top_k": preset.top_k if (preset and preset.top_k is not None) else DEFAULT_TOP_K,
            "min_p": preset.min_p if preset else DEFAULT_MIN_P,
            "repeat_penalty": preset.repeat_penalty if preset and preset.repeat_penalty and preset.repeat_penalty > 0 else DEFAULT_REPEAT_PENALTY,
        }

        # R1: release the request's DB connection before streaming; runtime uses
        # its own per-tool sessions and a fresh save session.
        await db.close()

        ctx = AgentRuntimeCtx(
            conversation_id=conversation_id,
            user_id=user_id,
            user_content=user_content,
            messages=messages,
            provider=provider,
            model=model,
            resolved_provider=resolved_provider,
            is_cloud=is_cloud,
            preset=preset,
            agent_id=agent_id,
            agent_version=agent_version,
            agent_version_obj=agent,
            allowed_tools=allowed,
            tool_context=tool_ctx,
            is_private=bool(request.private),
            extra_sampling=extra_sampling,
        )

        runtime = AgentRuntime()
        entered_runtime = True
        async for event in runtime.run(ctx):
            yield _sse(event)

    except AppError as e:
        if not entered_runtime:
            yield _sse({"type": "error", "message": e.detail})
            yield _sse({"type": "done", "conversation_id": conversation_id})
        else:
            raise
    except APIError as e:
        logger.warning("Provider API error before runtime: %s", repr(e))
        if not entered_runtime:
            yield _sse({"type": "error", "message": "upstream model provider error"})
            yield _sse({"type": "done", "conversation_id": conversation_id})
        else:
            raise
    except RuntimeError as e:
        logger.error("Tool setup error before runtime: %s", repr(e))
        if not entered_runtime:
            yield _sse({"type": "error", "message": str(e)})
            yield _sse({"type": "done", "conversation_id": conversation_id})
        else:
            raise
    except Exception as e:
        logger.error("Unexpected error before runtime: %s", repr(e))
        if not entered_runtime:
            yield _sse({"type": "error", "message": "internal server error"})
            yield _sse({"type": "done", "conversation_id": conversation_id})
        else:
            raise
    finally:
        if not entered_runtime:
            try:
                await release_stream_slot(user_id)
            except Exception:
                pass
