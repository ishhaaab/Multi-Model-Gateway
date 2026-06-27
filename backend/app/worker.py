"""arq worker bootstrap, run as its own compose service:

    arq app.worker.WorkerSettings

arq was chosen over RQ/Celery because the whole codebase is async
asyncpg, httpx and arq runs coroutines natively on one loop instead of
wrapping each job in asyncio.run.
"""
from arq.connections import RedisSettings

from app.core.config import settings
# Register every model so SQLAlchemy can resolve cross-table foreign keys in this
# process. The worker only imports ResearchJob transitively, so without this its
# FK research_jobs.user_id -> users.id can't find the 'users' table at mapper-config
# time (NoReferencedTableError). Mirrors what alembic/env.py imports.
from app.models import (  # noqa: F401
    users, conversations, messages, refresh_tokens,
    presets, templates, memories, workflows, tool_permissions, research_jobs,
)
from app.services.research import run_research_job


async def run_research(ctx, job_id: str) -> None:
    await run_research_job(job_id)


class WorkerSettings:
    functions = [run_research]
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    job_timeout = settings.RESEARCH_JOB_TIMEOUT_SECONDS
    max_jobs = 2          # research runs are model+network heavy; keep concurrency low
    keep_result = 0       # job state lives in Postgres, not in arq's result store
