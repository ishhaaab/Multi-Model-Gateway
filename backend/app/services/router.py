from app.core.config import settings, get_openrouter_api_key
from pydantic import BaseModel, Field
from typing import List, Optional, Tuple
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from enum import Enum

from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.providers import Provider as ProviderRow
from app.services.provider_registry import (
    ProviderConfigError,
    get_default_provider,
    row_to_provider,
)
from app.services.providers import LLMProvider, OpenAICompatProvider, OpenRouterProvider


class Provider(str, Enum):
    auto = "auto"
    local = "local"
    openrouter = "openrouter"


class ChatMessage(BaseModel):
    role: str
    # bound the message size so an unbounded payload can't OOM the process (issues.md MED-6)
    content: str = Field(max_length=100_000)


class ChatRequest(BaseModel):
    conversation_id: Optional[str] = None
    preset_id: Optional[str] = None
    messages: List[ChatMessage] = Field(min_length=1)
    model: str = "auto"
    stream: bool = True
    provider: Provider = Provider.auto
    private: bool = False
    provider_id: Optional[str] = None  # pin a specific configured provider row; overrides all routing heuristics


def get_local_client():
    return AsyncOpenAI(
        base_url=f"{settings.LM_URL}/v1",
        api_key="LM-STUDIO",
    )


def get_openrouter_client():
    key = get_openrouter_api_key()
    if not key:
        raise RuntimeError("OpenRouter is not configured (no API key)")
    return AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=key,
    )


def resolve_role(request: ChatRequest) -> str:
    """Pure routing heuristic: which role ("local" | "cloud") handles this
    request, exactly mirroring the legacy match/case rules. No DB access, no
    client construction."""
    last_message = request.messages[-1].content.lower()
    code = ["script", "code", "function", "debug", "bug", "python", "c++", "java", "javascript", "typescript"]
    image = ["draw", "image", "picture", "screenshot", "imagine"]

    if request.private:
        return "local"                       # privacy
    if request.provider == Provider.local:
        return "local"                       # explicitly use local
    if request.provider == Provider.openrouter:
        return "cloud"                       # explicitly use openrouter
    if any(k in last_message for k in code):
        return "cloud"                       # for coding tasks we use openrouter model
    if len(request.messages) > 80:
        return "cloud"                       # for long tasks, use openrouter model

    # i have to add comfyui provider for image gen using image list
    return "local"


async def get_provider(request: ChatRequest, user_id: str, db: AsyncSession) -> Tuple[LLMProvider, str, str]:
    """Resolve (provider adapter, model, role) for a chat/agent request.

    A pinned provider_id wins over every heuristic. Otherwise the pure
    routing rules pick the role and the registry supplies that role's default
    row; with no configured rows we fall back to the legacy env-var clients so
    existing deployments keep working untouched.
    """
    if request.provider_id:
        result = await db.execute(select(ProviderRow).where(ProviderRow.id == request.provider_id))
        row = result.scalar_one_or_none()
        if row is None:
            raise NotFoundError(f"provider {request.provider_id} not found")
        if str(row.user_id) != str(user_id):
            raise ForbiddenError("unauthorised")
        if request.model == "auto" and row.default_model is None:
            raise ProviderConfigError(
                f"provider '{row.name}' has no default model configured; "
                "set a default model or pass an explicit model"
            )
        provider = row_to_provider(row)
        model = request.model if request.model != "auto" else row.default_model
        return provider, model, row.role

    role = resolve_role(request)
    row = await get_default_provider(db, user_id, role)
    if row is not None:
        if request.model == "auto" and row.default_model is None:
            raise ProviderConfigError(
                f"provider '{row.name}' has no default model configured; "
                "set a default model or pass an explicit model"
            )
        provider = row_to_provider(row)
        model = request.model if request.model != "auto" else row.default_model
        return provider, model, role

    # legacy env-var fallback: no configured rows for this role
    if role == "local":
        provider = OpenAICompatProvider(
            base_url=settings.LM_URL,
            api_key="LM-STUDIO",
            default_model=settings.LM_CHAT_MODEL or settings.LM_DEFAULT_MODEL,
        )
        model = request.model if request.model != "auto" else provider.default_model
        return provider, model, role

    key = get_openrouter_api_key()
    if not key:
        raise RuntimeError("OpenRouter is not configured (no API key)")
    provider = OpenRouterProvider(api_key=key, default_model=settings.OPENROUTER_DEFAULT_MODEL)
    model = request.model if request.model != "auto" else provider.default_model
    return provider, model, role
