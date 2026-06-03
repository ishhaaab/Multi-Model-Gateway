import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.templates import PromptTemplate
from app.core.config import settings


QUALITY_TAGS = "masterpiece, high quality, very aesthetic, 4k" 

HUMAN_TAGS= "(realistic skin:1.2), pores"

POLAROID_TAGS= "shot on polaroid, shot on kodak, candid photo, (polaroid pic:1.4)"


DEFAULT_STRUCTURE = """
quality,
art style, artist references,
camera,
subject,
accessories and clothes,
pose,
environment,
lighting
"""

async def load_rewrite_model() -> str:
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{settings.LM_URL}/api/v1/models/load",
            json={
                "model": settings.LM_DEFAULT_MODEL,
                "context_length": 2048,
                "flash_attention": True
            }
        )
        response.raise_for_status()
        return response.json()["instance_id"]

async def unload_rewrite_model(instance_id: str):
    async with httpx.AsyncClient(timeout=30) as client:
        await client.post(
            f"{settings.LM_URL}/api/v1/models/unload",
            json={"instance_id": instance_id}
        )

async def get_template(template_id: str, user_id: str, db: AsyncSession) -> str:
    if not template_id:
        return DEFAULT_STRUCTURE
    result = await db.execute(
        select(PromptTemplate).where(
            PromptTemplate.id == template_id,
            PromptTemplate.user_id == user_id,
        )
    )
    template = result.scalar_one_or_none()
    return template.structure if template else DEFAULT_STRUCTURE

async def rewrite_prompt(prompt: str, template_id: str = None, db: AsyncSession = None, user_id: str = None) -> str:
    structure = await get_template(template_id, user_id, db) if db else DEFAULT_STRUCTURE

    instance_id = await load_rewrite_model()

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{settings.LM_URL}/v1/chat/completions",
                json={
                    "model": settings.LM_DEFAULT_MODEL,
                    "messages": [
                        {
                            "role": "system",
"content": f"""You are an SDXL prompt translator. You excel at converting the user's natural language description
into comma separated weighted tags.

Follow this category order:
{structure}

Tagging Rules:
- If the user emphasizes something with words like "make sure", "really", "extra", "must", "definitely", "very" or some other synonymns
wrap those specific tag(s) with a weight like: (tag 1:weight), (tag 2:weight),.....(tag n:weight) where n= the no. of words user is emphasising on
and tag= the words being emphasised
- if you think the user's request requires something to be weighted ie (has an importance of more than 1), 
use (tag:weight) for that part of the request with an appropriate weight in the range of 1.2 to 1.8.

- for the weight part in (tag(s):weight) use the following Weighing Rules:
    - Use (tag: 1.3) for mild emphasis, (tag: 1.5) for strong emphasis, (tag: 1.8) for very strong emphasis
    - Only weigh tags that were explicitly emphasized.

- DO NOT have weights greater than 2 or less than 1.
- Do NOT include category names in the output.
- Return only comma separated tags, nothing else.

"""
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "stream": False
                }
            )
            response.raise_for_status()
            rewritten= response.json()["choices"][0]["message"]["content"].strip()
            return f"{QUALITY_TAGS}, {rewritten}"
    finally:
        await unload_rewrite_model(instance_id)