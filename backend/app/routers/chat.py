from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from openai import APIError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import time
import logging

from app.db import get_db

from app.core.security import get_current_user
from app.core.metrics import record_metrics

from app.services.convo import conversation, load_history, save_messages, get_last_exchanges, detect_recall_request
from app.services.router import get_provider, ChatRequest, Provider

from app.models.presets import (
    Preset,
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_K,
    DEFAULT_MIN_P,
    DEFAULT_REPEAT_PENALTY,
)


router = APIRouter()

logger = logging.getLogger(__name__)

async def load_preset(preset_id, user_id, db: AsyncSession):
    if preset_id:
        result = await db.execute(
            select(Preset).where(Preset.id == preset_id, Preset.user_id == user_id)
        )
    else:
        # if no preset is chosen, we fall back to the user's "Default" preset that is created at
        # user reg. If preset is missing, we return None and stream_tokens uses
        # the hardcoded safe defaults.
        result = await db.execute(
            select(Preset)
            .where(Preset.user_id == user_id, Preset.name == "Default")
            .order_by(Preset.created_at.asc())
            .limit(1)
        )
    return result.scalar_one_or_none()



async def stream_tokens(request: ChatRequest, user_id: str, db: AsyncSession):
    conversation_id = await conversation(request, user_id, db)
    history = await load_history(conversation_id, request.messages[-1].content, db)
    current = {"role": "user", "content": request.messages[-1].content}
    messages = history + [current]

    preset = await load_preset(request.preset_id, user_id, db)

    system_prefix = []
    if preset and preset.system_prompt:
        system_prefix.append({"role": "system", "content": preset.system_prompt})

    # Positional recall: if the user asked to recall the last N exchanges, fetch them verbatim 
    recall_n = detect_recall_request(request.messages[-1].content)
    if recall_n:
        exchanges = await get_last_exchanges(conversation_id, recall_n, db)
        if exchanges:
            transcript = "\n".join(f"{m['role']}: {m['content']}" for m in exchanges)
            system_prefix.append({
                "role": "system",
                "content": f"The user asked to recall the last {recall_n} exchange(s). "
                           f"Here they are, oldest first:\n{transcript}",
            })

    if system_prefix:
        messages = system_prefix + messages

    client, model = await get_provider(request)
    is_cloud = "openrouter" in str(client.base_url).lower()
    start_time = time.time()
    token_count = 0
    full_response = ""


    if is_cloud:
        # Cloud providers report accurate usage in the final stream chunk.
        extra_params = {"stream_options": {"include_usage": True}}
    else:
        # LM Studio has sampling params via extra_body. We do NOT send
        # stream_options as some LM Studio builds stop streaming token-by-token
        # when it's present (usage then falls back to the streamed-chunk count).
        extra_params = {
            "extra_body": {
                "top_k": preset.top_k if (preset and preset.top_k is not None) else DEFAULT_TOP_K,
                "min_p": preset.min_p if preset else DEFAULT_MIN_P,
                "repeat_penalty": preset.repeat_penalty if preset and preset.repeat_penalty and preset.repeat_penalty > 0 else DEFAULT_REPEAT_PENALTY
            }
        }

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            temperature=preset.temperature if preset else DEFAULT_TEMPERATURE,
            max_tokens=preset.token_limit if preset and preset.token_limit and preset.token_limit > 0 else None,
            stop=preset.stop_strings if preset else None,
            top_p=preset.top_p if preset else None,
            **extra_params
        )
    except APIError as e:
        logger.error("Provider API error: %s", repr(e))
        yield "data: [ERROR] upstream model provider error\n\n"
        yield "data: [DONE]\n\n"
        return
    except Exception as e:
        logger.error("Unexpected error during completion: %s", repr(e))
        yield "data: [ERROR] internal server error\n\n"
        yield "data: [DONE]\n\n"
        return

    usage = None
    stream_error = False
    try:
        async for chunk in response:
            if getattr(chunk, "usage", None):
                usage = chunk.usage          # final usage-only chunk (include_usage)
            if not chunk.choices:
                continue
            content = chunk.choices[0].delta.content
            if content:
                full_response += content
                token_count += 1
                yield f"data: {content}\n\n"
    except Exception as e:
        # provider died mid-generation: keep whatever streamed so far so the
        # exchange isn't lost, and end the stream cleanly instead of crashing
        # without [DONE]
        logger.error("Stream interrupted mid-generation: %s", repr(e))
        stream_error = True

    elapsed = time.time() - start_time

    # Prefer the provider's reported token usage; fall back to the streamed count.
    if usage is not None:
        prompt_tok = usage.prompt_tokens or 0
        completion_tok = usage.completion_tokens or 0
    else:
        prompt_tok = 0
        completion_tok = token_count

    # on a mid-stream failure with nothing generated there is no exchange to save
    if full_response or not stream_error:
        await save_messages(conversation_id, request.messages[-1].content, full_response, model, completion_tok, db)
        record_metrics(request.provider.value, model, elapsed, prompt_tok, completion_tok, messages, full_response, conversation_id)

    if stream_error:
        yield "data: [ERROR] stream interrupted\n\n"
    yield "data: [DONE]\n\n"


@router.post("/chat/completions")
async def chat_completions(request: ChatRequest, db: AsyncSession = Depends(get_db), user_id=Depends(get_current_user)):
    return StreamingResponse(
        stream_tokens(request, user_id, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable proxy buffering (nginx) as Caddy uses flush_interval
        },
    )