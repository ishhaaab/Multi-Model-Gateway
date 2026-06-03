import httpx
import json
import uuid
import copy

COMFY_URL = "http://host.docker.internal:8188"

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

async def generate_image(
    prompt: str,
    negative_prompt: str = "text, watermark, blurry, low quality",
    steps: int = 10,
    cfg: float = 1.2,
    aspect_ratio: str = DEFAULT_ASPECT_RATIO,
    batch_size: int = 1,
    seed: int = None
) -> str:
    workflow = copy.deepcopy(BASE_WORKFLOW)
    
    # inject parameters
    workflow["6"]["inputs"]["text"] = prompt
    workflow["7"]["inputs"]["text"] = negative_prompt
    workflow["3"]["inputs"]["steps"] = steps
    workflow["3"]["inputs"]["cfg"] = cfg
    workflow["3"]["inputs"]["seed"] = seed or uuid.uuid4().int % (2**32)
    workflow["17"]["inputs"]["aspect_ratio"] = aspect_ratio
    workflow["18"]["inputs"]["batch_size"] = batch_size

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