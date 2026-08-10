"""Image-LoRA training orchestration, run by the arq trainer worker (see
app/trainer_worker.py). Delegates the actual training to ai-toolkit
(https://github.com/ostris/ai-toolkit), which the trainer Dockerfile clones
into /opt/ai-toolkit and runs as::

    python /opt/ai-toolkit/run.py <job config.yaml>

Progress is published to Redis pub/sub channel "train:{job_id}" as JSON
events. The SSE endpoint in routers/trainings.py subscribes and forwards
them. The job row in postgres is updated at each stage so plain polling
works too, and survives worker restarts.

Events:
  {"type":"progress","stage","progress","message"}
  {"type":"done","status":"complete","artifact_filename","sample_image"}
  {"type":"done","status":"cancelled"}
  {"type":"error","message"}

Cancellation: the cancel endpoint sets Redis key "train:cancel:{job_id}";
the worker checks it between output chunks and aborts cleanly.

Local SDXL models: the trainer compose service bind-mounts the host folder
${SDXL_MODEL_PATH} (default ./comfy-checkpoints) at /models/sdxl. When
SDXL_MODEL_PATH is set in .env, SDXL jobs point name_or_path at the local
folder (or a single-file checkpoint inside it when SDXL_MODEL_NAME is given)
instead of downloading the ~7GB Hugging Face model. Verified against the
ai-toolkit source in /opt/ai-toolkit: a single-file .safetensors IS loadable
directly — toolkit/stable_diffusion_model.py load_model() calls
StableDiffusionXLPipeline.from_single_file() whenever name_or_path exists on
disk and is NOT a directory (else it falls back to from_pretrained() for HF
ids / diffusers folders). No conversion step is needed. Note the model block
MUST set is_xl: true for SDXL or ai-toolkit treats the checkpoint as sd1 and
loads it with the wrong pipeline class.

Local SD1 models: the same pattern covers stable-diffusion-1.x —
${SD1_MODEL_PATH} (default ./comfy-checkpoints) is bind-mounted at
/models/sd1, and SD1 jobs point name_or_path there (optionally at
SD1_MODEL_NAME inside it) instead of downloading the ~4GB Hugging Face
model. SD1 must NOT set is_xl (and never is_flux) — ai-toolkit's ModelConfig
then infers the default 'sd1' arch and loads with
StableDiffusionPipeline.from_single_file(), the correct pipeline class for
SD1 checkpoints. SD1 is natively 512px, so the job resolution defaults to
512 and is capped at 1024.

6GB-VRAM tuning (sd1/sdxl) — verified against the installed ai-toolkit in
/opt/ai-toolkit: ``cache_latents_to_disk`` is a real dataset option
(toolkit/config_modules.py:1001; latents precomputed once and spilled to
disk instead of held in VRAM), ``ema_config.use_ema: false`` cleanly disables
EMA (toolkit/config_modules.py:545-549, EMAConfig at :827; no fp32 shadow
weights), and the ``low_vram`` model flag exists (config_modules.py:689) but
is a NO-OP for sd1/sdxl in this version — it is only consulted on the
FLUX/SD3/Wan transformer-quantization paths (stable_diffusion_model.py
:401/:665/:723, models/wan21/wan21.py, models/wan21/wan21_i2v.py,
util/quantize.py:416) so it is NOT set here. Combined with
batch_size 1, gradient_accumulation_steps 1, gradient_checkpointing, a
frozen text encoder and 512px resolution, an RTX 3060 Laptop (6GB) runs
~0.3-1s/step.

Adding a new base model type (extension point): (a) add the name to the
base_model Literal in routers/trainings.py, (b) add a branch in _build_config
below — model name_or_path (HF default or a local *_MODEL_PATH mount),
is_flux/is_xl arch flags, noise scheduler + sample-block params, and (c) add
a *_MODEL_PATH/*_MODEL_NAME pair in core/config.py plus a compose bind-mount
when a local checkpoint should be supported. The router Literal is the API
contract; _build_config is the single place that turns base_model into
ai-toolkit config.
"""
import asyncio
import json
import logging
import os
import re
import shutil
import time
from pathlib import Path

import yaml
from sqlalchemy import select

from app.core.config import settings
from app.core.redis import get_redis
from app.db import AsyncSessionLocal
from app.models.trainings import TrainingJob

logger = logging.getLogger(__name__)

CHANNEL = "train:{job_id}"
CANCEL_KEY = "train:cancel:{job_id}"

AI_TOOLKIT_DIR = "/opt/ai-toolkit"   # where the trainer Dockerfile clones ai-toolkit
RUNNER = f"{AI_TOOLKIT_DIR}/run.py"

TRAINING_ROOT = Path(settings.TRAINING_ROOT)


class TrainingCancelled(Exception):
    pass


