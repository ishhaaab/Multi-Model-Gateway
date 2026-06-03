from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from app.db import get_db
from app.core.security import get_current_user
from app.core.redis import get_redis
from app.services.template import rewrite_prompt
from app.services.comfy import (
    generate_image,
    get_job_status,
    ASPECT_RATIOS,
    DEFAULT_ASPECT_RATIO,
)

router = APIRouter()

class ImageRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    negative_prompt: Optional[str] = Field(default="text, watermark, blurry, low quality", max_length=4000)
    template_id: Optional[str] = None
    steps: int = Field(default=10, ge=1, le=50)
    cfg: float = Field(default=1.2, ge=0, le=20)
    aspect_ratio: str = Field(default=DEFAULT_ASPECT_RATIO)
    batch_size: int = Field(default=1, ge=1, le=8)
    seed: Optional[int] = Field(default=None, ge=0)
    rewrite: Optional[bool] = True

    @field_validator("aspect_ratio")
    @classmethod
    def _validate_aspect_ratio(cls, v: str) -> str:
        if v not in ASPECT_RATIOS:
            raise ValueError(
                f"Invalid aspect_ratio '{v}'. Must be one of: {', '.join(ASPECT_RATIOS)}"
            )
        return v

@router.post("/images/generate")
async def generate(request: ImageRequest, db: AsyncSession = Depends(get_db), user_id: str = Depends(get_current_user)):
    prompt = request.prompt
    if request.rewrite:
        prompt = await rewrite_prompt(request.prompt, request.template_id, db, user_id)

    prompt_id = await generate_image(
        prompt=prompt,
        negative_prompt=request.negative_prompt,
        steps=request.steps,
        cfg=request.cfg,
        aspect_ratio=request.aspect_ratio,
        batch_size=request.batch_size,
        seed=request.seed
    )

    # remember who owns this job so status lookups can be authorised
    redis = await get_redis()
    await redis.set(f"imgjob:{prompt_id}", str(user_id), ex=3600)

    return {"prompt_id": prompt_id, "rewritten_prompt": prompt}

@router.get("/images/status/{prompt_id}")
async def job_status(prompt_id: str, user_id: str = Depends(get_current_user)):
    redis = await get_redis()
    owner = await redis.get(f"imgjob:{prompt_id}")
    if owner != str(user_id):
        # unknown, expired, or someone else's job
        raise HTTPException(status_code=404, detail="job not found")
    return await get_job_status(prompt_id)


@router.get("/images/aspect-ratios")
async def list_aspect_ratios():
    # Static config (no auth) — the single source of truth for the
    # ResolutionSelector node, shared by every workflow that uses it.
    return {"aspect_ratios": ASPECT_RATIOS, "default": DEFAULT_ASPECT_RATIO}