from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional
from app.db import get_db
from app.core.security import get_current_user
from app.services.template import rewrite_prompt
from app.services.comfy import generate_image, get_job_status

router = APIRouter()

class ImageRequest(BaseModel):
    prompt: str
    negative_prompt: Optional[str] = "text, watermark, blurry, low quality"
    template_id: Optional[str] = None
    steps: Optional[int] = 10
    cfg: Optional[float] = 1.2
    aspect_ratio: Optional[str] = "9:16 (Portrait Widescreen)"
    batch_size: Optional[int] = 1
    seed: Optional[int] = None
    rewrite: Optional[bool] = True

@router.post("/images/generate")
async def generate(request: ImageRequest, db: AsyncSession = Depends(get_db), user_id: str = Depends(get_current_user)):
    prompt = request.prompt
    if request.rewrite:
        prompt = await rewrite_prompt(request.prompt, request.template_id, db)
    
    prompt_id = await generate_image(
        prompt=prompt,
        negative_prompt=request.negative_prompt,
        steps=request.steps,
        cfg=request.cfg,
        aspect_ratio=request.aspect_ratio,
        batch_size=request.batch_size,
        seed=request.seed
    )
    return {"prompt_id": prompt_id, "rewritten_prompt": prompt}

@router.get("/images/status/{prompt_id}")
async def job_status(prompt_id: str, user_id: str = Depends(get_current_user)):
    return await get_job_status(prompt_id)