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
from app.models.agent_installs import AgentInstall
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


# ── Marketplace: publish + install (versioned direct-shared, ADR-0001) ──


@router.post("/agents/{agent_id}/publish")
async def publish_agent(
    agent_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    """Owner publishes a new version; installers see banner until they upgrade."""
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if str(agent.user_id) != str(user_id):
        raise HTTPException(status_code=403, detail="Unauthorised")
    if not agent.is_public:
        raise HTTPException(status_code=422, detail="only public agents can be published")
    agent.version = int(agent.version) + 1
    await db.commit()
    await db.refresh(agent)
    return agent


@router.post("/agents/{agent_id}/install")
async def install_agent(
    agent_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    """Install or upgrade a public agent: upsert pinned_version to current."""
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if not agent.is_public:
        raise HTTPException(status_code=422, detail="only public agents can be installed")
    # Upsert install row
    existing = await db.execute(
        select(AgentInstall).where(AgentInstall.user_id == user_id, AgentInstall.agent_id == agent_id)
    )
    row = existing.scalar_one_or_none()
    if row is None:
        row = AgentInstall(
            id=uuid.uuid4(), user_id=user_id, agent_id=agent_id, pinned_version=int(agent.version)
        )
        db.add(row)
    else:
        row.pinned_version = int(agent.version)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/agents/{agent_id}/install")
async def uninstall_agent(
    agent_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    result = await db.execute(
        select(AgentInstall).where(AgentInstall.user_id == user_id, AgentInstall.agent_id == agent_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="not installed")
    await db.delete(row)
    await db.commit()
    return {"detail": "uninstalled"}


@router.get("/marketplace/agents")
async def list_marketplace_agents(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user),
    limit: int | None = Query(default=None, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Public agents only — any authed user may browse."""
    query = select(Agent).where(Agent.is_public.is_(True)).order_by(Agent.created_at.desc())
    if limit is not None:
        query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    return {"data": result.scalars().all()}


@router.get("/agents/installs")
async def list_my_installs(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    result = await db.execute(select(AgentInstall).where(AgentInstall.user_id == user_id))
    return {"data": result.scalars().all()}


class SuggestRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=500)
    description: str | None = None


class SuggestResponse(BaseModel):
    name: str
    description: str
    system_prompt: str
    suggested_tools: list[str]
    suggested_model: str | None = None


@router.post("/agents/suggest", response_model=SuggestResponse)
async def suggest_agent(
    body: SuggestRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    """Smart Suggest: draft name/description/system_prompt + tools/model from a goal string.

    Single non-streamed LLM call via the existing provider routing; no DB write.
    Tool names are validated against registry.all_tools() so the form never drifts.
    """
    import json as _json

    from app.services.router import ChatRequest, get_provider

    known_tools = [t.name for t in registry.all_tools()]
    tool_list_hint = ", ".join(known_tools[:20]) if known_tools else "(none registered)"

    meta_prompt = (
        "You are an agent configurator for llm-gateway. Given the user's goal, "
        "draft a JSON object with exactly these keys: "
        '{"name": string (short, <=60 chars), '
        '"description": string (one sentence), '
        '"system_prompt": string (2-4 sentences, imperative instructions for the agent), '
        '"suggested_tools": string[] (subset of available tools), '
        '"suggested_model": string|null}.\n'
        f"Available tools: {tool_list_hint}.\n"
        "Return ONLY valid JSON, no prose, no markdown.\n\n"
        f"Goal: {body.goal}\n"
        + (f"Context: {body.description}\n" if body.description else "")
    )

    # Use the same provider resolution as chat/agent so BYO-key + local/cloud routing applies
    req = ChatRequest(
        messages=[{"role": "user", "content": meta_prompt}],  # type: ignore[arg-type]
        model="auto",
    )
    try:
        provider, model, _role = await get_provider(req, user_id, db)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"no provider available for suggest: {e}")

    # Non-streamed completion
    try:
        text = await provider.complete(
            messages=[{"role": "user", "content": meta_prompt}],
            model=model,
            temperature=0.7,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"suggest generation failed: {e}")

    # Tolerant JSON extraction: find first {...}
    raw = (text or "").strip()
    obj = None
    try:
        obj = _json.loads(raw)
    except Exception:
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                obj = _json.loads(raw[start : end + 1])
            except Exception:
                obj = None
    if not isinstance(obj, dict):
        raise HTTPException(status_code=502, detail="suggest could not produce valid JSON")

    name = str(obj.get("name") or body.goal[:60]).strip()[:128] or body.goal[:60]
    description = str(obj.get("description") or "").strip()[:512]
    system_prompt = str(obj.get("system_prompt") or "").strip()[:4000]
    suggested_tools = obj.get("suggested_tools") or []
    if not isinstance(suggested_tools, list):
        suggested_tools = []
    # Filter to known tools — drift-free
    known_set = set(known_tools)
    suggested_tools = [str(t) for t in suggested_tools if str(t) in known_set][:10]
    suggested_model = obj.get("suggested_model")
    if suggested_model is not None:
        suggested_model = str(suggested_model).strip()[:128] or None

    return SuggestResponse(
        name=name,
        description=description or f"Agent for: {body.goal[:120]}",
        system_prompt=system_prompt or f"You are a helpful assistant focused on: {body.goal}",
        suggested_tools=suggested_tools,
        suggested_model=suggested_model,
    )
