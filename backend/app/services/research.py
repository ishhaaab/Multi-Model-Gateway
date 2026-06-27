"""Deep-research orchestration: plan then search then read then synthesize, run by
the arq worker (see app/worker.py).

Progress is published to Redis pub/sub channel "research:{job_id}" as JSON
events. The SSE endpoint in routers/research.py subscribes and forwards
them. The job row in postgres is updated at each stage so plain polling
works too, and survives worker restarts.

Events:
  {"type":"progress","stage","progress","message"}
  {"type":"done","status":"complete","result","sources"}
  {"type":"done","status":"cancelled"}
  {"type":"error","message"}

Cancellation: the cancel endpoint sets Redis key "research:cancel:{job_id}";
the worker checks it between steps and aborts cleanly.
"""
import json
import logging

from sqlalchemy import select

from app.core.config import settings, OPENROUTER_API_KEY
from app.core.redis import get_redis
from app.db import AsyncSessionLocal
from app.models.research_jobs import ResearchJob
from app.services.router import get_local_client, get_openrouter_client
from app.services.search import fetch_page, search

logger = logging.getLogger(__name__)

CHANNEL = "research:{job_id}"
CANCEL_KEY = "research:cancel:{job_id}"

PLAN_PROMPT = """You are a research planner. Given a research question, produce
up to {max_queries} distinct web search queries that together cover the question.
Respond with ONLY a JSON array of strings, e.g. ["query one", "query two"].
No explanations, no markdown."""

SYNTH_PROMPT = """You are a research analyst. Answer the user's research question
using ONLY the numbered sources below. Rules:
- Cite sources inline using their bracketed number, e.g. [1] or [2], after each claim.
- If sources conflict, say so and cite both.
- If the sources are insufficient for part of the question, state that openly.
- End with a "Sources" section listing each number (e.g. [1]) with its title and URL.

{sources_block}"""


class ResearchCancelled(Exception):
    pass


def _pick_client(provider: str | None, model: str | None):
    """Research favours the cloud model (long context, many sources) unless
    the job pinned a provider."""
    use_openrouter = (
        provider == "openrouter"
        or (provider in (None, "", "auto") and settings.OPENROUTER_DEFAULT_MODEL and OPENROUTER_API_KEY)
    )
    if use_openrouter:
        chosen = model if model and model != "auto" else settings.OPENROUTER_DEFAULT_MODEL
        return get_openrouter_client(), chosen
    chosen = model if model and model != "auto" else (settings.LM_CHAT_MODEL or settings.LM_DEFAULT_MODEL)
    return get_local_client(), chosen


async def _publish(redis, job_id: str, event: dict) -> None:
    await redis.publish(CHANNEL.format(job_id=job_id), json.dumps(event, ensure_ascii=False))


async def _check_cancelled(redis, job_id: str) -> None:
    if await redis.exists(CANCEL_KEY.format(job_id=job_id)):
        raise ResearchCancelled()


async def _set_stage(job, db, redis, stage: str, progress: int, message: str = "") -> None:
    job.stage = stage
    job.progress = progress
    await db.commit()
    await _publish(redis, str(job.id), {
        "type": "progress", "stage": stage, "progress": progress, "message": message,
    })


async def _complete(client, model: str, system: str, user: str, temperature: float = 0.3) -> str:
    response = await client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        stream=False,
        temperature=temperature,
    )
    return response.choices[0].message.content or ""


def _parse_queries(raw: str, fallback: str) -> list[str]:
    """Planner output should be a JSON array; tolerate fences and prose."""
    text = raw.strip()
    if "[" in text and "]" in text:
        text = text[text.index("["): text.rindex("]") + 1]
    try:
        queries = json.loads(text)
        if isinstance(queries, list):
            queries = [str(q).strip() for q in queries if str(q).strip()]
            if queries:
                return queries[: settings.RESEARCH_MAX_QUERIES]
    except ValueError:
        pass
    return [fallback]


