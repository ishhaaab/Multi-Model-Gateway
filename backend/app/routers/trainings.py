import json
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.queue import get_queue
from app.core.redis import get_redis
from app.core.security import get_current_user
from app.db import get_db
from app.models.trainings import TrainingJob

router = APIRouter()

# Redis pub/sub + cancel flag channel names. The trainer worker (next batch)
# will import these from its own module; they live here for now as the only
# producer/consumer contract between the API and the trainer.
CHANNEL = "train:{job_id}"
CANCEL_KEY = "train:cancel:{job_id}"

TRAINING_ROOT = Path(settings.TRAINING_ROOT)
TRAINING_ROOT.mkdir(parents=True, exist_ok=True)

_MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024        # dataset zip cap: 2 GB
_MAX_EXTRACTED_BYTES = 2 * 1024 * 1024 * 1024     # total uncompressed cap (zip-bomb guard)
_MAX_FILE_BYTES = 200 * 1024 * 1024               # per-file cap after extraction
_MAX_FILE_COUNT = 1000                            # max files extracted from one zip
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def _safe_zip_member(info: zipfile.ZipInfo) -> str | None:
    """Return a safe flattened target basename for a zip entry, or None to skip.

    Unsafe entries (absolute paths, drive letters, '..' traversal, backslash
    separators) are rejected — never extracted. Directories and macOS __MACOSX
    junk are skipped. Leading directories are stripped so every real file lands
    flat in the dataset dir.
    """
    name = info.filename
    if "\\" in name:
        return None
    if name.startswith("/") or (len(name) > 1 and name[1] == ":"):
        return None
    parts = name.split("/")
    if any(p in ("", ".", "..") for p in parts):
        return None
    if parts[0] == "__MACOSX":
        return None
    return parts[-1]


def _job_summary(job: TrainingJob) -> dict:
    return {
        "id": str(job.id),
        "name": job.name,
        "base_model": job.base_model,
        "status": job.status,
        "stage": job.stage,
        "progress": job.progress,
        "created_at": job.created_at,
        "artifact_filename": job.artifact_filename,
        "sample_image": job.sample_image,
        "error": job.error,
    }


async def _get_owned_job(job_id: str, user_id: str, db: AsyncSession) -> TrainingJob:
    result = await db.execute(select(TrainingJob).where(TrainingJob.id == job_id))
    job = result.scalar_one_or_none()
    # 404 for both missing and non owned, so job ids can't be enumerated
    if job is None or str(job.user_id) != str(user_id):
        raise HTTPException(status_code=404, detail="training job not found")
    return job


@router.post("/trainings")
async def create_training(
    name: str = Form(min_length=1),
    base_model: Literal["flux-dev", "sdxl"] = Form(...),
    dataset: UploadFile = File(...),
    steps: int = Form(default=1000, ge=100, le=20000),
    learning_rate: float = Form(default=1e-4, gt=0),
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    if not dataset.filename or not dataset.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=422, detail="dataset must be a .zip file")

    job_id = uuid.uuid4()
    job_dir = TRAINING_ROOT / str(job_id)
    dataset_dir = job_dir / "dataset"
    job_dir.mkdir(parents=True, exist_ok=True)

    try:
        # stream the upload to raw.zip, capped at 2 GB
        raw_path = job_dir / "raw.zip"
        total = 0
        with raw_path.open("wb") as fh:
            while chunk := await dataset.read(1024 * 1024):
                total += len(chunk)
                if total > _MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="dataset zip exceeds 2 GB limit")
                fh.write(chunk)

        # extract safely and flattened: all files land directly in dataset/
        dataset_dir.mkdir(parents=True, exist_ok=True)
        extracted_bytes = 0
        extracted_count = 0
        with zipfile.ZipFile(raw_path) as zf:
            for info in zf.infolist():
                target = _safe_zip_member(info)
                if target is None:
                    continue  # rejected/unsafe or junk entry — skip it
                extracted_count += 1
                if extracted_count > _MAX_FILE_COUNT:
                    raise HTTPException(
                        status_code=422,
                        detail=f"dataset contains too many files (max {_MAX_FILE_COUNT})",
                    )
                size = 0
                with zf.open(info) as src, (dataset_dir / target).open("wb") as dst:
                    # count actual bytes written — zip headers can lie about sizes
                    while chunk := src.read(1024 * 1024):
                        size += len(chunk)
                        if size > _MAX_FILE_BYTES:
                            raise HTTPException(
                                status_code=422,
                                detail=f"dataset file exceeds {_MAX_FILE_BYTES // (1024 * 1024)} MB after extraction",
                            )
                        dst.write(chunk)
                extracted_bytes += size
                if extracted_bytes > _MAX_EXTRACTED_BYTES:
                    raise HTTPException(
                        status_code=422,
                        detail="dataset too large after extraction",
                    )

        # validate the dataset: at least 3 images; caption .txt files may ride along
        image_count = sum(
            1 for f in dataset_dir.iterdir()
            if f.is_file() and f.suffix.lower() in _IMAGE_EXTENSIONS
        )
        if image_count < 3:
            raise HTTPException(
                status_code=422,
                detail=f"dataset must contain at least 3 image files (.jpg, .jpeg, .png, .webp); found {image_count}",
            )

        job = TrainingJob(
            id=job_id,
            user_id=user_id,
            name=name,
            base_model=base_model,
            dataset_dir=str(dataset_dir),
            status="queued",
            stage="queued",
            progress=0,
            params={"steps": steps, "learning_rate": learning_rate},
        )
        db.add(job)
        await db.commit()

        try:
            queue = await get_queue()
            await queue.enqueue_job("run_train", str(job.id))
        except Exception as e:
            # the row is already committed — flip it to failed so no orphaned
            # "queued" row points at files we are about to delete
            job.status = "failed"
            job.error = "failed to enqueue training job"
            await db.commit()
            shutil.rmtree(job_dir, ignore_errors=True)
            raise HTTPException(status_code=500, detail="failed to enqueue training job") from e
    except Exception:
        # leave no half-written job dir behind on any failure after files land
        shutil.rmtree(job_dir, ignore_errors=True)
        await db.rollback()
        raise
    finally:
        await dataset.close()

    return {"job_id": str(job.id), "status": "queued"}


