from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from openai import APIError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import time

from app.db import get_db

from app.core.security import get_current_user
from app.core.metrics import record_metrics

from app.services.convo import conversation, load_history, save_messages
from app.services.router import get_provider, ChatRequest, Provider

from app.models.presets import Preset


router = APIRouter()

async def load_preset(preset_id, db: AsyncSession):
    if not preset_id:
        return None
    result = await db.execute(select(Preset).where(Preset.id == preset_id))
    return result.scalar_one_or_none()



async def stream_tokens(request: ChatRequest, user_id: str, db: AsyncSession):
    conversation_id = await conversation(request, user_id, db)
    history = await load_history(conversation_id, request.messages[-1].content, db)
    current = {"role": "user", "content": request.messages[-1].content}
    messages = history + [current]

    preset = await load_preset(request.preset_id, db)

    if preset and preset.system_prompt:
        messages = [{"role": "system", "content": preset.system_prompt}] + messages

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
            temperature=preset.temperature if preset else 0.8,
            max_tokens=preset.token_limit if preset and preset.token_limit and preset.token_limit > 0 else None,
            stop=preset.stop_strings if preset else None,
            top_p=preset.top_p if preset else None,
            **extra_params
        )
    except APIError as e:
        print("OpenAI API Error:", repr(e))
        yield f"ERROR: {str(e)}"
    
    except Exception as e:
        print("Unexpected Error:", repr(e))
        yield "Internal server error"

    async for chunk in response:
        content = chunk.choices[0].delta.content
        if content:
            full_response += content
            token_count += 1
            yield f"data: {content}\n\n"

    elapsed = time.time() - start_time

    await save_messages(conversation_id, request.messages[-1].content, full_response, model, token_count, db)
    record_metrics(request.provider.value, model, elapsed, token_count, messages, full_response, conversation_id)

    yield "data: [DONE]\n\n"


@router.post("/chat/completions")
async def chat_completions(request: ChatRequest, db: AsyncSession = Depends(get_db), user_id=Depends(get_current_user)):
    return StreamingResponse(
        stream_tokens(request, user_id, db),
        media_type="text/event-stream"
    )