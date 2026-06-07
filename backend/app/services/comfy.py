import httpx
import uuid
import copy
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.workflows import Workflow
from app.core.exceptions import NotFoundError
from app.core.config import settings


COMFY_URL = settings.COMFY_URL

# Valid aspect_ratio values accepted by the ComfyUI ResolutionSelector node (id "17").
# Single source of truth: the frontend fetches these via GET /v1/images/aspect-ratios,
# and the image request validates against them. Every workflow that uses the
# ResolutionSelector node shares this list.
ASPECT_RATIOS = [
    "1:1 (Square)",
    "3:2 (Photo)",
    "4:3 (Standard)",
    "16:9 (Widescreen)",
    "21:9 (Ultrawide)",
    "2:3 (Portrait Photo)",
    "3:4 (Portrait Standard)",
    "9:16 (Portrait Widescreen)",
]
DEFAULT_ASPECT_RATIO = "9:16 (Portrait Widescreen)"

BASE_WORKFLOW = {
    "3": {
        "inputs": {
            "seed": 685468484323813,
            "steps": 10,
            "cfg": 1.2,
            "sampler_name": "lcm",
            "scheduler": "sgm_uniform",
            "denoise": 1,
            "model": ["4", 0],
            "positive": ["6", 0],
            "negative": ["7", 0],
            "latent_image": ["18", 0]
        },
        "class_type": "KSampler"
    },
    "4": {
        "inputs": {"ckpt_name": "xxxRay_dmd2.safetensors"},
        "class_type": "CheckpointLoaderSimple"
    },
    "6": {
        "inputs": {
            "text": "",
            "clip": ["4", 1]
        },
        "class_type": "CLIPTextEncode"
    },
    "7": {
        "inputs": {
            "text": "text, watermark, blurry, low quality",
            "clip": ["4", 1]
        },
        "class_type": "CLIPTextEncode"
    },
    "8": {
        "inputs": {
            "samples": ["3", 0],
            "vae": ["4", 2]
        },
        "class_type": "VAEDecode"
    },
    "17": {
        "inputs": {
            "aspect_ratio": DEFAULT_ASPECT_RATIO,
            "megapixels": 1.3
        },
        "class_type": "ResolutionSelector"
    },
    "18": {
        "inputs": {
            "width": ["17", 0],
            "height": ["17", 1],
            "batch_size": 1
        },
        "class_type": "EmptySD3LatentImage"
    },
    "19": {
        "inputs": {"images": ["8", 0]},
        "class_type": "PreviewImage"
    }
}

async def get_workflow(workflow_id: str, user_id: str, db: AsyncSession):
    if not workflow_id:
        return BASE_WORKFLOW, None
    request= await db.execute(select(Workflow).where(
        Workflow.id == workflow_id,
        Workflow.user_id == user_id))
    
    workflow= request.scalar_one_or_none()
    if workflow is None:
        raise NotFoundError("Workflow not found")
    return workflow.graph, workflow.param_map
    

# find the first node whose class_type contains X (here we use a substring match) 
def _find_node(graph, class_substr):
    for node_id, node in graph.items():
        if class_substr in node.get("class_type", ""):
            return node_id, node
    return None, None

def inject_params(
    graph: dict,
    param_map: dict | None = None,
    *,
    prompt: str,
    negative_prompt: str,
    steps: int,
    cfg: float,
    seed: int,
    aspect_ratio: str,
    batch_size: int,
) -> dict:
    
    g= copy.deepcopy(graph)
    targets= {}

    # auto-detect: to figure out which node + input each param maps to
    # Anchor on the sampler; steps/cfg/seed sit right on it.
    sampler_id, sampler = _find_node(g, "KSampler")
    if sampler:
        s_inputs = sampler["inputs"]
        targets["steps"] = [sampler_id, "steps"]
        targets["cfg"] = [sampler_id, "cfg"]
        # KSampler calls it "seed"; KSamplerAdvanced calls it "noise_seed"
        targets["seed"] = [sampler_id, "noise_seed" if "noise_seed" in s_inputs else "seed"]
        # positive/negative are links like ["node_id", "input_slot"] and
        # the prompt text lives on that node's "text"
        if "positive" in s_inputs:
            targets["positive"] = [s_inputs["positive"][0], "text"]
        if "negative" in s_inputs:
            targets["negative"] = [s_inputs["negative"][0], "text"]

    # aspect ratio + batch size have their own nodes 
    res_id, _ = _find_node(g, "ResolutionSelector")
    if res_id:
        targets["aspect_ratio"] = [res_id, "aspect_ratio"]

    latent_id, _ = _find_node(g, "LatentImage")
    if latent_id:
        targets["batch_size"] = [latent_id, "batch_size"]

    # explicit overrides from the workflow's param_map have priority
    # over auto-detect
    targets.update(param_map or {})
    values= {
        "positive": prompt,
        "negative": negative_prompt,
        "steps": steps,
        "cfg": cfg,
        "seed": seed,
        "aspect_ratio": aspect_ratio,
        "batch_size": batch_size}
    
    for param, value in values.items():
        target = targets.get(param)
        if not target:
            continue                      # if this graph has no slot for that param then skip, don't crash
        node_id, input_key = target       # target is [node_id, input_slot]
        if node_id in g and "inputs" in g[node_id]:
            g[node_id]["inputs"][input_key] = value

    return g


async def generate_image(
    workflow_id: str | None,
    user_id: str,
    db: AsyncSession,
    *,
    prompt: str,
    negative_prompt: str,
    steps: int,
    cfg: float,
    aspect_ratio: str,
    batch_size: int,
    seed: int | None = None,
) -> str:
    
    graph, param_map = await get_workflow(workflow_id, user_id, db)
    seed = seed if seed is not None else uuid.uuid4().int % (2**32)

    workflow = inject_params(
        graph,
        param_map,
        prompt=prompt,
        negative_prompt=negative_prompt,
        steps=steps,
        cfg=cfg,
        seed=seed,
        aspect_ratio=aspect_ratio,
        batch_size=batch_size,
    )

    client_id = str(uuid.uuid4())

    async with httpx.AsyncClient(timeout=120) as client:
        # submit the job
        response = await client.post(
            f"{COMFY_URL}/prompt",
            json={"prompt": workflow, "client_id": client_id}
        )
        response.raise_for_status()
        prompt_id = response.json()["prompt_id"]

    return prompt_id


async def get_job_status(prompt_id: str) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"{COMFY_URL}/history/{prompt_id}")
        response.raise_for_status()
        history = response.json()
        
        if prompt_id not in history:
            return {"status": "pending"}
        
        job = history[prompt_id]
        outputs = job.get("outputs", {})
        
        # find images in outputs
        images = []
        for node_id, node_output in outputs.items():
            if "images" in node_output:
                for img in node_output["images"]:
                    images.append({
                        "filename": img["filename"],
                        "url": f"{COMFY_URL}/view?filename={img['filename']}&subfolder={img.get('subfolder', '')}&type={img.get('type', 'output')}"
                    })
        
        return {"status": "complete", "images": images}