@router.get("/trainings")
async def list_trainings(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    result = await db.execute(
        select(TrainingJob)
        .where(TrainingJob.user_id == user_id)
        .order_by(TrainingJob.created_at.desc())
        .limit(50)
    )
    return {"data": [_job_summary(j) for j in result.scalars().all()]}


@router.get("/trainings/{job_id}")
async def get_training(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    job = await _get_owned_job(job_id, user_id, db)
    return {
        **_job_summary(job),
        "dataset_dir": job.dataset_dir,
        "params": job.params,
        "sample_image": job.sample_image,
    }


@router.post("/trainings/{job_id}/cancel")
async def cancel_training(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    job = await _get_owned_job(job_id, user_id, db)
    if job.status in ("complete", "failed", "cancelled"):
        raise HTTPException(status_code=409, detail=f"job already {job.status}")

    redis = await get_redis()
    # the trainer checks this flag between steps; expire it in case the job is gone
    await redis.set(CANCEL_KEY.format(job_id=job_id), "1", ex=3600)

    if job.status == "queued":
        # not picked up yet then cancel directly so the trainer skips non queued jobs
        job.status = "cancelled"
        await db.commit()
        await redis.publish(CHANNEL.format(job_id=job_id),
                            json.dumps({"type": "done", "status": "cancelled"}))
    return {"id": job_id, "status": job.status}


@router.get("/trainings/{job_id}/stream")
async def stream_training(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    # Subscribe to the channel BEFORE reading the job row: a terminal event
    # published between the snapshot read and the subscribe would otherwise be
    # missed, leaving the stream hanging on a finished job. (research.py has the
    # same pattern — out of scope here.)
    redis = await get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(CHANNEL.format(job_id=job_id))
    try:
        job = await _get_owned_job(job_id, user_id, db)
    except Exception:
        await pubsub.unsubscribe(CHANNEL.format(job_id=job_id))
        await pubsub.aclose()
        raise

    async def relay():
        # snapshot first, so late subscribers see the current state immediately
        yield f"data: {json.dumps({'type': 'progress', 'stage': job.stage, 'progress': job.progress, 'message': job.status})}\n\n"
        if job.status in ("complete", "failed", "cancelled"):
            if job.status == "complete":
                yield f"data: {json.dumps({'type': 'done', 'status': 'complete', 'artifact_filename': job.artifact_filename}, ensure_ascii=False)}\n\n"
            elif job.status == "failed":
                yield f"data: {json.dumps({'type': 'error', 'message': job.error or 'failed'})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'done', 'status': 'cancelled'})}\n\n"
            return

        try:
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15)
                if message is None:
                    yield ": keepalive\n\n"  # SSE comment keeps proxies from closing the idle stream
                    continue
                data = message["data"]
                yield f"data: {data}\n\n"
                try:
                    event = json.loads(data)
                except ValueError:
                    continue
                if event.get("type") in ("done", "error"):
                    return
        finally:
            await pubsub.unsubscribe(CHANNEL.format(job_id=job_id))
            await pubsub.aclose()

    return StreamingResponse(
        relay(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/trainings/{job_id}/artifact")
async def get_training_artifact(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    job = await _get_owned_job(job_id, user_id, db)
    if job.status != "complete" or not job.artifact_filename:
        raise HTTPException(status_code=404, detail="artifact not available")

    job_dir = (TRAINING_ROOT / str(job.id)).resolve()
    artifact = (job_dir / job.artifact_filename).resolve()
    # guard against traversal: the artifact must live inside the job's dir
    if not artifact.is_relative_to(job_dir) or not artifact.is_file():
        raise HTTPException(status_code=404, detail="artifact not available")

    return FileResponse(
        artifact,
        media_type="application/octet-stream",
        filename=job.artifact_filename,
    )
