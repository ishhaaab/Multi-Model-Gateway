
import logging
import httpx

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text as sa_text
import uuid
from app.models.memories import Memory

logger = logging.getLogger(__name__)


EMBED_URL = "http://host.docker.internal:11434/api/embeddings"
EMBED_MODEL = "nomic-embed-text:latest"

async def get_embedding(content: str) -> list[float] | None:
    """Return an embedding vector, or None if the embedding service is
    unreachable / returns an unexpected response. Memory is an auxiliary
    feature, so callers degrade gracefully instead of failing the request."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                EMBED_URL,
                json={"model": EMBED_MODEL, "prompt": content},
            )
            response.raise_for_status()
            return response.json()["embedding"]
    except (httpx.HTTPError, KeyError, ValueError) as e:
        logger.warning("embedding request failed (%s); skipping memory", e)
        return None


async def store_memory(conversation_id: str, role: str, content: str, db: AsyncSession):
    vector = await get_embedding(content)
    if vector is None:
        return  # embedding unavailable; skip persisting this memory
    memory = Memory(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        role=role,
        content=content,
        embedding=vector,
    )
    db.add(memory)
    await db.commit()


async def retrieve_memories(conversation_id: str, query: str, db: AsyncSession):
    query_vector = await get_embedding(query)
    if query_vector is None:
        return []  # embedding unavailable; no memory context this turn
    result = await db.execute(
        sa_text("SELECT content, role, created_at FROM memories WHERE conversation_id = :cid ORDER BY embedding <=> :emb LIMIT 3"),
        {"cid": conversation_id, "emb": str(query_vector)},
    )
    rows = result.fetchall()
    return [{"role": r.role, "content": r.content, "created_at": r.created_at} for r in rows]
