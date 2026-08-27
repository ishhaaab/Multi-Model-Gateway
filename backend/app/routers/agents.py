import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.core.config import settings
from app.db import get_db
from app.core.security import get_current_user
from app.models.agents import Agent
from app.models.agent_installs import AgentInstall
from app.services.tools import registry

logger = logging.getLogger(__name__)

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
    for name in tools:
        if not name or len(name) > 128:
            raise HTTPException(status_code=422, detail=f"invalid tool name: {name!r}")
    unknown = [n for n in tools if n not in known]
    if unknown:
        raise HTTPException(status_code=422, detail=f"unknown tools: {', '.join(unknown)}")
    return tools


async def _load_agent(db: AsyncSession, agent_id: UUID) -> Agent | None:
    """Fetch an agent row without any ownership check; None when it doesn't exist."""
    result = await db.execute(select(Agent).where(Agent.id == agent_id))
    return result.scalar_one_or_none()


async def _get_owned_agent(db: AsyncSession, agent_id: UUID, user_id: str) -> Agent:
    """Owner-only lookup for mutation routes (update/delete/publish).

    404 when the agent doesn't exist; 403 when it belongs to someone else. This
    is the repo's 404-vs-403 ownership convention — the workspace routes use
    `_get_workspace_agent` instead, which also allows installers/public agents.
    """
    agent = await _load_agent(db, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if str(agent.user_id) != str(user_id):
        raise HTTPException(status_code=403, detail="Unauthorised")
    return agent


async def _get_workspace_agent(db: AsyncSession, agent_id: UUID, user_id: str) -> Agent:
    """Lookup for workspace routes: owner, an installer, or a public agent.

    404 when the agent doesn't exist; 403 when the user is neither the owner nor
    an installer and the agent is not public. The installer-eligibility check
    mirrors `_resolve_agent` in services/agent/agent.py.
    """
    agent = await _load_agent(db, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if str(agent.user_id) != str(user_id):
        inst = await db.execute(
            select(AgentInstall).where(AgentInstall.user_id == user_id, AgentInstall.agent_id == agent_id)
        )
        if inst.scalar_one_or_none() is None and not agent.is_public:
            raise HTTPException(status_code=403, detail="Unauthorised")
    return agent


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


# ── Static routes must come before /agents/{agent_id} to avoid shadowing ──


@router.get("/agents/installs")
async def list_my_installs(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    result = await db.execute(select(AgentInstall).where(AgentInstall.user_id == user_id))
    return {"data": result.scalars().all()}


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


class SuggestRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=500)
    description: str | None = None


class SuggestResponse(BaseModel):
    name: str
    description: str
    system_prompt: str
    suggested_tools: list[str]
    suggested_model: str | None = None


# ── Suggest helpers (module-level so suggest_agent stays a thin orchestrator) ──

def _looks_like_auth_error(msg: str) -> bool:
    low = (msg or "").lower()
    return (
        "user not found" in low
        or "invalid api key" in low
        or "authentication" in low
        or ("401" in low and "unauthorized" in low)
    )


def _parse_suggest_json(raw: str) -> dict | None:
    """Best-effort JSON parse of the model's raw output (may be wrapped in prose)."""
    import json as _json

    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        obj = _json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except Exception:  # noqa: BLE001
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            obj = _json.loads(raw[start : end + 1])
            if isinstance(obj, dict):
                return obj
        except Exception:  # noqa: BLE001
            return None
    return None


def _build_suggest_response(obj: dict, goal: str, known_tools: list[str]) -> SuggestResponse:
    name = str(obj.get("name") or goal[:60]).strip()[:128] or goal[:60]
    description = str(obj.get("description") or "").strip()[:512]
    system_prompt = str(obj.get("system_prompt") or "").strip()[:4000]
    suggested_tools = obj.get("suggested_tools") or []
    if not isinstance(suggested_tools, list):
        suggested_tools = []
    known_set = set(known_tools)
    suggested_tools = [str(t) for t in suggested_tools if str(t) in known_set][:10]
    suggested_model = obj.get("suggested_model")
    if suggested_model is not None:
        suggested_model = str(suggested_model).strip()[:128] or None
    return SuggestResponse(
        name=name,
        description=description or f"Agent for: {goal[:120]}",
        system_prompt=system_prompt or f"You are a helpful assistant focused on: {goal}",
        suggested_tools=suggested_tools,
        suggested_model=suggested_model,
    )


def _cloud_candidates() -> list[str]:
    """Ordered cloud model candidates: explicit SUGGEST_CLOUD_MODEL, then free fallbacks."""
    out: list[str] = []
    if settings.SUGGEST_CLOUD_MODEL.strip():
        out.append(settings.SUGGEST_CLOUD_MODEL.strip())
    out.extend(m.strip() for m in settings.SUGGEST_CLOUD_FALLBACK_MODELS.split(",") if m.strip())
    return out


async def _suggest_cloud(
    messages: list[dict],
    user_id: str,
    db: AsyncSession,
    known_tools: list[str],
    goal: str,
) -> tuple[SuggestResponse | None, str | None]:
    """Try OpenRouter with ordered :free candidates. Returns (response, error).

    `response` is non-None on success; otherwise `error` captures the last
    failure so the caller can fall back to local and surface a useful hint.
    """
    from app.services.provider_router import ProviderRouter
    from app.services.router import ChatRequest, Provider

    try:
        req = ChatRequest(messages=messages, model="auto", provider=Provider.openrouter)  # type: ignore[arg-type]
        resolved = await ProviderRouter().resolve(req, user_id, db)
    except Exception as e:  # noqa: BLE001 — no cloud configured is expected
        msg = str(e)
        logger.warning("suggest cloud unavailable: %s — falling back to local", msg)
        return None, msg

    # Prefer a :free model even if the user's default is a paid one.
    candidates: list[str] = []
    if resolved.model and resolved.model.strip().endswith(":free"):
        candidates.append(resolved.model.strip())
    seen = set(candidates)
    for m in _cloud_candidates():
        if m not in seen:
            candidates.append(m)
            seen.add(m)

    last_error: str | None = None
    for cand in candidates:
        try:
            text = await resolved.provider.complete(messages=messages, model=cand, temperature=0.7)
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            last_error = msg
            logger.warning("suggest cloud failed on %s: %s", cand, msg)
            continue
        obj = _parse_suggest_json(text)
        if obj is not None:
            logger.info("suggest served from cloud %s", cand)
            return _build_suggest_response(obj, goal, known_tools), None
        logger.warning("suggest cloud %s returned non-JSON, trying next candidate", cand)
        last_error = f"cloud {cand} returned non-JSON"

    logger.warning("suggest cloud exhausted: %s — falling back to local", last_error)
    return None, last_error


async def _suggest_local(
    messages: list[dict],
    user_id: str,
    db: AsyncSession,
    known_tools: list[str],
    goal: str,
) -> SuggestResponse:
    """LM Studio / OpenAI-compatible fallback. Raises HTTPException(502) on failure."""
    from app.services.provider_router import ProviderRouter
    from app.services.router import ChatRequest, Provider

    req = ChatRequest(messages=messages, model="auto", provider=Provider.local)  # type: ignore[arg-type]
    resolved = await ProviderRouter().resolve(req, user_id, db)
    text = await resolved.provider.complete(messages=messages, model=resolved.model, temperature=0.7)
    obj = _parse_suggest_json(text)
    if obj is None:
        raise HTTPException(status_code=502, detail="suggest could not produce valid JSON")
    logger.info("suggest served from local %s", resolved.model)
    return _build_suggest_response(obj, goal, known_tools)


@router.post("/agents/suggest", response_model=SuggestResponse)
async def suggest_agent(
    body: SuggestRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    """Smart Suggest: draft name/description/system_prompt + tools/model from a goal string.

    Cloud-then-local fallback (free-model aware): try OpenRouter with a :free
    model first (your key is free-only), then LM Studio/local. A 401
    "User not found." from OpenRouter no longer surfaces as a raw 502 — it
    falls through to local and logs a hint.
    """
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
    messages = [{"role": "user", "content": meta_prompt}]

    # Attempt 1: cloud (OpenRouter, :free models).
    cloud_resp, cloud_error = await _suggest_cloud(messages, user_id, db, known_tools, body.goal)
    if cloud_resp is not None:
        return cloud_resp

    # Attempt 2: local (LM Studio / OpenAI-compatible). Surface a useful hint
    # instead of the raw provider payload when both tiers fail.
    try:
        return await _suggest_local(messages, user_id, db, known_tools, body.goal)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        logger.warning("suggest local failed: %s", msg)
        if _looks_like_auth_error(cloud_error or ""):
            raise HTTPException(
                status_code=502,
                detail=(
                    "suggest generation failed on cloud (401 User not found — check OpenRouter API key) "
                    f"and local fallback failed: {msg}"
                ),
            )
        if cloud_error:
            raise HTTPException(status_code=502, detail=f"suggest generation failed (cloud: {cloud_error}; local: {msg})")
        raise HTTPException(status_code=502, detail=f"suggest generation failed: {msg}")


# ── Param routes ──


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
    agent = await _get_owned_agent(db, agent_id, user_id)
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
    agent = await _get_owned_agent(db, agent_id, user_id)
    await db.delete(agent)
    await db.commit()
    return {"detail": "Agent deleted"}


@router.post("/agents/{agent_id}/publish")
async def publish_agent(
    agent_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    """Owner publishes a new version; installers see banner until they upgrade."""
    agent = await _get_owned_agent(db, agent_id, user_id)
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


# ── Workspace: per-user-per-agent files + undo (T3, ADR-0002/0003) ──


@router.get("/agents/{agent_id}/workspace/files")
async def workspace_files(
    agent_id: UUID,
    path: str = ".",
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    from app.services.workspace.store import get_workspace_store

    await _get_workspace_agent(db, agent_id, user_id)
    store = get_workspace_store()
    files = store.list_files(str(user_id), str(agent_id), path)
    return {"files": files}


@router.get("/agents/{agent_id}/workspace/file")
async def workspace_file(
    agent_id: UUID,
    path: str,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    from app.services.workspace.store import get_workspace_store

    await _get_workspace_agent(db, agent_id, user_id)
    store = get_workspace_store()
    return store.read_file(str(user_id), str(agent_id), path)


@router.get("/agents/{agent_id}/workspace/edits")
async def workspace_edits(
    agent_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user),
    limit: int | None = Query(default=None, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    from app.models.file_edits import FileEdit

    await _get_workspace_agent(db, agent_id, user_id)
    q = select(FileEdit).where(FileEdit.user_id == user_id, FileEdit.agent_id == agent_id).order_by(FileEdit.created_at.desc())
    if limit is not None:
        q = q.limit(limit).offset(offset)
    res = await db.execute(q)
    return {"data": res.scalars().all()}


class UndoRequest(BaseModel):
    edit_id: str


@router.post("/agents/{agent_id}/workspace/undo")
async def workspace_undo(
    agent_id: UUID,
    body: UndoRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    from app.services.workspace.store import get_workspace_store

    await _get_workspace_agent(db, agent_id, user_id)
    store = get_workspace_store()
    return await store.undo(str(user_id), str(agent_id), body.edit_id, db)
