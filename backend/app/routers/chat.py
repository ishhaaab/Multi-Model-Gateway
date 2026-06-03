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

from app.models.presets import Preset


router = APIRouter()

logger = logging.getLogger(__name__)

async def load_preset(preset_id, user_id, db: AsyncSession):
    if not preset_id:
        return None
    result = await db.execute(
        select(Preset).where(Preset.id == preset_id, Preset.user_id == user_id)
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
    start_time = time.time()
    token_count = 0
    full_response = ""


    extra_params = {}
    if request.provider == Provider.local or request.provider == Provider.auto:
        extra_params = {
            "extra_body": {
                "top_k": preset.top_k if preset else 0.95,
                "min_p": preset.min_p if preset else 0.05,
                "repeat_penalty": preset.repeat_penalty if preset and preset.repeat_penalty and preset.repeat_penalty > 0 else 1.10
            }
        }

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            stream_options={"include_usage": True},
            temperature=preset.temperature if preset else 0.8,
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

    elapsed = time.time() - start_time

    # Prefer the provider's reported token usage; fall back to the streamed count.
    if usage is not None:
        prompt_tok = usage.prompt_tokens or 0
        completion_tok = usage.completion_tokens or 0
    else:
        prompt_tok = 0
        completion_tok = token_count

    await save_messages(conversation_id, request.messages[-1].content, full_response, model, completion_tok, db)
    record_metrics(request.provider.value, model, elapsed, prompt_tok, completion_tok, messages, full_response, conversation_id)

    yield "data: [DONE]\n\n"


@router.post("/chat/completions")
async def chat_completions(request: ChatRequest, db: AsyncSession = Depends(get_db), user_id=Depends(get_current_user)):
    return StreamingResponse(
        stream_tokens(request, user_id, db),
        media_type="text/event-stream"
    )