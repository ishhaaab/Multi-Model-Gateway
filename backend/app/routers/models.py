from fastapi import APIRouter, HTTPException
from openai import AsyncOpenAI
import httpx
from app.core.config import settings
from app.services.router import get_lm_client


router = APIRouter()

@router.get("/models")
async def list_lm_models():
    client = get_lm_client()
    result = await client.models.list()
    return {"data": [{"id": m.id, "object": "model"} for m in result.data]}


@router.get("/openrouter/models")
async def list_openrouter_models():
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}"}
        )
        if response.status_code != 200:
            raise HTTPException(status_code=502, detail="Failed to fetch OpenRouter models")
        
        data = response.json().get("data", [])
        
        free_models = [
            {
                "id": m["id"],
                "name": m.get("name", m["id"]),
                "context_length": m.get("context_length"),
                "description": m.get("description", ""),
            }
            for m in data
            if ":free" in m["id"] or (
                m.get("pricing", {}).get("prompt") == "0" and
                m.get("pricing", {}).get("completion") == "0"
            )
        ]
        
        return {"data": free_models, "count": len(free_models)}