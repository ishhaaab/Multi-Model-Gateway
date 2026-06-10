from fastapi import APIRouter, HTTPException, Depends
from openai import AsyncOpenAI
import httpx
from app.core.config import settings, OPENROUTER_API_KEY
from app.core.security import get_current_user
from app.services.router import get_local_client


router = APIRouter()

@router.get("/models")
async def list_local_models(user_id: str = Depends(get_current_user)):
    client = get_local_client()
    try:
        result = await client.models.list()
    except Exception:
        raise HTTPException(status_code=502, detail="LM Studio unavailable")
    return {"data": [{"id": m.id, "object": "model"} for m in (result.data or [])]}



@router.get("/openrouter/models")
async def list_openrouter_models(user_id: str = Depends(get_current_user)):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"}
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