async def _research(job, db, redis) -> tuple[str, list[dict]]:
    client, model = _pick_client(job.provider, job.model)
    job_id = str(job.id)

    # 1. plan
    await _set_stage(job, db, redis, "planning", 5, "generating search queries")
    try:
        raw_plan = await _complete(client, model, PLAN_PROMPT.format(
            max_queries=settings.RESEARCH_MAX_QUERIES), job.query)
        queries = _parse_queries(raw_plan, job.query)
    except Exception as e:
        logger.warning("research %s: planner failed (%r); using the raw query", job_id, e)
        queries = [job.query]
    await _check_cancelled(redis, job_id)

    # 2. search n gather candidate sources, deduped by URL
    candidates: list[dict] = []
    seen: set[str] = set()
    for i, q in enumerate(queries):
        await _set_stage(job, db, redis, "searching",
                         10 + int(30 * i / len(queries)), f"searching: {q}")
        try:
            for r in await search(q, settings.RESEARCH_RESULTS_PER_QUERY):
                if r["url"] and r["url"] not in seen:
                    seen.add(r["url"])
                    candidates.append(r)
        except Exception as e:
            logger.warning("research %s: search '%s' failed: %r", job_id, q, e)
        await _check_cancelled(redis, job_id)

    if not candidates:
        raise RuntimeError("no search results found for any query")

    # 3. read n fetch the top pages
    sources: list[dict] = []
    to_read = candidates[: settings.RESEARCH_MAX_SOURCES]
    for i, c in enumerate(to_read):
        await _set_stage(job, db, redis, "reading",
                         40 + int(40 * i / len(to_read)), f"reading: {c['url']}")
        try:
            content = await fetch_page(c["url"])
        except Exception as e:
            logger.warning("research %s: fetch '%s' failed: %r", job_id, c["url"], e)
            content = c.get("snippet", "")  # fall back to the search snippet
        if content:
            sources.append({
                "n": len(sources) + 1,
                "title": c["title"],
                "url": c["url"],
                "content": content,
            })
        await _check_cancelled(redis, job_id)

    if not sources:
        raise RuntimeError("could not read any of the search results")

    # 4. synthesize with citations
    await _set_stage(job, db, redis, "synthesizing", 85, f"synthesizing from {len(sources)} sources")
    sources_block = "\n\n".join(
        f"[{s['n']}] {s['title']} — {s['url']}\n{s['content']}" for s in sources
    )
    answer = await _complete(
        client, model, SYNTH_PROMPT.format(sources_block=sources_block), job.query,
    )

    # persist sources without page bodies (the answer carries the citations)
    slim_sources = [{"n": s["n"], "title": s["title"], "url": s["url"]} for s in sources]
    return answer, slim_sources


async def run_research_job(job_id: str) -> None:
    """arq entry point: owns the job row's lifecycle from running → terminal."""
    redis = await get_redis()
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ResearchJob).where(ResearchJob.id == job_id))
        job = result.scalar_one_or_none()
        if job is None or job.status != "queued":
            logger.warning("research %s: missing or not queued; skipping", job_id)
            return

        job.status = "running"
        await db.commit()

        try:
            answer, sources = await _research(job, db, redis)
            job.status = "complete"
            job.progress = 100
            job.stage = "done"
            job.result = answer
            job.sources = sources
            await db.commit()
            await _publish(redis, job_id, {
                "type": "done", "status": "complete", "result": answer, "sources": sources,
            })
        except ResearchCancelled:
            job.status = "cancelled"
            await db.commit()
            await _publish(redis, job_id, {"type": "done", "status": "cancelled"})
        except Exception as e:
            logger.error("research %s failed: %r", job_id, e)
            job.status = "failed"
            job.error = str(e)
            await db.commit()
            await _publish(redis, job_id, {"type": "error", "message": str(e)})
        finally:
            await redis.delete(CANCEL_KEY.format(job_id=job_id))
