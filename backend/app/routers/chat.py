from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from pydantic import BaseModel
from typing import List, Dict
from app.core.config import settings


router = APIRouter()

class ChatRequests(BaseModel):
    messages: List[Dict[str,str]]
    model: str = "settings.LM_DEFAULT_MODEL"
    stream: bool = True


def get_lm_client():
    return AsyncOpenAI(
        base_url=settings.LM_URL,
        api_key = "lm-studio"
        )

async def stream_tokens(request: ChatRequests):
    client= get_lm_client()
    response = await client.chat.completions.create(
        model= request.model,
        messages= request.messages,
        stream = True,
    )

    async for chunk in response:
        content= chunk.choices[0].delta.content

        if content:
            yield f"data: {content}\n\n"

    yield "data: [Done]\n\n" 


@router.post("/chat/completions")
async def chat_completions(request: ChatRequests):
    return StreamingResponse(
        stream_tokens(request),
        media_type="text/event-stream"
    )

