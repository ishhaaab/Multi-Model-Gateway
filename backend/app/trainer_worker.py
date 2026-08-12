"""arq worker bootstrap for image-LoRA training, run as its own compose service:

    arq app.trainer_worker.WorkerSettings

Same layout as app.worker.py (deep research), tuned for GPU-bound training:
one job at a time and a long job timeout to match ai-toolkit runs.
"""
from arq.connections import RedisSettings

from app.core.config import settings
# Register every model so SQLAlchemy can resolve cross-table foreign keys in this
# process. The trainer only imports TrainingJob transitively, so without this its
# FK trainings.user_id -> users.id can't find the 'users' table at mapper-config
# time (NoReferencedTableError). Mirrors what app/worker.py and alembic/env.py import.
from app.models import (  # noqa: F401
    users, conversations, messages, refresh_tokens,
    presets, templates, memories, workflows, tool_permissions, research_jobs,
    providers, trainings, memory_files,
)
from app.services.trainer import run_train_job


async def run_train(ctx, job_id: str) -> None:
    await run_train_job(job_id)


class WorkerSettings:
    functions = [run_train]
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    job_timeout = settings.TRAINING_JOB_TIMEOUT_SECONDS
    max_jobs = 1          # training is GPU-bound; one job at a time
    keep_result = 0       # job state lives in Postgres, not in arq's result store
