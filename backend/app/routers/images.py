import httpx
import shutil
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from app.db import get_db
from app.core.security import get_current_user
from app.core.redis import get_redis
from app.core.config import settings
from app.models.trainings import TrainingJob
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
    workflow_id: Optional[str] = None
    steps: int = Field(default=10, ge=1, le=50)
    cfg: float = Field(default=1.2, ge=0, le=20)
    aspect_ratio: str = Field(default=DEFAULT_ASPECT_RATIO)
    batch_size: int = Field(default=1, ge=1, le=8)
    seed: Optional[int] = Field(default=None, ge=0)
    rewrite: Optional[bool] = True
    training_id: Optional[str] = None  # use a trained LoRA from a completed training job

    @field_validator("aspect_ratio")
    @classmethod
    def _validate_aspect_ratio(cls, v: str) -> str:
        if v not in ASPECT_RATIOS:
            raise ValueError(
                f"Invalid aspect_ratio '{v}'. Must be one of: {', '.join(ASPECT_RATIOS)}"
            )
        return v

async def _prepare_training_lora(training_id: str, user_id: str, db: AsyncSession) -> str:
    """Copy a completed training artifact into the ComfyUI LoRA folder and
    return the filename ComfyUI loads it by.

    Ownership rules mirror the trainings router (404 for missing/foreign, 409
    when the job isn't done) so a job id can't be probed through this endpoint.
    """
    result = await db.execute(select(TrainingJob).where(TrainingJob.id == training_id))
    job = result.scalar_one_or_none()
    if job is None or str(job.user_id) != str(user_id):
        raise HTTPException(status_code=404, detail="training job not found")

    if job.status != "complete" or not job.artifact_filename:
        raise HTTPException(status_code=409, detail="training not complete")

    # guard against traversal: the artifact must live inside the job's dir
    job_dir = (Path(settings.TRAINING_ROOT) / str(job.id)).resolve()
    src = (job_dir / job.artifact_filename).resolve()
    if not src.is_relative_to(job_dir) or not src.is_file():
        raise HTTPException(status_code=404, detail="training artifact not found")

    # COMFY_LORA_DIR is the HOST folder (used by docker-compose as the bind
    # source) — an empty value means the mount isn't configured at all.
    if not settings.COMFY_LORA_DIR:
        raise HTTPException(
            status_code=400,
            detail="COMFY_LORA_DIR is not configured; set it to your ComfyUI models/loras folder",
        )

    dest_name = f"lora_{job.id}.safetensors"
    # COMFY_LORA_CONTAINER_PATH is where the backend writes inside the container
    # (matches the compose mount target); on host-side runs it equals the host dir.
    dest_dir = Path(settings.COMFY_LORA_CONTAINER_PATH)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / dest_name
    if not dest_path.exists():
        shutil.copy2(src, dest_path)
    return dest_name


@router.post("/images/generate")
async def generate(request: ImageRequest, db: AsyncSession = Depends(get_db), user_id: str = Depends(get_current_user)):
    prompt = request.prompt
    if request.rewrite:
        prompt = await rewrite_prompt(request.prompt, request.template_id, db, user_id)

    lora_name = None
    if request.training_id:
        lora_name = await _prepare_training_lora(request.training_id, user_id, db)

    prompt_id = await generate_image(
        request.workflow_id,
        user_id,
        db,
        prompt=prompt,
        negative_prompt=request.negative_prompt,
        steps=request.steps,
        cfg=request.cfg,
        aspect_ratio=request.aspect_ratio,
        batch_size=request.batch_size,
        seed=request.seed,
        lora_name=lora_name,
    )

    # remember who owns this job so status lookups can be authorised
    redis = await get_redis()
    await redis.set(f"imgjob:{prompt_id}", str(user_id), ex=3600)

    payload = {"prompt_id": prompt_id, "rewritten_prompt": prompt}
    if lora_name:
        payload["lora"] = lora_name
    return payload

@router.get("/images/status/{prompt_id}")
async def job_status(prompt_id: str, user_id: str = Depends(get_current_user)):
    redis = await get_redis()
    owner = await redis.get(f"imgjob:{prompt_id}")
    if owner != str(user_id):
        # unknown, expired, or someone else's job
        raise HTTPException(status_code=404, detail="job not found")
    try:
        return await get_job_status(prompt_id)
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="ComfyUI unavailable")


@router.get("/images/aspect-ratios")
async def list_aspect_ratios():
    # Static config & the single source of truth for the
    # ResolutionSelector node, shared by every workflow that uses it.
    return {"aspect_ratios": ASPECT_RATIOS, "default": DEFAULT_ASPECT_RATIO}