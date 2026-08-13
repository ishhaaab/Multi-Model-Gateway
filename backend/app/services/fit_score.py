"""VRAM-aware fit scoring for the local model catalog and Hugging Face.

Local metadata comes from LM Studio (/api/v0/models: quant, max context);
Hugging Face metadata comes from the HF Hub /api/models (safetensors
parameters/size, downloads, likes). VRAM need is a documented heuristic, not
a promise:

  weights_gb ≈ size on disk          (or params_b × bytes/param for the quant)
  kv_gb      ≈ ctx_tokens × 128 KB × (params_b / 7)   # GQA-era ballpark
  need_gb    ≈ (weights + kv) × 1.1                   # runtime overhead

Verdicts: fits_fully (need ≤ free VRAM), partial_offload (≥40% of the
weights fit), wont_fit, cpu_only (no GPU detected).
"""
import logging
import re
import time

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# effective bytes per parameter for common quantizations (GGUF-style ballpark)
QUANT_BYTES_PER_PARAM = {
    "q2": 0.40, "q3": 0.48, "q4": 0.60, "q5": 0.70, "q6": 0.85, "q8": 1.10,
    "f16": 2.0, "bf16": 2.0, "fp16": 2.0, "f32": 4.0, "fp32": 4.0,
}
DEFAULT_BYTES_PER_PARAM = 0.60  # assume Q4-ish when the quant is unknown

# shared sort order for every cookbook: best-fit first, then score within a rank
_VERDICT_RANK = {"fits_fully": 0, "partial_offload": 1, "cpu_only": 2, "wont_fit": 3, "unknown": 4}

_PARAMS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[bB]\b")

# in-process TTL cache for Hugging Face catalog fetches (keyed by search+limit)
_HF_CACHE_TTL = 600  # seconds
_hf_cache: dict[tuple[str, int], tuple[float, list[dict]]] = {}


def _cache_get(search: str, limit: int) -> list[dict] | None:
    item = _hf_cache.get((search, limit))
    if item is None:
        return None
    ts, models = item
    if time.monotonic() - ts > _HF_CACHE_TTL:
        _hf_cache.pop((search, limit), None)
        return None
    return models


def _cache_set(search: str, limit: int, models: list[dict]) -> None:
    _hf_cache[(search, limit)] = (time.monotonic(), models)


def _parse_params_b(text: str) -> float | None:
    """'qwen2.5-7b-instruct' → 7.0 ; 'llama-3.1-8B-Q4' → 8.0"""
    match = _PARAMS_RE.search(text or "")
    return float(match.group(1)) if match else None


def _bytes_per_param(quant: str | None) -> float:
    q = (quant or "").lower()
    for key, bpp in QUANT_BYTES_PER_PARAM.items():
        if key in q:
            return bpp
    return DEFAULT_BYTES_PER_PARAM


async def get_local_models() -> list[dict]:
    """Catalog from LM Studio (/api/v0/models); if it's down the catalog is empty."""
    models: list[dict] = []

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{settings.LM_URL}/api/v0/models")
            response.raise_for_status()
        for m in response.json().get("data", []):
            if m.get("type") not in (None, "llm", "vlm"):
                continue  # skip embedding models etc.
            models.append({
                "id": m.get("id", ""),
                "source": "lmstudio",
                "params_b": _parse_params_b(m.get("id", "")),
                "quant": m.get("quantization"),
                "size_bytes": None,  # LM Studio doesn't report file size here
                "max_context": m.get("max_context_length"),
            })
    except Exception as e:
        logger.warning("LM Studio catalog unavailable: %r", e)

    return models


def estimate_fit(model: dict, vram_free_mb: int | None, context_tokens: int) -> dict:
    params_b = model.get("params_b")

    if model.get("size_bytes"):
        weights_gb = model["size_bytes"] / 1e9
    elif params_b:
        weights_gb = params_b * _bytes_per_param(model.get("quant"))
    else:
        weights_gb = None

    if weights_gb is None:
        return {
            "verdict": "unknown",
            "score": 0,
            "need_gb": None,
            "rationale": "could not estimate model size (no file size or parameter count)",
        }

    kv_gb = context_tokens * 128e3 * ((params_b or 7) / 7) / 1e9
    need_gb = (weights_gb + kv_gb) * 1.1

    if vram_free_mb is None:
        return {
            "verdict": "cpu_only",
            "score": 0,
            "need_gb": round(need_gb, 1),
            "rationale": f"no GPU detected; ~{need_gb:.1f} GB would be needed at {context_tokens} ctx (CPU inference will be slow)",
        }

    free_gb = vram_free_mb / 1024
    score = min(100, round(100 * free_gb / need_gb))

    if need_gb <= free_gb:
        verdict = "fits_fully"
        rationale = (f"~{weights_gb:.1f} GB weights + ~{kv_gb:.1f} GB KV cache "
                     f"(@{context_tokens} ctx) fits in {free_gb:.1f} GB free VRAM")
    elif free_gb >= weights_gb * 0.4:
        verdict = "partial_offload"
        rationale = (f"needs ~{need_gb:.1f} GB but only {free_gb:.1f} GB free — "
                     f"partial GPU offload, expect reduced speed")
    else:
        verdict = "wont_fit"
        rationale = f"needs ~{need_gb:.1f} GB, only {free_gb:.1f} GB free VRAM"

    return {
        "verdict": verdict,
        "score": score,
        "need_gb": round(need_gb, 1),
        "rationale": rationale,
    }


