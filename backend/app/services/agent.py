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
from app.models.presets import (
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_K,
    DEFAULT_MIN_P,
    DEFAULT_REPEAT_PENALTY,
)
from app.models.tool_permissions import ToolPermission
from app.services.convo import conversation, load_history, save_messages
from app.services.router import ChatRequest, get_provider
from app.services.tools import registry

logger = logging.getLogger(__name__)


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


async def get_allowed_tools(user_id: str, db: AsyncSession) -> list[registry.Tool]:
    """Per-tenant policy: an explicit grant/deny row wins; otherwise
    first-party tools are allowed and MCP tools are denied."""
    result = await db.execute(
        select(ToolPermission).where(ToolPermission.user_id == user_id)
    )
    overrides = {row.tool_name: row.allowed for row in result.scalars().all()}
    return [t for t in registry.all_tools() if overrides.get(t.name, t.first_party)]


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
    conversation_id = None
    try:
        conversation_id = await conversation(request, user_id, db)
        user_content = request.messages[-1].content
        history = await load_history(conversation_id, user_content, db)
        messages = history + [{"role": "user", "content": user_content}]
        if preset and preset.system_prompt:
            messages = [{"role": "system", "content": preset.system_prompt}] + messages

        ctx = registry.ToolContext(user_id=user_id, conversation_id=conversation_id, db=db)
        allowed = await get_allowed_tools(user_id, db)
        tools_by_name = {t.name: t for t in allowed}
        tool_schemas = [registry.openai_schema(t) for t in allowed]

        client, model = await get_provider(request)
        is_cloud = "openrouter" in str(client.base_url).lower()
        # mirror the chat path: LM Studio takes extra sampling params via extra_body
        extra_params = {} if is_cloud else {
            "extra_body": {
                "top_k": preset.top_k if (preset and preset.top_k is not None) else DEFAULT_TOP_K,
                "min_p": preset.min_p if preset else DEFAULT_MIN_P,
                "repeat_penalty": preset.repeat_penalty if preset and preset.repeat_penalty and preset.repeat_penalty > 0 else DEFAULT_REPEAT_PENALTY,
            }
        }

        start_time = time.time()
        prompt_tok = 0
        completion_tok = 0
        final_answer = ""

        # +1 lap: the last one always runs tool less so a final answer is produced
        for iteration in range(settings.AGENT_MAX_ITERATIONS + 1):
            over_budget = (prompt_tok + completion_tok) > settings.AGENT_TOKEN_BUDGET
            offer_tools = bool(tool_schemas) and not over_budget and iteration < settings.AGENT_MAX_ITERATIONS

            kwargs = dict(
                model=model,
                messages=messages,
                stream=False,
                temperature=preset.temperature if preset else DEFAULT_TEMPERATURE,
                **extra_params,
            )
            if offer_tools:
                kwargs["tools"] = tool_schemas
                kwargs["tool_choice"] = "auto"

            response = await client.chat.completions.create(**kwargs)

            if response.usage:
                prompt_tok += response.usage.prompt_tokens or 0
                completion_tok += response.usage.completion_tokens or 0

            msg = response.choices[0].message
            tool_calls = msg.tool_calls or []
            if not tool_calls or not offer_tools:
                final_answer = msg.content or ""
                break

            messages.append({
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in tool_calls
                ],
            })

            for tc in tool_calls:
                name = tc.function.name
                yield _sse({"type": "tool_call", "id": tc.id, "name": name,
                            "arguments": tc.function.arguments})

                tool = tools_by_name.get(name)
                if tool is None:
                    # not registered, or registered but not permitted for this user
                    result = f"Error: unknown or unauthorised tool '{name}'"
                else:
                    result = await _execute_tool(tool, tc.function.arguments, ctx)

                yield _sse({"type": "tool_result", "id": tc.id, "name": name, "content": result})
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

        if final_answer:
            yield _sse({"type": "token", "content": final_answer})

        elapsed = time.time() - start_time
        await save_messages(conversation_id, user_content, final_answer, model, completion_tok, db)
        record_metrics(request.provider.value, model, elapsed, prompt_tok, completion_tok,
                       messages, final_answer, conversation_id)

        yield _sse({"type": "done", "conversation_id": conversation_id})

    except APIError as e:
        logger.error("Provider API error in agent run: %s", repr(e))
        yield _sse({"type": "error", "message": "upstream model provider error"})
        yield _sse({"type": "done", "conversation_id": conversation_id})
    except AppError as e:
        # raised inside the stream, after headers are sent, so the global
        # handler can't translate it so surface it as an SSE error event
        yield _sse({"type": "error", "message": e.detail})
        yield _sse({"type": "done", "conversation_id": conversation_id})
    except Exception as e:
        logger.error("Unexpected error in agent run: %s", repr(e))
        yield _sse({"type": "error", "message": "internal server error"})
        yield _sse({"type": "done", "conversation_id": conversation_id})
