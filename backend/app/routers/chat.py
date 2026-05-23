from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
import time

from app.db import get_db
from app.services.router import get_provider, ChatRequest
from app.core.security import get_current_user
from app.services.convo import conversation, load_history, save_messages
from app.core.metrics import record_metrics

router = APIRouter()

async def stream_tokens(request: ChatRequest, user_id: str, db: AsyncSession):
    conversation_id = await conversation(request, user_id, db)
    history = await load_history(conversation_id, db)
    current = {"role": "user", "content": request.messages[-1].content}
    messages = history + [current]

    client, model = await get_provider(request)
    
    start_time = time.time()
    token_count = 0
    full_response = ""

    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        stream=True,
    )

    async for chunk in response:
        content = chunk.choices[0].delta.content
        if content:
            full_response += content
            token_count += 1
            yield f"data: {content}\n\n"

    elapsed = time.time() - start_time

    await save_messages(conversation_id, request.messages[-1].content, full_response, model, db)
    record_metrics(request.provider, model, elapsed, token_count, messages, full_response, conversation_id)

    yield "data: [DONE]\n\n"


@router.post("/chat/completions")
async def chat_completions(request: ChatRequest, db: AsyncSession = Depends(get_db), user_id=Depends(get_current_user)):
    return StreamingResponse(
        stream_tokens(request, user_id, db),
        media_type="text/event-stream"
    )