async def _publish(redis, job_id: str, event: dict) -> None:
    await redis.publish(CHANNEL.format(job_id=job_id), json.dumps(event, ensure_ascii=False))


async def _set_stage(job, db, redis, stage: str, progress: int, message: str = "") -> None:
    job.stage = stage
    job.progress = progress
    await db.commit()
    await _publish(redis, str(job.id), {
        "type": "progress", "stage": stage, "progress": progress, "message": message,
    })


def _build_config(job) -> dict:
    """Build the ai-toolkit config dict for job.base_model.

    The top-level shape was verified against the examples shipped in the
    cloned repo (config/examples/train_lora_flux_24gb.yaml and the sd35 lora
    example): current ai-toolkit expects ``job: extension`` with a ``config:``
    wrapper containing one ``sd_trainer`` process — toolkit/config.py refuses
    configs without a "config" section. Older versions used ``job: train``
    with the options at the top level; do not "fix" this back to that shape.

    SDXL/SD1 model resolution: if the matching *_MODEL_PATH setting is set,
    name_or_path points at the local model mounted at /models/<family> (a
    diffusers-format folder, or a single-file .safetensors when *_MODEL_NAME
    is given) — ai-toolkit loads single files via from_single_file(), no
    conversion step needed. Otherwise the HF default is used (a one-time
    download). The model block sets ``is_xl: true`` for SDXL so ai-toolkit
    builds a StableDiffusionXLPipeline; SD1 leaves it false (and is_flux
    false) so ai-toolkit uses the default sd1 arch (StableDiffusionPipeline).
    See the module docstring for how to add a new base model type.
    """
    params = job.params or {}
    steps = int(params.get("steps", 1000))
    lr = float(params.get("learning_rate", 1e-4))
    is_flux = job.base_model == "flux-dev"
    is_sd1 = job.base_model == "sd1"
    is_xl = job.base_model == "sdxl"
    save_every = max(50, steps // 10)

    # resolution control for small-GPU users. FLUX is capped at 1024 (its
    # native training resolution; bigger just wastes VRAM). SD1 defaults to
    # 512 (its native resolution) and is capped at 1024 — SD1 was trained at
    # 512 and does not meaningfully benefit from higher. SDXL honors the
    # request as given.
    resolution = int(params.get("resolution", 512 if is_sd1 else 1024))
    if is_flux or is_sd1:
        resolution = min(resolution, 1024)

    if is_flux:
        model_name_or_path = "black-forest-labs/FLUX.1-dev"
    elif is_xl:
        if settings.SDXL_MODEL_PATH:
            local = "/models/sdxl"
            if settings.SDXL_MODEL_NAME:
                local = f"{local}/{settings.SDXL_MODEL_NAME}"
            logger.info("training %s: using local SDXL model at %s", str(job.id), local)
            model_name_or_path = local
        else:
            logger.warning(
                "training %s: SDXL_MODEL_PATH not set — falling back to %s "
                "(downloads ~7GB from Hugging Face on first use)",
                str(job.id), "stabilityai/stable-diffusion-xl-base-1.0",
            )
            model_name_or_path = "stabilityai/stable-diffusion-xl-base-1.0"
    else:  # sd1
        if settings.SD1_MODEL_PATH:
            local = "/models/sd1"
            if settings.SD1_MODEL_NAME:
                local = f"{local}/{settings.SD1_MODEL_NAME}"
            logger.info("training %s: using local SD1 model at %s", str(job.id), local)
            model_name_or_path = local
        else:
            logger.warning(
                "training %s: SD1_MODEL_PATH not set — falling back to %s "
                "(downloads ~4GB from Hugging Face on first use)",
                str(job.id), "runwayml/stable-diffusion-v1-5",
            )
            model_name_or_path = "runwayml/stable-diffusion-v1-5"

    process = {
        "type": "sd_trainer",
        # save_root inside ai-toolkit becomes {training_folder}/{name} — the
        # final LoRA lands at {output}/{job_id}/{job_id}.safetensors
        "training_folder": str(TRAINING_ROOT / str(job.id) / "output"),
        "device": "cuda:0",
        "network": {
            "type": "lora",
            "linear": 16,
            "linear_alpha": 16,
        },
        "save": {
            "dtype": "float16",
            "save_every": save_every,
            "max_step_saves_to_keep": 2,
            "push_to_hub": False,
        },
        "datasets": [
            {
                "folder_path": job.dataset_dir,
                "caption_ext": "txt",
                "cache_latents_to_disk": True,
                "resolution": [resolution],
            }
        ],
        "train": {
            "batch_size": 1,
            "steps": steps,
            "gradient_accumulation_steps": 1,
            "train_unet": True,
            "train_text_encoder": False,   # FLUX TE is not LoRA-able; SDXL/SD1 TE off by default
            "gradient_checkpointing": True,
            "optimizer": "adamw8bit",
            "lr": lr,
            "noise_scheduler": "flowmatch" if is_flux else "ddpm",
            "dtype": "bf16",
            # 6GB-VRAM tuning (sd1/sdxl): EMA off (no fp32 shadow weights);
            # cache_latents_to_disk is set on the dataset block; batch 1 +
            # grad accum 1 + gradient checkpointing + frozen TE are the rest
            # of the 6GB recipe (see module docstring). FLUX keeps EMA on.
            "ema_config": {"use_ema": True, "ema_decay": 0.99} if is_flux else {"use_ema": False},
        },
        "model": {
            "name_or_path": model_name_or_path,
            "is_flux": is_flux,
            # required for SDXL: without is_xl, ai-toolkit's ModelConfig infers
            # arch 'sd1' and loads the checkpoint with StableDiffusionPipeline
            # instead of StableDiffusionXLPipeline (breaks single-file loading
            # and samples wrong). is_xl is ignored for flux; sd1 must leave it
            # false so ai-toolkit uses the default sd1 arch.
            "is_xl": is_xl,
            "quantize": is_flux,   # 8bit mixed precision; FLUX needs it on 24GB class cards
        },
        "sample": {
            # generic placeholder prompt — real users will want their own
            # subject / trigger word here. Prompts could later come from params.
            # sd1/sdxl both sample with euler_a / guidance 7.0 / 30 steps.
            "prompts": ["a photo of a person"],
            "sampler": "flowmatch" if is_flux else "euler_a",  # 'sgm' was removed upstream
            "sample_every": save_every,
            "width": resolution,
            "height": resolution,
            "seed": 42,
            "walk_seed": True,
            "guidance_scale": 3.5 if is_flux else 7.0,
            "sample_steps": 20 if is_flux else 30,
            "neg": "",
        },
    }

    return {"job": "extension", "config": {"name": str(job.id), "process": [process]}}


async def _write_config(job, cfg) -> Path:
    cfg_path = TRAINING_ROOT / str(job.id) / "config.yaml"
    # the upload endpoint creates the job dir, but be safe if it vanished
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    return cfg_path


async def _run_subprocess(job, db, redis, cfg_path) -> int:
    """Run ai-toolkit and stream its output as progress events. Returns the
    process exit code (0 = completed, non-zero = failed). Raises
    TrainingCancelled when the cancel flag is seen mid-run — the caller's
    except TrainingCancelled handles the cancelled bookkeeping."""
    env = os.environ.copy()
    if job.base_model == "flux-dev":
        token = env.get("HF_TOKEN", "")
        if not token:
            raise RuntimeError("FLUX.1-dev is a gated model — set HF_TOKEN in .env")
        env["HF_TOKEN"] = token

    proc = await asyncio.create_subprocess_exec(
        "python", RUNNER, str(cfg_path),
        cwd=AI_TOOLKIT_DIR,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    job_id = str(job.id)
    last_publish = 0.0
    last_step = -1

    def _step_progress(step: int, total: int) -> int:
        if not total:
            total = int((job.params or {}).get("steps", step))
        return min(90, 10 + int(80 * step / max(total, 1)))

    async def _consume():
        nonlocal last_publish, last_step
        while True:
            chunk = await proc.stdout.read(4096)
            if not chunk:
                break
            # ai-toolkit's progress bar is a tqdm bar redrawn with \r (no \n),
            # so split on both line endings — a \n-only reader would starve
            # until some other print happens.
            for seg in re.split(r"[\r\n]+", chunk.decode(errors="replace")):
                seg = seg.strip()
                if not seg:
                    continue
                now = time.monotonic()

                # 1. a training step: tqdm "N/total [elapsed..." or legacy "Step: N"
                step = None
                total = 0
                m = re.search(r"Step:\s*(\d+)", seg)
                if m:
                    step = int(m.group(1))
                else:
                    m = re.search(r"(\d+)\s*/\s*(\d+)\s*\[", seg)
                    if m:
                        step, total = int(m.group(1)), int(m.group(2))
                if step is not None and step != last_step:
                    # always track the latest step so the final progress value
                    # stays right even when publishing is throttled below
                    last_step = step
                    if now - last_publish >= 5:
                        await _set_stage(job, db, redis, "training", _step_progress(step, total), seg[:200])
                        last_publish = now
                    continue

                # 2. checkpoint save — match only explicit save announcements so
                # the startup config dump ("use_ema: true" etc.) can never
                # false-trigger; and only once real training steps have been
                # seen (stage already "training"), never during startup
                low = seg.lower()
                if any(k in low for k in ("saving at step", "saved checkpoint", "saving lora", "saved lora")):
                    if job.stage == "training" and now - last_publish >= 5:
                        await _set_stage(job, db, redis, "saving", 95, seg[:200])
                        last_publish = now
                    continue

                # 3. heartbeat so the SSE stream stays alive during long silent stretches
                if now - last_publish >= 5:
                    await _set_stage(job, db, redis, "training", job.progress, seg[:200])
                    last_publish = now

            if await redis.exists(CANCEL_KEY.format(job_id=job_id)):
                proc.terminate()
                await proc.wait()
                raise TrainingCancelled
        return await proc.wait()

    try:
        # wait_for (rather than wrapping only proc.wait()) so a run that hangs
        # mid-step without writing output still hits the timeout and is killed.
        return await asyncio.wait_for(_consume(), timeout=settings.TRAINING_JOB_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        logger.error("training %s: hit %ss timeout; terminating", job_id, settings.TRAINING_JOB_TIMEOUT_SECONDS)
        proc.terminate()
        await proc.wait()
        raise


async def _collect_artifacts(job, db, redis) -> None:
    """After a clean exit, find the produced LoRA + newest sample image and
    copy them to the job dir so the API can serve them without touching the
    ai-toolkit output tree."""
    job_id = str(job.id)
    output_dir = TRAINING_ROOT / job_id / "output"
    job_dir = TRAINING_ROOT / job_id

    lora_candidates = list(output_dir.rglob("*.safetensors"))
    if not lora_candidates:
        raise RuntimeError("training finished but no LoRA artifact was produced")
    # prefer filenames containing "lora", else the most recently written file
    # (ai-toolkit names the final save {job.name}.safetensors — a UUID here)
    lora_candidates.sort(key=lambda p: ("lora" not in p.name.lower(), -p.stat().st_mtime))
    shutil.copy2(lora_candidates[0], job_dir / "lora.safetensors")

    sample_candidates = []
    for pattern in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
        sample_candidates.extend(output_dir.rglob(pattern))
    sample_image = None
    if sample_candidates:
        newest = max(sample_candidates, key=lambda p: p.stat().st_mtime)
        sample_image = f"sample{newest.suffix.lower()}"
        shutil.copy2(newest, job_dir / sample_image)

    job.artifact_filename = "lora.safetensors"
    job.sample_image = sample_image
    job.stage = "done"
    job.progress = 100
    job.status = "complete"
    await db.commit()
    await _publish(redis, job_id, {
        "type": "done", "status": "complete",
        "artifact_filename": job.artifact_filename, "sample_image": job.sample_image,
    })


async def _ensure_captions(job) -> None:
    """ai-toolkit does NOT require a .txt caption per image.

    Verified in the cloned repo (toolkit/data_loader.py +
    toolkit/dataloader_mixins.py): FileItemDTO.load_caption falls back to an
    empty caption (or default_caption) when {image}.txt is missing, so we do
    not synthesize caption files here. Datasets may ride along their own .txt
    captions (same basename); images without one simply train with an empty
    prompt, which is equivalent to a blank caption at caption_dropout_rate 0.
    """
    logger.info("training %s: ai-toolkit tolerates missing captions; not writing .txt files", str(job.id))


async def run_train_job(job_id: str) -> None:
    """arq entry point: owns the job row's lifecycle from running → terminal."""
    redis = await get_redis()
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(TrainingJob).where(TrainingJob.id == job_id))
        job = result.scalar_one_or_none()
        if job is None or job.status != "queued":
            logger.warning("training %s: missing or not queued; skipping", job_id)
            return

        job.status = "running"
        await db.commit()

        try:
            await _ensure_captions(job)
            await _set_stage(job, db, redis, "preparing", 3, "building config")

            try:
                cfg = _build_config(job)
                cfg_path = await _write_config(job, cfg)
            except Exception as e:
                logger.error("training %s: failed to build config: %r", job_id, e)
                job.status = "failed"
                job.error = str(e)[:2000]
                await db.commit()
                await _publish(redis, job_id, {"type": "error", "message": str(e)[:2000]})
                return

            rc = await _run_subprocess(job, db, redis, cfg_path)
            if rc != 0:
                job.status = "failed"
                job.error = f"training exited with code {rc}"
                await db.commit()
                await _publish(redis, job_id, {"type": "error", "message": job.error})
            else:
                await _collect_artifacts(job, db, redis)
        except TrainingCancelled:
            job.status = "cancelled"
            await db.commit()
            await _publish(redis, job_id, {"type": "done", "status": "cancelled"})
        except Exception as e:
            logger.error("training %s failed: %r", job_id, e)
            job.status = "failed"
            job.error = str(e)[:2000]
            await db.commit()
            await _publish(redis, job_id, {"type": "error", "message": str(e)[:2000]})
        finally:
            await redis.delete(CANCEL_KEY.format(job_id=job_id))
