from fastapi import APIRouter
from openai import AsyncOpenAI
from app.core.config import settings
from app.services.router import get_lm_client, get_provider


router = APIRouter()

@router.get("/models")
async def list_lm_models():
    client = get_lm_client()
    result = await client.models.list()
    return {"data": [{"id": m.id, "object": "model"} for m in result.data]}

@router.get("/openrouter/models")
async def list_openrouter_models():
    client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.OPENROUTER_API_KEY
    )
    result = await client.models.list()
    return {"data": [{"id": m.id, "object": "model"} for m in result.data]}