from fastapi import APIRouter
from openai import AsyncOpenAI
from app.core.config import settings
from app.services.router import get_lm_client, get_provider


router = APIRouter()

@router.get("/models") # when a GET request is sent to the url /models, execute this list_models() func. 
async def list_local_models():
    client = get_lm_client()
    models = await client.models.list()
    return models

@router.get("/openrouter/models") # when a GET request is sent to the url /models, execute this list_models() func. 
async def list_models():
    client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=settings.OPENROUTER_API_KEY
)
    models = await client.models.list()
    return models