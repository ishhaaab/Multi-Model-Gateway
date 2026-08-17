import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.db import get_db
from app.core.security import get_current_user
from app.models.agents import Agent
from app.services.tools import registry

router = APIRouter()


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    preset_id: Optional[UUID] = None
    provider: Optional[str] = Field(default=None, max_length=32)
    model: Optional[str] = Field(default=None, max_length=128)
    allowed_tools: Optional[list[str]] = None
    max_iterations: Optional[int] = Field(default=6, ge=1, le=20)
    token_budget: Optional[int] = Field(default=24000, ge=1000, le=200000)
    is_public: Optional[bool] = False


class AgentUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    preset_id: Optional[UUID] = None
    provider: Optional[str] = Field(default=None, max_length=32)
    model: Optional[str] = Field(default=None, max_length=128)
    allowed_tools: Optional[list[str]] = None
    max_iterations: Optional[int] = Field(default=None, ge=1, le=20)
    token_budget: Optional[int] = Field(default=None, ge=1000, le=200000)
    is_public: Optional[bool] = None


def _validate_allowed_tools(tools: list[str] | None) -> list[str]:
    if tools is None:
        return []
    known = {t.name for t in registry.all_tools()}
    # Also allow any string that looks like a tool name — future tools from
    # not-yet-registered MCP servers are kept but filtered at execution time
    # via get_allowed_tools_for_agent. Here we 422 only on clearly invalid
    # characters to catch typos early without being overly strict.
    for name in tools:
        if not name or len(name) > 128:
            raise HTTPException(status_code=422, detail=f"invalid tool name: {name!r}")
    # Strict 422 for unknown names gives immediate feedback in the form
    unknown = [n for n in tools if n not in known]
    if unknown:
        raise HTTPException(status_code=422, detail=f"unknown tools: {', '.join(unknown)}")
    return tools


@router.post("/agents", status_code=201)
async def create_agent(
    body: AgentCreate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    allowed = _validate_allowed_tools(body.allowed_tools)
    agent = Agent(
        id=uuid.uuid4(),
        user_id=user_id,
        name=body.name,
        description=body.description,
        system_prompt=body.system_prompt,
        preset_id=body.preset_id,
        provider=body.provider,
        model=body.model,
        allowed_tools=allowed,
        max_iterations=body.max_iterations if body.max_iterations is not None else 6,
        token_budget=body.token_budget if body.token_budget is not None else 24000,
        is_public=bool(body.is_public),
        version=1,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return agent


@router.get("/agents")
async def list_agents(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user),
    limit: int | None = Query(default=None, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    query = select(Agent).where(Agent.user_id == user_id).order_by(Agent.created_at.desc())
    if limit is not None:
        query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    return {"data": result.scalars().all()}


@router.get("/agents/{agent_id}")
async def get_agent(
    agent_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    # Private agents are owner-only; public agents are readable by anyone authed
    if not agent.is_public and str(agent.user_id) != str(user_id):
        raise HTTPException(status_code=403, detail="Unauthorised")
    return agent


@router.patch("/agents/{agent_id}")
async def update_agent(
    agent_id: UUID,
    body: AgentUpdate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if str(agent.user_id) != str(user_id):
        raise HTTPException(status_code=403, detail="Unauthorised")
    data = body.model_dump(exclude_unset=True)
    if "allowed_tools" in data:
        data["allowed_tools"] = _validate_allowed_tools(data["allowed_tools"])
    for key, value in data.items():
        setattr(agent, key, value)
    await db.commit()
    await db.refresh(agent)
    return agent


@router.delete("/agents/{agent_id}")
async def delete_agent(
    agent_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if str(agent.user_id) != str(user_id):
        raise HTTPException(status_code=403, detail="Unauthorised")
    await db.delete(agent)
    await db.commit()
    return {"detail": "Agent deleted"}
