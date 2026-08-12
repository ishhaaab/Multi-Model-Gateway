"""arq worker bootstrap, run as its own compose service:

    arq app.worker.WorkerSettings

arq was chosen over RQ/Celery because the whole codebase is async
asyncpg, httpx and arq runs coroutines natively on one loop instead of
wrapping each job in asyncio.run.
"""
from datetime import datetime

from arq import cron
from arq.connections import RedisSettings
from sqlalchemy import delete

from app.core.config import settings
# Register every model so SQLAlchemy can resolve cross-table foreign keys in this
# process. The worker only imports ResearchJob transitively, so without this its
# FK research_jobs.user_id -> users.id can't find the 'users' table at mapper-config
# time (NoReferencedTableError). Mirrors what alembic/env.py imports.
from app.models import (  # noqa: F401
    users, conversations, messages, refresh_tokens,
    presets, templates, memories, workflows, tool_permissions, research_jobs,
    providers, trainings, memory_files,
)
from app.models.refresh_tokens import RefreshToken
from app.db import AsyncSessionLocal
from app.services.research import run_research_job


async def run_research(ctx, job_id: str) -> None:
    await run_research_job(job_id)


async def sweep_expired_tokens(ctx) -> None:
    """Hourly janitor: drop expired refresh-token rows (R7)."""
    async with AsyncSessionLocal() as db:
        await db.execute(delete(RefreshToken).where(RefreshToken.expires_at < datetime.utcnow()))
        await db.commit()


class WorkerSettings:
    functions = [run_research]
    # R7: hourly sweep of expired refresh tokens (minute 0 of every hour).
    # NOTE: arq does not hot-reload — restart the worker container after
    # changing anything here (functions or cron_jobs) for it to take effect.
    cron_jobs = [cron(sweep_expired_tokens, minute=0)]
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    job_timeout = settings.RESEARCH_JOB_TIMEOUT_SECONDS
    max_jobs = 2          # research runs are model+network heavy; keep concurrency low
    keep_result = 0       # job state lives in Postgres, not in arq's result store
