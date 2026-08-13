from fastapi import APIRouter, Depends, Query

from app.core.config import settings
from app.core.security import get_current_user
from app.services.fit_score import build_hf_cookbook
from app.services.hardware import probe_hardware

router = APIRouter()


@router.get("/hf/models")
async def hf_models(
    search: str = Query(default="", max_length=200),
    limit: int = Query(default=10, ge=1, le=50),
    context_tokens: int = Query(default=None, ge=512, le=262144),
    user_id: str = Depends(get_current_user),
):
    hw = await probe_hardware()
    return await build_hf_cookbook(hw, context_tokens or settings.COOKBOOK_CONTEXT_TOKENS, search, limit)
