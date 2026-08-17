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
from app.services.router import ChatRequest, get_provider
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


async def run_agent(request: ChatRequest, user_id: str, preset, db: AsyncSession):
    # Resolve agent override if the client is running as an agent (ADR-0004).
    # When agent_id is set, the agent's system_prompt and filtered allowed_tools win;
    # otherwise the legacy global-agent path is unchanged (backward compat).
    agent_id = getattr(request, "agent_id", None)
    agent_version = getattr(request, "agent_version", None)
    agent = None
    if agent_id:
        # Lazy import to avoid cycle
        from app.models.agents import Agent

        result = await db.execute(select(Agent).where(Agent.id == agent_id))
        agent = result.scalar_one_or_none()
        if agent is None:
            raise NotFoundError("agent not found")
        if not agent.is_public and str(agent.user_id) != str(user_id):
            raise ForbiddenError("unauthorised")
        # Agent's own max_iterations/token_budget override the global settings
        # only for this run — preset fallback stays for non-agent chats.

    conversation_id = None
    try:
        # Persist agent binding on the conversation so history + memory scoping
        # can be per-agent (stores the resolved version, not just the id).
        if agent_id and request.conversation_id is None:
            # New conversation — inject agent binding into the convo creation
            # so conversation() sees it. We stash it on the request for the
            # convo helper which reads request.agent_id (set above).
            pass
        conversation_id = await conversation(request, user_id, db)
        # If this is an existing conversation being continued as an agent chat,
        # ensure the conversation's agent_id is set/updated for scoping.
        if agent_id:
            from app.models.conversations import Conversation as ConvRow

            cres = await db.execute(select(ConvRow).where(ConvRow.id == conversation_id))
            crow = cres.scalar_one_or_none()
            if crow is not None and crow.agent_id is None:
                crow.agent_id = agent_id
                crow.agent_version = agent_version if agent_version is not None else agent.version
                await db.commit()
        user_content = request.messages[-1].content
        history = await load_history(conversation_id, user_content, db)
        messages = history + [{"role": "user", "content": user_content}]
        # Agent system_prompt wins over preset when running as an agent
        effective_system_prompt = (agent.system_prompt if agent and agent.system_prompt else None) or (
            preset.system_prompt if preset and preset.system_prompt else None
        )
        if effective_system_prompt:
            messages = [{"role": "system", "content": effective_system_prompt}] + messages

        # Memory-file index injection (Tier 1 index + Tier 1.5 full files) —
        # built BEFORE the connection is released below; best-effort, a memory
        # failure must never fail the request.
        memory_context = await safe_build_memory_context(db, user_id)
        if memory_context:
            if effective_system_prompt:
                messages[0]["content"] = effective_system_prompt + "\n\n" + memory_context
            else:
                messages = [{"role": "system", "content": memory_context}] + messages

        ctx = registry.ToolContext(user_id=user_id, conversation_id=conversation_id, db=db)
        # Extend context with agent binding for workspace/file tools
        ctx.agent_id = agent_id  # type: ignore[attr-defined]
        if agent_id:
            allowed = await get_allowed_tools_for_agent(agent_id, agent_version, user_id, db)
        else:
            allowed = await get_allowed_tools(user_id, db)
        tools_by_name = {t.name: t for t in allowed}
        tool_schemas = [registry.openai_schema(t) for t in allowed]

        provider, model, role = await get_provider(request, user_id, db)
        is_cloud = provider.is_cloud
        resolved_provider = "openrouter" if is_cloud else "local"  # CR-6: resolved, not "auto"
        # mirror the chat path: LM Studio takes extra sampling params via extra_body
        extra_sampling = {} if is_cloud else {
            "top_k": preset.top_k if (preset and preset.top_k is not None) else DEFAULT_TOP_K,
            "min_p": preset.min_p if preset else DEFAULT_MIN_P,
            "repeat_penalty": preset.repeat_penalty if preset and preset.repeat_penalty and preset.repeat_penalty > 0 else DEFAULT_REPEAT_PENALTY,
        }

        # Release the DB connection back to the pool BEFORE the multi-round loop —
        # every read is done, and holding an idle connection across the whole run
        # is what exhausts the pool under concurrency (roadmap R1). Tools and the
        # final save use their own short-lived sessions; get_db's own close()
        # afterwards is then a no-op.
        await db.close()

        start_time = time.time()
        prompt_tok = 0
        completion_tok = 0
        final_answer = ""
        truncated = False
        # memory-file paths the agent wrote this turn (M2) — the curation pass
        # skips them so it can't clobber an in-turn memory write
        written_paths: list[str] = []

        # +1 lap: the last one always runs tool less so a final answer is produced
        for iteration in range(settings.AGENT_MAX_ITERATIONS + 1):
            over_budget = (prompt_tok + completion_tok) > settings.AGENT_TOKEN_BUDGET
            offer_tools = bool(tool_schemas) and not over_budget and iteration < settings.AGENT_MAX_ITERATIONS

            if offer_tools:
                # keep the payload inside the model's context window: drop the
                # oldest tool rounds before the call (R2)
                _prune_old_tool_rounds(messages, int(0.6 * settings.AGENT_TOKEN_BUDGET))
                try:
                    resp = await provider.chat_with_tools(
                        messages=messages,
                        model=model,
                        temperature=preset.temperature if preset else DEFAULT_TEMPERATURE,
                        tools=tool_schemas,
                        tool_choice="auto",
                        max_tokens=None,
                        extra_sampling=extra_sampling if not is_cloud else None,
                    )
                except APIError as e:
                    if not _is_context_error(e):
                        raise
                    # the provider rejects the prompt as too long: drop every
                    # tool round and synthesize from the essential prefix alone
                    logger.warning(
                        "context overflow mid-loop; degrading to tool-less final round: %s",
                        repr(e),
                    )
                    truncated = True
                    _prune_old_tool_rounds(messages, settings.AGENT_TOKEN_BUDGET, drop_all=True)
                    final_answer = await provider.complete(
                        messages=messages,
                        model=model,
                        temperature=preset.temperature if preset else DEFAULT_TEMPERATURE,
                        max_tokens=None,
                    )
                    break
                if resp.prompt_tokens is not None:
                    prompt_tok += resp.prompt_tokens
                    completion_tok += resp.completion_tokens or 0
                tool_calls = resp.tool_calls or []
                if not tool_calls:
                    final_answer = resp.content or ""
                    break
            else:
                _prune_old_tool_rounds(messages, settings.AGENT_TOKEN_BUDGET)
                final_answer = await provider.complete(
                    messages=messages,
                    model=model,
                    temperature=preset.temperature if preset else DEFAULT_TEMPERATURE,
                    max_tokens=None,
                )
                # tools were withheld due to the iteration cap / token budget (not because
                # the model finished) → the answer may be incomplete (issues.md CR-8)
                truncated = bool(tool_schemas) and not offer_tools
                break

            messages.append({
                "role": "assistant",
                "content": resp.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": tc.arguments},
                    }
                    for tc in tool_calls
                ],
            })

            for tc in tool_calls:
                name = tc.name
                yield _sse({"type": "tool_call", "id": tc.id, "name": name,
                            "arguments": tc.arguments})

                if name in _MEMORY_WRITE_TOOLS:
                    # best-effort: parse the args for the path the agent is
                    # writing; a malformed payload just means no capture
                    try:
                        targs = json.loads(tc.arguments or "{}")
                    except ValueError:
                        targs = {}
                    if isinstance(targs, dict) and targs.get("path"):
                        written_paths.append(str(targs["path"]))

                tool = tools_by_name.get(name)
                if tool is None:
                    # not registered, or registered but not permitted for this user
                    result = f"Error: unknown or unauthorised tool '{name}'"
                else:
                    # the request session was released before the loop (R1); each
                    # tool gets a short-lived session for its own DB work
                    async with AsyncSessionLocal() as tool_db:
                        ctx.db = tool_db
                        result = await _execute_tool(tool, tc.arguments, ctx)

                yield _sse({"type": "tool_result", "id": tc.id, "name": name, "content": result})
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

        if final_answer:
            yield _sse({"type": "token", "content": final_answer})

        elapsed = time.time() - start_time
        # prompt_tok accumulates only when a resp reported usage (provider
        # exact); a local run without usage stays 0 → cumulative chunk counts
        provenance = "exact" if prompt_tok > 0 else "chunk_count"
        # fresh short-lived session — the request's own connection was released above (R1)
        async with AsyncSessionLocal() as save_db:
            await save_messages(conversation_id, user_content, final_answer, model, prompt_tok, completion_tok, save_db, token_provenance=provenance)
        # off the response path: embeddings + tracing (metadata-only for private chats)
        spawn(store_exchange_memories(conversation_id, user_content, final_answer))
        spawn(asyncio.to_thread(
            record_metrics, resolved_provider, model, elapsed, prompt_tok, completion_tok,
            messages, final_answer, conversation_id, not request.private,
        ))
        # M2: background memory curation — off-path, best-effort; private chats
        # are excluded inside enqueue_curation; paths the agent wrote this turn
        # are passed along so the pass skips them.
        spawn(enqueue_curation(str(user_id), str(conversation_id), written_paths,
                               private=request.private))

        done_evt: dict = {"type": "done", "conversation_id": conversation_id, "truncated": truncated}
        if agent_id:
            done_evt["agent_id"] = agent_id
            done_evt["agent_version"] = agent_version if agent_version is not None else (agent.version if agent else None)
        yield _sse(done_evt)

    except APIError as e:
        logger.error("Provider API error in agent run: %s", repr(e))
        yield _sse({"type": "error", "message": "upstream model provider error"})
        yield _sse({"type": "done", "conversation_id": conversation_id})
    except AppError as e:
        # raised inside the stream, after headers are sent, so the global
        # handler can't translate it so surface it as an SSE error event
        yield _sse({"type": "error", "message": e.detail})
        yield _sse({"type": "done", "conversation_id": conversation_id})
    except RuntimeError as e:
        # e.g. chat_with_tools on a provider that doesn't support tool calling
        # yet (Anthropic/Google) — surface the real message, not a generic 500
        logger.error("Tool-calling error in agent run: %s", repr(e))
        yield _sse({"type": "error", "message": str(e)})
        yield _sse({"type": "done", "conversation_id": conversation_id})
    except Exception as e:
        logger.error("Unexpected error in agent run: %s", repr(e))
        yield _sse({"type": "error", "message": "internal server error"})
        yield _sse({"type": "done", "conversation_id": conversation_id})
    finally:
        # release the stream slot on every exit path — normal completion,
        # handled errors, unhandled errors, and client disconnect
        await release_stream_slot(user_id)