async def build_cookbook(hardware: dict, context_tokens: int | None = None) -> dict:
    context_tokens = context_tokens or settings.COOKBOOK_CONTEXT_TOKENS
    vram_free_mb = None
    if hardware["gpu_available"]:
        # single-GPU assumption: score against the card with the most free VRAM
        vram_free_mb = max(g["vram_free_mb"] for g in hardware["gpus"])

    entries = []
    for model in await get_local_models():
        fit = estimate_fit(model, vram_free_mb, context_tokens)
        entries.append({**{k: v for k, v in model.items() if k != "size_bytes"}, **fit})

    entries.sort(key=lambda e: (_VERDICT_RANK.get(e["verdict"], 5), -e["score"]))

    recommendation = None
    if entries and entries[0]["verdict"] in ("fits_fully", "partial_offload"):
        recommendation = entries[0]["id"]

    return {
        "hardware": hardware,
        "context_tokens": context_tokens,
        "models": entries,
        "recommendation": recommendation,
    }


async def get_hf_models(search: str = "", limit: int = 10) -> list[dict]:
    """Top Hugging Face models from the Hub API, sorted by downloads.

    Returns a lightweight catalog entry per model (params from safetensors,
    size in bytes, popularity stats). Never raises — on any failure it logs a
    warning and returns [] so the cookbook page degrades to an empty table.
    Results are cached in-process for _HF_CACHE_TTL seconds.
    """
    cached = _cache_get(search, limit)
    if cached is not None:
        return cached

    params: dict = {"limit": min(limit, 50), "sort": "downloads"}
    if search:
        params["search"] = search

    models: list[dict] = []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get("https://huggingface.co/api/models", params=params)
            response.raise_for_status()
        for m in response.json():
            weights = m.get("safetensors") or m.get("pytorch") or {}
            params_b = weights.get("parameters") if isinstance(weights, dict) else None
            if params_b is None:
                params_b = _parse_params_b(m.get("id", ""))
            models.append({
                "id": m.get("id", ""),
                "source": "hf",
                "params_b": params_b,
                "size_bytes": weights.get("total") if isinstance(weights, dict) else None,
                "quant": None,
                "max_context": None,
                "downloads": m.get("downloads"),
                "likes": m.get("likes"),
                "lastModified": m.get("lastModified"),
                "pipeline_tag": m.get("pipeline_tag"),
                "library_name": m.get("library_name"),
            })
    except Exception as e:
        logger.warning("Hugging Face catalog unavailable: %r", e)
        return []

    _cache_set(search, limit, models)
    return models


async def build_hf_cookbook(hardware: dict, context_tokens: int, search: str = "", limit: int = 10) -> dict:
    """Fit-score the Hugging Face catalog against the probed hardware.

    Shares estimate_fit and the verdict sort order with build_cookbook, so the
    two tables rank apples-to-apples. Response mirrors the local cookbook but
    with a `search` echo and `count` instead of a recommendation.
    """
    vram_free_mb = None
    if hardware["gpu_available"]:
        # single-GPU assumption: score against the card with the most free VRAM
        vram_free_mb = max(g["vram_free_mb"] for g in hardware["gpus"])

    entries = []
    for model in await get_hf_models(search, limit):
        fit = estimate_fit(model, vram_free_mb, context_tokens)
        entries.append({**{k: v for k, v in model.items() if k != "size_bytes"}, **fit})

    entries.sort(key=lambda e: (_VERDICT_RANK.get(e["verdict"], 5), -e["score"]))

    return {
        "hardware": hardware,
        "context_tokens": context_tokens,
        "search": search,
        "models": entries,
        "count": len(entries),
    }
