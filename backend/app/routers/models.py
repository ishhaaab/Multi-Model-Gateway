from fastapi import APIRouter
from openai import AsyncOpenAI
from app.core.config import settings


router = APIRouter()

def get_lm_client():
    return AsyncOpenAI(
        base_url=settings.LM_URL,
        api_key = "lm-studio"
        )

@router.get("/models") # when a GET request is sent to the url /models, execute this list_models() func. 
async def list_models():
    client = get_lm_client()
    models = await client.models.list()
    return models

